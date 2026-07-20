from pydantic import BaseModel, Field
from typing import Optional

class ResetRequest(BaseModel):
    """Payload for resetting an active session."""
    session_id: str
    patient_id: Optional[str] = None

class ChatRequest(BaseModel):
    """Payload for processing a user's text message."""
    message: str
    session_id: str
    emotion: Optional[str] = None
    patient_id: Optional[str] = None

class StartRequest(BaseModel):
    """Payload for initializing a new session."""
    patient_id: Optional[str] = None

class PatientCreateRequest(BaseModel):
    """Payload for creating a new patient record."""
    name: str
    age: Optional[int] = Field(None, ge=5, le=99)
    gender: Optional[str] = None
    occupation: Optional[str] = None
    primary_concern: Optional[str] = None

class EndSessionRequest(BaseModel):
    """Payload for gracefully terminating a session and generating a summary."""
    session_id: str
    patient_id: Optional[str] = None

class ChatResult(BaseModel):
    """Internal model encapsulating the orchestrator's response to a user message."""
    assistant_message: str
    intent: str
    risk_flagged: bool
    clinical_summary: Optional[str] = None
