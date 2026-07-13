import os
import ollama
from core.ports import LLM1Output, LLM2Output

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
- assistant_message: Separate your empathetic reflection and your follow-up question with "&&". ALWAYS include both parts, regardless of your intent.
- clinical_summary: If intent="ANALYZE", provide a highly clinical, phenomenological 3-5 sentence third-person summary of the patient's state, symptoms, and duration. Write this in the formal register of a psychiatric textbook to optimize semantic search (HyDE) over clinical literature. Otherwise, null.

Example 1 (CONTINUE):
{"assistant_message": "That sounds really difficult, and it makes sense you'd feel stuck. && When did this feeling of being stuck first start?", "intent": "CONTINUE", "risk_flag": false, "clinical_summary": null}

Example 2 (ANALYZE):
{"assistant_message": "Thank you for sharing that with me. It takes courage to open up. && Could you tell me more about how these thoughts are affecting your daily life?", "intent": "ANALYZE", "risk_flag": false, "clinical_summary": "Patient presents with a two-week history of pervasive anhedonia and psychomotor retardation. They report persistent rumination centered on themes of worthlessness and guilt, exacerbated by a recent interpersonal stressor. Sleep architecture is notably disrupted with early morning awakening. No overt psychotic features or acute risk of self-harm are currently endorsed."}
"""

LLM2_SYSTEM_PROMPT = """
You are a clinical pattern analyst. You will be provided with a patient's existing clinical profile, a summary of their current session, their recent message history, and relevant clinical context (Sims' Symptoms in the Mind).

Your task is to perform a delta analysis: compare their current behavior and state against their existing profile, and output the updated patterns across 8 domains.

##  CRITICAL ANTI-HALLUCINATION RULE
Only report what the patient **explicitly stated or unmistakably implied** in the current session OR what remains highly relevant from their existing profile. If a domain lacks evidence and has no prior history, return an empty list `[]`. Do NOT infer unmentioned symptoms, assume common comorbidities, or pad fields. Sparse, accurate data is always correct. 

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
"""

class OllamaLLMProvider:
    """
    Concrete implementation of the LLMProvider protocol using local Ollama models.
    Provides the engine for both the fast conversational responses (LLM1) 
    and the deep background pattern analysis (LLM2).
    """
    def __init__(self, host: str, model1: str, model2: str):
        self.host = host
        self.model1 = model1
        self.model2 = model2
        
    def _client(self):
        return ollama.Client(host=self.host)
        
    def generate_opening_context(self, profile_recap: str | None) -> list:
        if profile_recap:
            return [
                {
                    "role": "user",
                    "content": (
                        f"{profile_recap}\n\n"
                        "Start the psychiatric session. Greet the patient warmly, "
                        "briefly acknowledge continuity if it feels right, then use && "
                        "to add an open question at the end — e.g. "
                        "'Welcome back, it's good to see you. && How have things been for you since we last spoke?'"
                    ),
                }
            ]
        else:
            return [
                {
                    "role": "user",
                    "content": (
                        "Start the psychiatric session. Greet the patient warmly and naturally, "
                        "then use && to add an open question at the end — e.g. "
                        "'Hello, I'm Dr. Aiden. I'm here to listen. && What brings you here today?'"
                    ),
                }
            ]
        
    def psychiatrist_response(self, context: list) -> LLM1Output:
        try:
            messages = [{"role": "system", "content": LLM1_SYSTEM_PROMPT}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            response = self._client().chat(
                model=self.model1,
                messages=messages,
                format=LLM1Output.model_json_schema(),
                options={"temperature": 0.6, "num_predict": 1024},
            )
            raw = response.message.content
            return LLM1Output.model_validate_json(raw)
        except Exception as e:
            print(f"[LLM1 ERROR] {e}")
            return LLM1Output(
                assistant_message="I'm here, and I'm listening. Please take your time. && Would you like to tell me more about what's on your mind?",
                intent="CONTINUE",
                risk_flag=False,
                clinical_summary=None
            )

    def internal_reasoning(self, context: list) -> LLM2Output:
        try:
            messages = [{"role": "system", "content": LLM2_SYSTEM_PROMPT}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            response = self._client().chat(
                model=self.model2,
                messages=messages,
                format=LLM2Output.model_json_schema(),
                options={"temperature": 0.1, "num_predict": 1024},
                keep_alive=0,
            )
            raw = response.message.content
            return LLM2Output.model_validate_json(raw)
        except Exception as e:
            print(f"[LLM2 ERROR] {e}")
            return LLM2Output(
                emotional_themes=[],
                thinking_patterns=[],
                behavioral_patterns=[],
                interpersonal_dynamics=[],
                stressors=[],
                unclear_areas=[],
                risk_assessment="Unable to complete risk assessment due to analysis error.",
                protective_factors=[]
            )

    def summarize_history(self, turns: list) -> str:
        if not turns:
            return ""
        try:
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
            response = self._client().chat(
                model=self.model1,
                messages=messages,
                options={"temperature": 0.3, "num_predict": 300},
            )
            return response.message.content.strip()
        except Exception as e:
            print(f"[SUMMARIZE ERROR] {e}")
            return "[Summary unavailable]"
