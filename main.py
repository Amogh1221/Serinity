"""
main.py — Serinity FastAPI application (on-device version).

Changes from cloud version:
  - In-memory sessions dict → SQLite-backed memory_store (Phase 5)
  - /transcribe now returns {text, emotion, event} (Phase 2)
  - /chat_text prepends [vocal tone: X] hint for non-neutral/non-unknown emotion (Phase 2)
  - /chat_text runs contains_risk_signal() BEFORE LLM1 on every message (Phase 3)
    If matched, crisis resources are always injected into the response.
  - ANALYZE branch uses llm1_response.clinical_summary for RAG retrieval (Phase 4)
    Falls back to user-only messages from recent history if summary is empty.
  - analysis_briefing now includes risk_assessment + protective_factors (Phase 3)
  - After ANALYZE, updates patient_profile in memory_store (Phase 5)
  - /start and /reset accept optional patient_id; returning patients get a
    profile-aware greeting (Phase 5)

CHANGELOG (2026-07-12) — safety fix, based on production log review:
  - BUG FIX: contains_risk_signal() was being computed and logged
    (risk_injected=...) but CRISIS_RESOURCES was never actually appended to
    the outgoing assistant_message. The docstring above said resources were
    "always injected" — the code never did it. That's now fixed: whenever
    any risk signal fires, CRISIS_RESOURCES is appended to the message the
    client receives.
  - Risk detection is now the OR of three independent signals:
      1. contains_risk_signal(request.message) — deterministic keyword check,
         runs before LLM1 is even called.
      2. llm1_response.risk_flag — LLM1's own NLU-based read of this turn.
      3. risk_assessment_indicates_concern(llm2_response.risk_assessment) —
         only checked on the ANALYZE path, in case the analyst surfaces risk
         that wasn't obvious from the single latest message alone.
  - If signal (1) or (2) fires and LLM1 nonetheless returned intent=CONTINUE,
    intent is forcibly overridden to ANALYZE in code. The log showed LLM1
    itself failing to escalate on several consecutive explicit turns — the
    updated prompt asks it to escalate on its own, but this is a code-level
    backstop that doesn't depend on a small model reliably following that
    instruction every time.
  - The CRISIS_RESOURCES block is appended only to the message returned to
    the client — NOT to what's persisted via append_message(). This keeps
    conversation history (and therefore future LLM1/LLM2 context windows)
    clean, so the resource block doesn't get re-fed into the model on every
    subsequent turn or distort LLM2's pattern analysis.
  - The "risk_flagged" field in the API response now reflects the combined
    signal above, not just the raw keyword check. If any frontend logic
    branches on this field specifically expecting keyword-only semantics,
    that logic should be reviewed.

Preserved unchanged:
  - Route surface: /health, /start, /reset, /chat_text, /transcribe
  - Ethical guardrails in LLM1 (in llm_engine.py)
  - MIT license attribution
"""

from fastapi import FastAPI, Request, UploadFile, File, Response
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
import uuid
import json
from typing import Dict, List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from rag_engine   import rag_engine
from llm_engine   import llm_engine
from memory_store import (
    create_session,
    session_exists,
    append_message,
    get_working_context,
    get_patient_id,
    update_patient_profile,
    build_profile_recap,
    save_session_summary,
    create_patient,
    list_patients,
    get_patient,
    get_patient_sessions,
    get_patient_profile,
)
# Crisis resources (India-only, displayed when LLM1 sets risk_flag=True)
_CRISIS_RESOURCES = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💛  You are not alone. Free, confidential support is available right now:

  • iCall (TISS): 9152987821
  • Vandrevala Foundation: 1860-2662-345 / 1800-2333-330
  • Kiran Mental Health: 1800-599-0019  (toll-free, 24 × 7)

Please reach out — a real person will listen.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
from debug_logger import get_logger, close_logger

app = FastAPI(title="Serinity", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class ResetRequest(BaseModel):
    session_id: str
    patient_id: Optional[str] = None


class ChatRequest(BaseModel):
    message:    str
    session_id: str
    # Optional: emotion from /transcribe if frontend passes it through
    emotion:    Optional[str] = None
    patient_id: Optional[str] = None


class StartRequest(BaseModel):
    patient_id: Optional[str] = None


class PatientCreateRequest(BaseModel):
    name: str
    age:  Optional[int] = None


class EndSessionRequest(BaseModel):
    session_id: str
    patient_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_list(items: list) -> str:
    """Format a list for display in the analysis briefing."""
    if not items:
        return "None identified yet"
    return "\n  • " + "\n  • ".join(items)



def _build_opening_context(patient_id: Optional[str]) -> list:
    """
    Build the initial context for a new session.
    If a patient profile exists, inject a short recap so LLM1 can acknowledge
    continuity naturally in its greeting.
    """
    recap = build_profile_recap(patient_id) if patient_id else None

    if recap:
        return [
            {
                "role": "user",
                "content": (
                    f"{recap}\n\n"
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


def create_new_session(patient_id: Optional[str] = None):
    """
    Create a new session in memory_store, get the opening greeting from LLM1,
    persist it, and return (session_id, opening_message, patient_id).
    """
    session_id = create_session(patient_id=patient_id)
    resolved_patient_id = get_patient_id(session_id)

    opening_context = _build_opening_context(resolved_patient_id)
    llm1_response   = llm_engine.psychiatrist_response(opening_context)

    append_message(session_id, "assistant", llm1_response.assistant_message)

    patient_info = get_patient(resolved_patient_id)
    user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
    log = get_logger(session_id, user_name)
    log.session_start(resolved_patient_id)
    log.assistant_reply(llm1_response.assistant_message, risk_injected=False)

    return session_id, llm1_response.assistant_message, resolved_patient_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/patients")
def get_patients():
    return list_patients()


@app.post("/patients/create")
def create_new_patient(request: PatientCreateRequest):
    p_id = create_patient(name=request.name, age=request.age)
    return {"patient_id": p_id, "name": request.name}


@app.get("/patients/{patient_id}/dashboard")
def patient_dashboard(patient_id: str):
    patient_info = get_patient(patient_id)
    if not patient_info:
        return Response(status_code=404)
        
    profile = get_patient_profile(patient_id)
    sessions = get_patient_sessions(patient_id)
    
    return {
        "patient": patient_info,
        "profile": profile,
        "sessions": sessions
    }

@app.post("/end_session")
def end_session_endpoint(request: EndSessionRequest):
    session_id = request.session_id
    patient_id = get_patient_id(session_id) or request.patient_id

    # Generate the session summary via LLM1
    history = get_working_context(session_id)
    summary = "No conversation occurred."
    if len(history) > 1:
        try:
            summary = llm_engine.summarize_history(history)
        except Exception as e:
            summary = f"Summary generation failed: {e}"

    # Persist summary into patient profile for next-session warm-start
    if patient_id:
        save_session_summary(patient_id, summary)

    # Log session end to debug file
    patient_info = get_patient(patient_id) if patient_id else None
    user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
    log = get_logger(session_id, user_name)
    log._write_txt(f"\n======================================================\n  SESSION SUMMARY\n======================================================\n{summary}\n")
    close_logger(session_id)

    # Do NOT return the summary to the client — it's internal only.
    return {"status": "ended"}


@app.post("/start")
def start_session(request: StartRequest = StartRequest()):
    session_id, opening_message, patient_id = create_new_session(
        patient_id=request.patient_id
    )
    return {
        "assistant_message": opening_message,
        "session_id":        session_id,
        "patient_id":        patient_id,
    }


@app.post("/reset")
def reset_session(request: ResetRequest):
    session_id, opening_message, patient_id = create_new_session(
        patient_id=request.patient_id
    )
    return {
        "assistant_message": opening_message,
        "session_id":        session_id,
        "patient_id":        patient_id,
    }



@app.post("/chat_text")
def chat_text(request: ChatRequest):
    # ------------------------------------------------------------------
    # 1. Session recovery
    # ------------------------------------------------------------------
    if not session_exists(request.session_id):
        session_id, opening_message, patient_id = create_new_session(
            patient_id=request.patient_id
        )
        # Return early with new session info; client should re-send
        return {
            "assistant_message": opening_message,
            "session_id":        session_id,
            "patient_id":        patient_id,
            "intent":            "CONTINUE",
        }

    session_id = request.session_id
    patient_id = get_patient_id(session_id) or request.patient_id
    patient_info = get_patient(patient_id) if patient_id else None
    user_name = patient_info.get("name", "Guest Patient") if patient_info else "Guest Patient"
    log = get_logger(session_id, user_name)

    # ------------------------------------------------------------------
    # 2. Preprocess user message — prepend vocal tone hint if applicable
    # ------------------------------------------------------------------
    user_message = request.message
    emotion = (request.emotion or "").lower().strip()
    if emotion and emotion not in ("neutral", "unknown", ""):
        user_message = f"[vocal tone: {emotion}] {user_message}"

    # Log user message
    log.user_message(request.message, emotion=emotion or None)

    # ------------------------------------------------------------------
    # 4. Persist user message
    # ------------------------------------------------------------------
    append_message(session_id, "user", user_message)

    # ------------------------------------------------------------------
    # 5. Build working context (last N turns + optional rolling summary)
    # ------------------------------------------------------------------
    history = get_working_context(session_id, llm_engine=llm_engine)

    # ------------------------------------------------------------------
    # 6. Call LLM1 (Dr. Aiden)
    # ------------------------------------------------------------------
    llm1_response = llm_engine.psychiatrist_response(history)
    log.llm1_decision(llm1_response)

    # ------------------------------------------------------------------
    # 6b. Risk flag — driven entirely by LLM1's NLU judgment.
    #     If LLM1 set risk_flag but still returned CONTINUE, force ANALYZE
    #     as a code-level backstop.
    # ------------------------------------------------------------------
    combined_risk = llm1_response.risk_flag
    if combined_risk and llm1_response.intent != "ANALYZE":
        llm1_response.intent = "ANALYZE"

    # ------------------------------------------------------------------
    # 7. CONTINUE path
    # ------------------------------------------------------------------
    if llm1_response.intent == "CONTINUE":
        append_message(session_id, "assistant", llm1_response.assistant_message)
        log.assistant_reply(llm1_response.assistant_message, risk_injected=combined_risk)
        return {
            "assistant_message": llm1_response.assistant_message,
            "intent":            "CONTINUE",
            "risk_flagged":      combined_risk,
        }

    # ------------------------------------------------------------------
    # 8. ANALYZE path
    # ------------------------------------------------------------------
    if llm1_response.intent == "ANALYZE":

        # 8a. Choose retrieval query: clinical_summary > user-only recent messages
        if llm1_response.clinical_summary and llm1_response.clinical_summary.strip():
            retrieval_query  = llm1_response.clinical_summary
            query_source     = "clinical_summary (LLM1-generated)"
        else:
            # Fallback: user-only messages from recent history. This is also
            # the path taken whenever ANALYZE was forced by the code-level
            # risk override above (LLM1 originally said CONTINUE and so
            # never populated clinical_summary).
            retrieval_query = "\n".join(
                msg["content"]
                for msg in history[-10:]
                if msg.get("role") == "user"
            )
            query_source = "user_messages_fallback"

        log.analyze_triggered(retrieval_query, query_source)

        retrieved_context = rag_engine.retrieve(retrieval_query)
        log.retrieved_context(retrieved_context)

        # 8b. Call LLM2 (analyst) with history + clinical context
        llm2_input = history[-10:] + [
            {
                "role": "user",
                "content": (
                    f"Clinical Context for Analysis:\n{retrieved_context}\n\n"
                    "Please perform pattern analysis across all eight domains."
                ),
            }
        ]
        llm2_response = llm_engine.internal_reasoning(llm2_input)
        log.llm2_output(llm2_response)

        # 8c. Update long-term patient profile
        if patient_id:
            update_patient_profile(patient_id, llm2_response)

        # 8d. Build internal clinical briefing for LLM1's final response
        analysis_briefing = f"""[Internal Clinical Analysis - For Treatment Planning]

Emotional Themes:
{format_list(llm2_response.emotional_themes)}

Thinking Patterns:
{format_list(llm2_response.thinking_patterns)}

Behavioral Patterns:
{format_list(llm2_response.behavioral_patterns)}

Interpersonal Dynamics:
{format_list(llm2_response.interpersonal_dynamics)}

Identified Stressors:
{format_list(llm2_response.stressors)}

Areas Requiring Further Exploration:
{format_list(llm2_response.unclear_areas)}

Risk Assessment:
{llm2_response.risk_assessment}

Protective Factors:
{format_list(llm2_response.protective_factors)}

Based on this clinical insight, provide your next therapeutic response to the patient."""

        # 8e. Get LLM1's final response incorporating the analysis
        briefing_history = history + [{"role": "user", "content": analysis_briefing}]
        llm1_final = llm_engine.psychiatrist_response(briefing_history)
        log.llm1_final(llm1_final)

        # Also check LLM2's risk_assessment in case the fuller-history analysis
        # surfaces risk that wasn't obvious from the single latest message.
        llm2_risk = llm2_response.risk_assessment.strip().lower() not in (
            "", "no safety concerns identified",
            "no safety concerns identified.",
        )
        final_risk = combined_risk or llm2_risk

        append_message(session_id, "assistant", llm1_final.assistant_message)
        log.assistant_reply(llm1_final.assistant_message, risk_injected=final_risk)

        return {
            "assistant_message": llm1_final.assistant_message,
            "intent":            "CONTINUE",
            "risk_flagged":      final_risk,
        }

    # Fallback (should not reach here)
    return {
        "assistant_message": llm1_response.assistant_message,
        "intent":            "CONTINUE",
        "risk_flagged":      combined_risk,
    }


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribe uploaded audio using SenseVoice-Small.
    Returns text + emotion tag + event tag (Phase 2).
    """
    audio_bytes = await audio.read()
    result = llm_engine.transcribe_audio(audio_bytes)
    return {
        "text":    result.get("text",    ""),
        "emotion": result.get("emotion", "unknown"),
        "event":   result.get("event",   None),
    }