from typing import Protocol, List, Optional, Any, Dict
from pydantic import BaseModel

class LLM1Output(BaseModel):
    """
    Data model representing the output of the conversational LLM (LLM1).
    Used to structure the immediate response sent to the patient.
    """
    assistant_message: str
    intent: str
    risk_flag: bool = False
    clinical_summary: Optional[str] = None
    search_query: Optional[str] = None

class LLM2Output(BaseModel):
    """
    Data model representing the output of the analytical LLM (LLM2).
    Used to structure the background psychological analysis of the patient's state.
    """
    assistant_message: str
    emotional_themes: List[str]
    thinking_patterns: List[str]
    behavioral_patterns: List[str]
    interpersonal_dynamics: List[str]
    stressors: List[str]
    unclear_areas: List[str]
    risk_assessment: str
    protective_factors: List[str]

class LLM3Output(BaseModel):
    """
    Data model representing the output of the post-session LLM (LLM3).
    Used for summarizing the session and merging the clinical profile.
    """
    session_summary: str
    update_profile: bool
    emotional_themes: List[str]
    thinking_patterns: List[str]
    behavioral_patterns: List[str]
    interpersonal_dynamics: List[str]
    stressors: List[str]
    unclear_areas: List[str]
    risk_assessment: str
    protective_factors: List[str]
    updated_primary_concern: Optional[str] = None

class RiskSignal(Protocol):
    """
    Protocol for evaluating patient messages against specific risk criteria 
    (e.g. self-harm, crisis). Multiple signals can be combined in the RiskAssessmentService.
    """
    def check(self, message: str, llm1_output: LLM1Output, llm2_output: Optional[LLM2Output] = None) -> bool:
        """Evaluate if there is a risk flag present in the current turn."""
        ...

class LLMProvider(Protocol):
    """
    Protocol defining the interface for connecting to Large Language Models.
    Abstracts away specific LLM implementations (e.g. Ollama, OpenAI) from the core logic.
    """
    def generate_opening_context(self, profile_recap: Optional[str]) -> list:
        """Generate the system/user prompt context for starting a session."""
        ...

    def psychiatrist_response(self, context: list, patient_info: dict = None, medium_term_memory: str | None = None) -> LLM1Output:
        """Generate a conversational response mimicking a psychiatrist (LLM1 fast path)."""
        ...

    def internal_reasoning(self, context: list, stable_prefix: str | None = None) -> LLM2Output:
        """Perform a deep psychological analysis of the conversation history (LLM2 slow path)."""
        ...
        
    def psychiatrist_query_response(self, context: list, retrieved_context: str) -> str:
        """Synthesize a final response to a user's query using retrieved clinical guidelines (LLM1 sync path)."""
        ...
        
    def generate_end_of_session_profile(self, old_profile: dict, session_history: list, patient_info: dict = None) -> 'LLM3Output':
        """Generate a concise session summary and fully merged clinical profile (LLM3 post-session path)."""
        ...



class STTProvider(Protocol):
    """
    Protocol for Speech-to-Text services.
    Abstracts audio transcription logic from the API layer.
    """
    def transcribe(self, audio_bytes: bytes) -> Dict[str, Any]:
        """Convert audio bytes to text and extract emotional metadata."""
        ...

class VectorStore(Protocol):
    """
    Protocol for semantic vector databases.
    Used for retrieving relevant psychological context or clinical guidelines.
    """
    def retrieve(self, query: str, k: int = 8) -> str:
        """Retrieve top semantic matches as a concatenated string."""
        ...

class SessionStore(Protocol):
    """
    Protocol for managing active conversational sessions.
    Responsible for tracking the immediate history and message context.
    """
    def create_session(self, patient_id: Optional[str] = None) -> str:
        """Initialize a new session and return the session ID."""
        ...
    def session_exists(self, session_id: str) -> bool:
        """Check if a session ID is currently active."""
        ...
    def append_message(self, session_id: str, role: str, content: str) -> None:
        """Add a new message (user or assistant) to the session history."""
        ...
    def get_working_context(self, session_id: str, llm_engine: Any = None) -> list:
        """Retrieve the formatted message history for the current session."""
        ...
    def save_session_summary(self, session_id: str, summary: str) -> None:
        """Persist the generated summary of the session when it ends."""
        ...
    def end_session(self, session_id: str) -> None:
        """Explicitly mark a session as ended, updating timestamps and setting is_active to 0."""
        ...
    def get_abandoned_sessions(self, timeout_minutes: int) -> list[str]:
        """Return a list of session IDs that have been inactive longer than timeout_minutes."""
        ...
    def get_patient_id(self, session_id: str) -> Optional[str]:
        """Lookup the associated patient ID for a given session."""
        ...
    def get_session_count(self, patient_id: str) -> int:
        """Get the total number of sessions for a given patient."""
        ...
        
    def get_active_session(self, patient_id: str) -> Optional[str]:
        ...
        
    def get_all_messages(self, session_id: str) -> list[dict]:
        ...

class ProfileStore(Protocol):
    """
    Protocol for managing long-term patient profiles.
    Responsible for storing demographic data, tracking past sessions, and updating psychological profiles.
    """
    def create_patient(self, name: str, age: Optional[int] = None) -> str:
        """Create a new patient record and return their ID."""
        ...
    def list_patients(self) -> list:
        """Return a list of all registered patients."""
        ...
    def get_patient(self, patient_id: str) -> dict:
        """Retrieve basic demographic info for a specific patient."""
        ...
    def get_patient_sessions(self, patient_id: str) -> list:
        """Retrieve a list of all past sessions for a patient."""
        ...
    def delete_patient(self, patient_id: str) -> None:
        """Delete all records associated with a patient."""
        ...
    def reset_patient_data(self, patient_id: str) -> None:
        """Delete sessions, messages, and profiles, but keep the patient record."""
        ...
    def update_patient_profile(self, patient_id: str, llm3_output: LLM3Output) -> None:
        """Merge final post-session insights into the patient's long-term dashboard profile."""
        ...
    def get_long_term_memory(self, patient_id: str) -> dict:
        """Retrieve the working long-term memory for the patient used by LLM1."""
        ...
    def update_long_term_memory(self, patient_id: str, llm2_output: LLM2Output) -> None:
        """Update the working long-term memory with mid-session LLM2 insights."""
        ...
    def get_patient_profile(self, patient_id: str) -> dict:
        """Retrieve the aggregated psychological profile of a patient."""
        ...
    def build_profile_recap(self, patient_id: str) -> Optional[str]:
        """Generate a concise text recap of the patient's profile for LLM context."""
        ...


