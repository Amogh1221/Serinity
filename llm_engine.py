"""
llm_engine.py — Serinity on-device LLM engine.

Changes from cloud version:
  - HuggingFace InferenceClient → Ollama local inference
  - Ollama structured output (format=schema) for guaranteed valid JSON
  - faster-whisper → SenseVoice-Small (FunASR) for STT + emotion detection
  - LLM1Output gains clinical_summary field (used for HyDE-style RAG queries)
  - LLM2Output gains risk_assessment + protective_factors fields
  - LLM2 uses keep_alive=0 so it's evicted from VRAM immediately after ANALYZE
    (keeps LLM1 + embeddings warm within the 6GB VRAM budget)

CHANGELOG (2026-07-12) — safety + prompt revision, based on production log review:
  - LLM1Output gains risk_flag: bool. This is an NLU-based risk signal,
    populated by LLM1 every turn (independent of intent), used by main.py
    as a second signal alongside safety.py's keyword check — either one
    firing forces the ANALYZE path. See main.py for the combination logic.
  - LLM1_SYSTEM_PROMPT: added a non-negotiable safety rule at the very top
    of the prompt (read before anything else). The log showed LLM1 staying
    on intent="CONTINUE" across four consecutive turns of escalating
    suicidal content (turns 5-8) because the ANALYZE criteria buried "ask
    about self-harm" as one soft bullet among many. It's now an unconditional
    rule that overrides the rest of the prompt.
  - LLM1_SYSTEM_PROMPT: fixed "When Receiving Analysis Results" — it
    previously only referenced the original six analysis domains and never
    mentioned risk_assessment or protective_factors at all, despite those
    fields existing in LLM2Output since Phase 3. That's why turns 3 and 10
    show LLM2 correctly flagging "significant risk" while LLM1's synthesis
    ignored it entirely. risk_assessment now explicitly overrides
    psychoeducation/pattern-synthesis in that section.
  - Both prompts trimmed: removed the three full worked JSON examples and
    the verbose Output Structure prose from LLM1's prompt (schema-constrained
    decoding already guarantees the JSON shape, so the model doesn't need to
    learn it from examples) — one short tone example remains. LLM2's eight
    domains are compressed from 5-10 sub-bullets each to 2-3 bullets + a
    short example. Nothing safety-related was cut.
  - LLM2_SYSTEM_PROMPT: added an explicit instruction not to infer stressors
    (job loss, money, relationship problems) that the patient never actually
    stated. The log showed LLM2 correctly leaving "stressors" empty at turn 3
    ("no clear life events mentioned") but inventing plausible-sounding
    stressors by turn 9-10 that the patient never said.

NOTE on SenseVoice integration:
  Using funasr+torch path (option a from changes.txt §5.1). ONNX route was
  evaluated but funasr is more reliable within the hackathon time budget.
  Swap to ONNX later for a lighter dependency footprint.
"""

import os
import io
import re
import json
import tempfile
import ollama as _ollama

from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# HF_HOME must be set BEFORE funasr/huggingface_hub imports so the model
# cache lands in the project's models/ folder, not ~/.cache/huggingface.
# Resolve relative path from .env against the project root (this file's dir).
_hf_home_raw = os.getenv("HF_HOME", "./models")
if not os.path.isabs(_hf_home_raw):
    _hf_home_raw = os.path.join(os.path.dirname(os.path.abspath(__file__)), _hf_home_raw)
os.environ["HF_HOME"] = _hf_home_raw
os.makedirs(_hf_home_raw, exist_ok=True)

# ---------------------------------------------------------------------------
# Env config
# ---------------------------------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM1_MODEL  = os.getenv("LLM1_MODEL",  "phi4-mini")
LLM2_MODEL  = os.getenv("LLM2_MODEL",  "qwen2.5:7b-instruct")

# ---------------------------------------------------------------------------
# Pydantic output schemas — used for Ollama structured output
# ---------------------------------------------------------------------------

class LLM1Output(BaseModel):
    assistant_message: str
    intent: Literal["CONTINUE", "ANALYZE"]
    # NLU-based risk signal — true when THIS turn's patient message expresses
    # suicidal ideation, self-harm, or wanting to die/not exist.
    risk_flag: bool = False
    # Populated only when intent == "ANALYZE".
    clinical_summary: Optional[str] = None


class LLM2Output(BaseModel):
    emotional_themes:       List[str] = Field(default_factory=list)
    thinking_patterns:      List[str] = Field(default_factory=list)
    behavioral_patterns:    List[str] = Field(default_factory=list)
    interpersonal_dynamics: List[str] = Field(default_factory=list)
    stressors:              List[str] = Field(default_factory=list)
    unclear_areas:          List[str] = Field(default_factory=list)
    # Phase 3 additions — always populated
    risk_assessment:        str       = "Not yet assessed"
    protective_factors:     List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# System Prompts — Phase 6 revision (trimmed for cost/naturalness, safety
# rule promoted to the top, analysis-results handling fixed)
# ---------------------------------------------------------------------------

LLM1_SYSTEM_PROMPT = """
You are a compassionate, professional AI psychiatrist conducting a clinical interview. Do not introduce yourself by name.

##  CRITICAL SAFETY RULE (Overrides all else)
If the patient expresses active/passive thoughts of suicide, self-harm, or wishing to die (even indirectly, e.g., "end it", "not be here"):
1. Set "intent" to "ANALYZE".
2. Set "risk_flag" to true.
3. In "assistant_message", ask directly and calmly about immediate safety (e.g., "Are you safe right now?", "Do you have a plan?"). Do not ask open-ended exploration questions.
*Note:* Do not trigger this for normal stress or sadness. Re-evaluate "risk_flag" fresh on every turn based ONLY on the current message.

## Role & Conversational Style
- Build rapport and conduct a thorough psychiatric interview (explore onset, duration, severity, impact, sleep, appetite, mood, etc.).
- Acknowledge/reflect the patient's feelings before asking ONE focused follow-up. Do not stack questions. Use 3-5 sentences total.
- **Passive Patients:** If they say "I don't know", "what should I do?", etc., TAKE THE LEAD. Briefly validate, then ask a concrete question about a specific area (e.g., sleep). Do not respond with a passive statement.

## Intent Decision Logic
- CONTINUE (Default): Use when symptom profile (onset/duration/severity/impact) is incomplete, patient is passive, or < 8-10 meaningful exchanges have occurred.
- ANALYZE: Use ONLY if 8-10+ substantive exchanges occurred, full symptom profiles are established across 3-4 domains, AND more questions yield diminishing returns. Do not trigger just because the patient is passive.

## Handling Analysis Results (When provided)
- If `risk_assessment` shows ANY concern, address immediate safety FIRST.
- If no risk: Synthesize insights naturally, use patterns to guide targeted follow-ups, offer gentle psychoeducation, and validate. 

## Ethical Guardrails
- NO PRESCRIBING: Never recommend or adjust medication. Advise consulting a physician if asked.
- Never minimize symptoms.
- Tone Signals: The user's input may include bracketed tags (e.g., [vocal tone: sad]). Use these as cues for empathy. NEVER include bracketed tags (e.g., [vocal tone: empathetic]) in your own output.

## Output Structure (Strict JSON)
- assistant_message: Separate your empathetic reflection and your follow-up question with "&&". If intent="ANALYZE", omit the question and the "&&".
- clinical_summary: If intent="ANALYZE", provide a 3-5 sentence third-person clinical summary (e.g., "Patient reports a two-week history of low mood..."). Otherwise, null.

Example Output:
{"assistant_message": "That sounds really difficult, and it makes sense you'd feel stuck. && When did this feeling of being stuck first start?", "intent": "CONTINUE", "risk_flag": false, "clinical_summary": null}
"""

LLM2_SYSTEM_PROMPT = """
You are a clinical pattern analyst. Analyze the conversation history and clinical context (Sims' Symptoms in the Mind) to identify patterns across 8 domains.

##  CRITICAL ANTI-HALLUCINATION RULE
Only report what the patient **explicitly stated or unmistakably implied**. If a domain lacks evidence, return an empty list `[]`. Do NOT infer unmentioned symptoms, assume common comorbidities, or pad fields. Sparse, accurate data is always correct. 

## Domains (Be specific, include duration/frequency where available)
1. emotional_themes: Recurring moods (e.g., "Sadness lasting 3 weeks").
2. thinking_patterns: Cognitive style/content (e.g., "Rumination on past mistakes").
3. behavioral_patterns: Observable actions (e.g., "Avoiding social gatherings for 2 months").
4. interpersonal_dynamics: Relationship functioning (e.g., "Withdrawing from family").
5. stressors: Explicitly named triggers (e.g., "Recent job loss"). If not explicitly mentioned, return [].
6. unclear_areas: Gaps needing follow-up (e.g., "Duration of sleep issues not specified").
7. risk_assessment: ALWAYS POPULATED. Must start with exactly ONE of:
   - "No safety concerns identified"
   - "Some risk indicators present - monitor"
   - "Significant risk indicators present - recommend immediate professional/crisis support"
   Follow with specific evidence from the text.
8. protective_factors: Concrete, existing strengths/resources (e.g., "Maintains close relationship with sister").

## Guardrails
- **NO MEDICATION:** Never suggest, recommend, or factor in pharmacological treatments.
- Use clinical language appropriately, but do not force it onto sparse data.

## Output Structure (Strict JSON)
{
  "emotional_themes": [],
  "thinking_patterns": [],
  "behavioral_patterns": [],
  "interpersonal_dynamics": [],
  "stressors": [],
  "unclear_areas": [],
  "risk_assessment": "...",
  "protective_factors": []
}
"""


# ---------------------------------------------------------------------------
# Ollama client helper
# ---------------------------------------------------------------------------

def _ollama_client():
    """Return an Ollama client pointed at the configured host."""
    return _ollama.Client(host=OLLAMA_HOST)


# ---------------------------------------------------------------------------
# SenseVoice emotion parser helpers
# ---------------------------------------------------------------------------

# SenseVoice embeds tags like <|HAPPY|><|Speech|><|withitn|> in the output.
_EMOTION_MAP = {
    "HAPPY":     "happy",
    "SAD":       "sad",
    "ANGRY":     "angry",
    "NEUTRAL":   "neutral",
    "FEARFUL":   "fearful",
    "DISGUSTED": "disgusted",
    "SURPRISED": "surprised",
}
_KNOWN_EVENTS = {"Speech", "Laughter", "Cry", "Cough", "Sneeze", "Breath", "Noise"}

_TAG_RE = re.compile(r"<\|([^|]+)\|>")


def _parse_sensevoice_output(raw_text: str) -> tuple[str, str, str | None]:
    """
    Parse SenseVoice output into (clean_text, emotion, event).
    SenseVoice output format: <|lang|><|EMOTION|><|Event|><|withitn|>actual words
    """
    tags = _TAG_RE.findall(raw_text)
    clean = _TAG_RE.sub("", raw_text).strip()

    emotion = "neutral"
    event: str | None = None

    for tag in tags:
        upper = tag.upper()
        if upper in _EMOTION_MAP:
            emotion = _EMOTION_MAP[upper]
        # Check event (case-sensitive match against known events)
        if tag in _KNOWN_EVENTS:
            event = tag

    return clean, emotion, event


# ---------------------------------------------------------------------------
# Main engine class
# ---------------------------------------------------------------------------

class LLMEngine:
    def __init__(self):
        self.model1 = LLM1_MODEL
        self.model2 = LLM2_MODEL
        self._sense_voice = None
        self._init_stt()

    # ------------------------------------------------------------------
    # STT init — SenseVoice-Small via FunASR
    # ------------------------------------------------------------------

    def _init_stt(self):
        try:
            print("[STARTUP] Loading SenseVoice-Small (STT + emotion engine)...")
            from funasr import AutoModel
            # SenseVoiceSmall downloads to HF_HOME or ~/.cache/huggingface on first run.
            # Set HF_HOME env var to redirect download location if needed.
            self._sense_voice = AutoModel(
                model="FunAudioLLM/SenseVoiceSmall",  # HF repo (iic/ is ModelScope)
                trust_remote_code=True,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                device="cpu",
                hub="hf",   # use HuggingFace Hub (not ModelScope)
            )
            print("[STARTUP] SenseVoice-Small ready.")
        except Exception as e:
            print(f"[WARNING] SenseVoice failed to load: {e}")
            print("[WARNING] Voice transcription will be disabled. The app will still work for text input.")
            self._sense_voice = None

    # ------------------------------------------------------------------
    # LLM1 — Dr. Aiden, conversational psychiatrist
    # ------------------------------------------------------------------

    def psychiatrist_response(self, context: list) -> LLM1Output:
        """
        Call LLM1 (phi4-mini) via Ollama with structured JSON output.
        LLM1 stays warm in Ollama (no keep_alive override) because it handles
        every turn and the VRAM budget allows it alongside embeddings.
        """
        try:
            client = _ollama_client()
            messages = [{"role": "system", "content": LLM1_SYSTEM_PROMPT}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            response = client.chat(
                model=self.model1,
                messages=messages,
                format=LLM1Output.model_json_schema(),
                options={"temperature": 0.6, "num_predict": 1024},
            )
            raw = response.message.content
            return LLM1Output.model_validate_json(raw)

        except Exception as e:
            print(f"[LLM1 ERROR] {e}")
            # risk_flag defaults to False here deliberately: this fallback
            # can't assess risk at all, so it must not claim to. The
            # deterministic keyword check in safety.py runs independently of
            # this call and still protects the patient even if this fails.
            return LLM1Output(
                assistant_message="I'm here, and I'm listening. Please take your time. && Would you like to tell me more about what's on your mind?",
                intent="CONTINUE",
                risk_flag=False,
                clinical_summary=None,
            )

    # ------------------------------------------------------------------
    # LLM2 — Clinical pattern analyst
    # ------------------------------------------------------------------

    def internal_reasoning(self, context: list) -> LLM2Output:
        """
        Call LLM2 (qwen2.5:7b-instruct) via Ollama with structured JSON output.
        keep_alive=0 evicts LLM2 from VRAM immediately after the call, freeing
        ~4.5GB so LLM1 + embeddings (~2.6GB combined) can stay resident.
        This adds ~5-10s load latency on the ANALYZE path, which is acceptable
        since ANALYZE is already the slow multi-call path.
        """
        try:
            client = _ollama_client()
            messages = [{"role": "system", "content": LLM2_SYSTEM_PROMPT}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            response = client.chat(
                model=self.model2,
                messages=messages,
                format=LLM2Output.model_json_schema(),
                options={
                    "temperature": 0.4,  # lower temp for analytical consistency
                    "num_predict": 2048,
                    "keep_alive": 0,     # evict from VRAM immediately after response
                },
            )
            raw = response.message.content
            return LLM2Output.model_validate_json(raw)

        except Exception as e:
            print(f"[LLM2 ERROR] {e}")
            return LLM2Output()

    # ------------------------------------------------------------------
    # Summarize overflow history (for working memory rolling summary)
    # ------------------------------------------------------------------

    def summarize_history(self, turns: list) -> str:
        """
        Ask LLM1 to compress old conversation turns into a brief rolling
        summary. Used by memory_store to manage the working memory window.
        """
        if not turns:
            return ""
        try:
            client = _ollama_client()
            formatted = "\n".join(
                f"{t['role'].upper()}: {t['content']}" for t in turns
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a clinical note-taker. Summarize the following "
                        "patient-psychiatrist conversation excerpt in 3-5 sentences, "
                        "third-person clinical register. Capture key symptoms, "
                        "themes, and any safety concerns. Be concise."
                    ),
                },
                {"role": "user", "content": formatted},
            ]
            response = client.chat(
                model=self.model1,
                messages=messages,
                options={"temperature": 0.3, "num_predict": 300},
            )
            return response.message.content.strip()
        except Exception as e:
            print(f"[SUMMARIZE ERROR] {e}")
            return "[Summary unavailable]"

    # ------------------------------------------------------------------
    # STT — SenseVoice-Small transcription + emotion
    # ------------------------------------------------------------------

    def transcribe_audio(self, audio_bytes: bytes) -> dict:
        """
        Transcribe audio and return emotion metadata.

        Returns:
            {
                "text":    str,            # transcribed speech
                "emotion": str,            # happy|sad|angry|neutral|fearful|disgusted|surprised|unknown
                "event":   str | None      # e.g. "Cry", "Laughter", "Speech", None
            }
        """
        if self._sense_voice is None:
            return {"text": "", "emotion": "unknown", "event": None}

        try:
            # SenseVoice needs a file path, not raw bytes — write to a temp file
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            res = self._sense_voice.generate(
                input=tmp_path,
                cache={},
                language="auto",
                use_itn=True,
                batch_size_s=60,
            )

            # res is a list of dicts; first element has the result
            if res and isinstance(res, list) and len(res) > 0:
                raw_text = res[0].get("text", "")
                clean_text, emotion, event = _parse_sensevoice_output(raw_text)
                return {"text": clean_text.strip(), "emotion": emotion, "event": event}

            return {"text": "", "emotion": "unknown", "event": None}

        except Exception as e:
            print(f"[STT ERROR] {e}")
            return {"text": "", "emotion": "unknown", "event": None}
        finally:
            # Clean up temp file
            try:
                import os as _os
                _os.unlink(tmp_path)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Module-level singleton (imported by main.py and memory_store.py)
# ---------------------------------------------------------------------------
llm_engine = LLMEngine()