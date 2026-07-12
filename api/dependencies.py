"""
Dependency injection module for FastAPI.
Instantiates all infrastructure components (LLMs, Databases, STT) as singletons
and wires them into the core domain services (Orchestrator, PatientService).
Provides getter functions to inject these into FastAPI route handlers.
"""
import os
from dotenv import load_dotenv

from providers.ollama_llm_provider import OllamaLLMProvider
from providers.sensevoice_stt_provider import SenseVoiceSTTProvider
from providers.chroma_vector_store import ChromaVectorStore
from persistence.sqlite_memory_store import SQLiteMemoryStore
from providers.llm_risk_signal import LLMRiskSignal
from providers.clinical_risk_signal import ClinicalRiskSignal
from services.risk_assessment_service import RiskAssessmentService
from services.conversation_orchestrator import ConversationOrchestrator
from services.patient_service import PatientService
from core.ports import ProfileStore, SessionStore, AnalysisJobStore, STTProvider

load_dotenv()

OLLAMA_HOST          = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM1_MODEL           = os.getenv("LLM1_MODEL", "phi4-mini")
LLM2_MODEL           = os.getenv("LLM2_MODEL", "qwen2.5:7b-instruct")
EMBEDDING_MODEL      = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
CHROMA_PERSIST_DIR   = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION    = os.getenv("CHROMA_COLLECTION_NAME", "mhcva-knowledge")
MEMORY_DB_PATH       = os.getenv("MEMORY_DB_PATH", "./data/serinity.db")
WORKING_MEMORY_TURNS = int(os.getenv("WORKING_MEMORY_TURNS", "20"))

_hf_home_raw = os.getenv("HF_HOME", "./models")
if not os.path.isabs(_hf_home_raw):
    _hf_home_raw = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _hf_home_raw)
os.environ["HF_HOME"] = _hf_home_raw
os.makedirs(_hf_home_raw, exist_ok=True)

# Instantiate singleton infrastructure
llm_provider = OllamaLLMProvider(host=OLLAMA_HOST, model1=LLM1_MODEL, model2=LLM2_MODEL)
vector_store = ChromaVectorStore(
    host=OLLAMA_HOST,
    embedding_model=EMBEDDING_MODEL,
    persist_dir=CHROMA_PERSIST_DIR,
    collection_name=CHROMA_COLLECTION
)
memory_store = SQLiteMemoryStore(db_path=MEMORY_DB_PATH, working_memory_turns=WORKING_MEMORY_TURNS)
stt_provider = SenseVoiceSTTProvider()

# Instantiate Risk Service
risk_service = RiskAssessmentService([
    LLMRiskSignal(),
    ClinicalRiskSignal()
])

# Instantiate Domain Services
conversation_orchestrator = ConversationOrchestrator(
    llm_provider=llm_provider,
    vector_store=vector_store,
    session_store=memory_store,
    profile_store=memory_store,
    job_store=memory_store,
    risk_service=risk_service
)

patient_service = PatientService(
    profile_store=memory_store,
    session_store=memory_store,
    llm_provider=llm_provider
)

# FastAPI dependency injection functions
def get_orchestrator() -> ConversationOrchestrator:
    return conversation_orchestrator

def get_patient_service() -> PatientService:
    return patient_service

def get_stt_provider() -> STTProvider:
    return stt_provider

def get_memory_store() -> SQLiteMemoryStore:
    return memory_store

def get_profile_store() -> ProfileStore:
    return memory_store

def get_session_store() -> SessionStore:
    return memory_store

def get_job_store() -> AnalysisJobStore:
    return memory_store
