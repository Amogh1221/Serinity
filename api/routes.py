from fastapi import APIRouter, Depends, UploadFile, File, Request, Response, BackgroundTasks
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
    ConversationOrchestrator, PatientService
)
from core.ports import ProfileStore, SessionStore, STTProvider

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Removed hardcoded crisis string, handled by frontend now

@router.get("/health")
def health():
    """Simple health check endpoint to verify API is running."""
    return {"status": "ok"}

@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Serves the main frontend Single Page Application (SPA)."""
    return templates.TemplateResponse(request, "index.html")

@router.get("/patients")
def get_patients(profile_store: ProfileStore = Depends(get_profile_store)):
    """Retrieve a list of all registered patients."""
    return profile_store.list_patients()

@router.post("/patients/create")
def create_new_patient(
    request: PatientCreateRequest, 
    profile_store: ProfileStore = Depends(get_profile_store)
):
    """Create a new patient record in the database."""
    p_id = profile_store.create_patient(
        name=request.name, 
        age=request.age,
        gender=request.gender,
        occupation=request.occupation,
        primary_concern=request.primary_concern
    )
    return {"patient_id": p_id, "name": request.name}

@router.get("/patients/{patient_id}/dashboard")
def patient_dashboard(
    patient_id: str, 
    profile_store: ProfileStore = Depends(get_profile_store)
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
    patient_service: PatientService = Depends(get_patient_service)
):
    """Reset the patient's data, including sessions, messages, and profile."""
    patient_service.reset_patient_data(patient_id)
    return {"status": "success", "message": "Patient data reset successfully."}

@router.delete("/patients/{patient_id}")
def delete_patient(
    patient_id: str,
    patient_service: PatientService = Depends(get_patient_service)
):
    """Delete a patient and all their associated data completely."""
    patient_service.delete_patient(patient_id)
    return {"status": "success", "message": "Patient deleted successfully."}

@router.post("/end_session")
def end_session_endpoint(
    request: EndSessionRequest, 
    background_tasks: BackgroundTasks,
    patient_service: PatientService = Depends(get_patient_service)
):
    """Gracefully terminate an active session and generate a clinical summary in the background."""
    patient_service.end_session(request.session_id, request.patient_id)
    background_tasks.add_task(patient_service.generate_session_summary, request.session_id, request.patient_id)
    return {"status": "ended"}

@router.post("/start")
def start_session(
    request: StartRequest = StartRequest(), 
    patient_service: PatientService = Depends(get_patient_service)
):
    """Initialize a new conversation session and generate the psychiatrist's opening remark."""
    session_id, opening_message, patient_id = patient_service.create_new_session(request.patient_id)
    return {
        "assistant_message": opening_message,
        "session_id":        session_id,
        "patient_id":        patient_id,
    }


@router.post("/chat_text")
def chat_text(
    request: ChatRequest, 
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    patient_service: PatientService = Depends(get_patient_service),
    session_store: SessionStore = Depends(get_session_store),
    profile_store: ProfileStore = Depends(get_profile_store)
):
    """
    Process a user's chat message through the core orchestrator.
    LLM2 analysis is run synchronously within the orchestrator if triggered.
    """
    if not session_store.session_exists(request.session_id):
        session_id, opening_message, patient_id = patient_service.create_new_session(request.patient_id)
        return {
            "assistant_message": opening_message,
            "session_id":        session_id,
            "patient_id":        patient_id,
            "intent":            "CONTINUE",
        }

    chat_result = orchestrator.handle_message(
        session_id=request.session_id,
        message=request.message,
        emotion=request.emotion,
        default_patient_id=request.patient_id
    )


    return {
        "assistant_message": chat_result.assistant_message,
        "intent":            chat_result.intent,
        "risk_flagged":      chat_result.risk_flagged,
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
    result = stt_provider.transcribe(audio_bytes)
    return {
        "text":    result.get("text",    ""),
        "emotion": result.get("emotion", "unknown"),
        "event":   result.get("event",   None),
    }

@router.get("/{full_path:path}", response_class=HTMLResponse)
def catch_all(request: Request, full_path: str):
    """
    Catch-all route to support History API (clean URLs) in the frontend SPA.
    If the user navigates directly to /profiles or /dashboard, serve index.html
    so the frontend JS can handle the routing.
    """
    return templates.TemplateResponse(request, "index.html")
