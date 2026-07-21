"""
Main API Routes
Handles patient management, dashboard, and conversation endpoints.
"""

from fastapi import APIRouter, Depends, UploadFile, File, Request, Response, BackgroundTasks, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.schemas import (
    ResetRequest, ChatRequest, StartRequest, 
    PatientCreateRequest, EndSessionRequest
)
from api.dependencies import (
    get_orchestrator, get_patient_service, 
    get_stt_provider, get_profile_store, get_session_store,
    get_current_user,
    ConversationOrchestrator, PatientService
)
from core.ports import ProfileStore, SessionStore, STTProvider

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/health")
def health():
    """Simple health check endpoint to verify API is running."""
    return {"status": "ok"}

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Serves the main frontend Single Page Application (SPA)."""
    return templates.TemplateResponse(request, "index.html")



@router.get("/patients")
def get_patients(profile_store: ProfileStore = Depends(get_profile_store), user: dict = Depends(get_current_user)):
    """Retrieve a list of all registered patients for the logged-in user."""
    patients = profile_store.list_patients_for_user(user["id"])
    if not patients:
        # Auto-create a default profile for older accounts that lack one
        patient_id = profile_store.create_patient(
            name=user.get("username", "User"),
            age=None,
            gender=None,
            primary_concern=None,
            user_id=user["id"]
        )
        return [{"patient_id": patient_id, "name": user.get("username", "User")}]
    return patients

@router.post("/patients/create")
def create_new_patient(
    request: PatientCreateRequest, 
    profile_store: ProfileStore = Depends(get_profile_store),
    user: dict = Depends(get_current_user)
):
    """Create a new patient record in the database."""
    p_id = profile_store.create_patient(
        name=request.name, 
        age=request.age,
        gender=request.gender,
        occupation=request.occupation,
        primary_concern=request.primary_concern,
        user_id=user["id"]
    )
    return {"patient_id": p_id, "name": request.name}

@router.get("/patients/{patient_id}/dashboard")
def patient_dashboard(
    patient_id: str, 
    profile_store: ProfileStore = Depends(get_profile_store),
    user: dict = Depends(get_current_user)
):
    """Retrieve full dashboard data for a patient (info, profile, past sessions)."""
    patient_info = profile_store.get_patient(patient_id)
    if not patient_info:
        return Response(status_code=404)
        
    profile = profile_store.get_patient_profile(patient_id)
    sessions = profile_store.get_patient_sessions(patient_id)
    
    return {
        "patient": patient_info,
        "profile": profile,
        "sessions": sessions
    }

@router.post("/patients/{patient_id}/reset")
def reset_patient(
    patient_id: str,
    patient_service: PatientService = Depends(get_patient_service),
    user: dict = Depends(get_current_user)
):
    """Reset the patient's data, including sessions, messages, and profile."""
    patient_service.reset_patient_data(patient_id)
    return {"status": "success", "message": "Patient data reset successfully."}

@router.delete("/patients/{patient_id}")
def delete_patient(
    patient_id: str,
    patient_service: PatientService = Depends(get_patient_service),
    user: dict = Depends(get_current_user)
):
    """Delete a patient and all their associated data completely."""
    patient_service.delete_patient(patient_id)
    return {"status": "success", "message": "Patient deleted successfully."}

@router.post("/end_session")
def end_session_endpoint(
    request: EndSessionRequest, 
    background_tasks: BackgroundTasks,
    patient_service: PatientService = Depends(get_patient_service),
    user: dict = Depends(get_current_user)
):
    """Gracefully terminate an active session and generate a clinical summary in the background."""
    patient_service.end_session(request.session_id, request.patient_id)
    background_tasks.add_task(patient_service.generate_session_summary, request.session_id, request.patient_id)
    return {"status": "ended"}

@router.post("/start")
def start_session(
    request: StartRequest = StartRequest(), 
    patient_service: PatientService = Depends(get_patient_service),
    user: dict = Depends(get_current_user)
):
    """Initialize a new conversation session and generate the psychiatrist's opening remark."""
    try:
        session_id, opening_message, patient_id = patient_service.create_new_session(request.patient_id)
        return {
            "assistant_message": opening_message,
            "session_id":        session_id,
            "patient_id":        patient_id,
        }
    except Exception as e:
        error_str = str(e).lower()
        if "connection error" in error_str or "all providers failed" in error_str or "unavailable" in error_str:
            raise HTTPException(status_code=503, detail="LLMs are currently unavailable. Cannot start session.")
        raise e


@router.post("/chat_text")
def chat_text(
    request: ChatRequest, 
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    patient_service: PatientService = Depends(get_patient_service),
    session_store: SessionStore = Depends(get_session_store),
    profile_store: ProfileStore = Depends(get_profile_store),
    user: dict = Depends(get_current_user)
):
    """
    Process a user's chat message through the core orchestrator.
    LLM2 analysis is run synchronously within the orchestrator if triggered.
    """
    if not session_store.session_exists(request.session_id):
        # Session expired, create a new one
        session_id, opening_message, patient_id = patient_service.create_new_session(request.patient_id)
        # Instead of dropping the user's message and returning the greeting, pipe the user's message into the new session
        request.session_id = session_id
        request.patient_id = patient_id

    try:
        chat_result = orchestrator.handle_message(
            session_id=request.session_id,
            message=request.message,
            emotion=request.emotion,
            default_patient_id=request.patient_id
        )
    except Exception as e:
        error_str = str(e).lower()
        error_type = type(e).__name__.lower()
        if any(k in error_str for k in ("rate limit", "ratelimit", "429", "402", "tokens exhausted", "quota")) or "ratelimit" in error_type:
            raise HTTPException(status_code=429, detail="Tokens Exhausted")
        if "connection error" in error_str or "all providers failed" in error_str or "unavailable" in error_str:
            raise HTTPException(status_code=503, detail="LLMs are currently unavailable. Please try again later.")
        raise e


    return {
        "assistant_message": chat_result.assistant_message,
        "intent":            chat_result.intent,
        "risk_flagged":      chat_result.risk_flagged,
        "session_id":        request.session_id,
    }

@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...), 
    stt_provider: STTProvider = Depends(get_stt_provider)
):
    """
    Accepts raw audio bytes from the frontend and passes them to the STTProvider
    for speech-to-text and emotional tone extraction.
    """
    audio_bytes = await audio.read()
    # Run the CPU-bound transcription in a threadpool to prevent blocking the async event loop
    result = await run_in_threadpool(stt_provider.transcribe, audio_bytes)
    return {
        "text":    result.get("text",    ""),
        "emotion": result.get("emotion", "unknown"),
        "event":   result.get("event",   None),
    }

@router.get("/patients/{patient_id}/active_session")
def get_active_session(
    patient_id: str,
    patient_service: PatientService = Depends(get_patient_service),
    user: dict = Depends(get_current_user)
):
    """Check if the patient currently has an active session."""
    session_id = patient_service.get_active_session(patient_id)
    return {"session_id": session_id}

@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str,
    patient_service: PatientService = Depends(get_patient_service),
    user: dict = Depends(get_current_user)
):
    """Retrieve all raw messages for a given session to continue a chat."""
    messages = patient_service.get_session_messages(session_id)
    return {"messages": messages}

_BLOCKED_PATH_FRAGMENTS = {
    ".streamlit", ".env", "secrets.toml", "config.toml", ".git", "wp-admin", ".well-known"
}

@router.get("/{full_path:path}", response_class=HTMLResponse)
def catch_all(request: Request, full_path: str):
    """
    Catch-all route to support History API (clean URLs) in the frontend SPA.
    Returns 404 for known config/secret paths probed by bots (e.g. .streamlit/secrets.toml).
    Otherwise serves index.html so the frontend JS handles SPA routing.
    """
    if any(fragment in full_path for fragment in _BLOCKED_PATH_FRAGMENTS):
        return Response(status_code=404)
    return templates.TemplateResponse(request, "index.html")
