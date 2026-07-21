"""
Dependency injection module for FastAPI.
Instantiates all infrastructure components (LLMs, Databases, STT) as singletons
and wires them into the core domain services (Orchestrator, PatientService).
Provides getter functions to inject these into FastAPI route handlers.
"""
import os
from dotenv import load_dotenv

from providers.llms.groq_llm_provider import GroqLLMProvider
from providers.llms.ollama_llm_provider import OllamaLLMProvider
from providers.llms.huggingface_llm_provider import HuggingFaceLLMProvider
from providers.llms.fallback_llm_provider import FallbackLLMProvider
from providers.speech_to_text_provider import SenseVoiceSTTProvider
from providers.chroma_provider import ChromaVectorStore
from providers.pinecone_provider import PineconeVectorStore
from persistence.sqlite_memory_store import SQLiteProfileStore, SQLiteSessionStore
from persistence.user_store import SQLiteUserStore

# Safety/Risk Signals
from providers.safety.llm import LLMRiskSignal
from providers.safety.clinical import ClinicalRiskSignal

# Uncomment if using Cascade
# from core.ports import SafetySignal
from providers.safety.bert import BertRiskSignal
from providers.safety.keyword import KeywordRiskSignal
from providers.safety.cascade import CascadeRiskSignal
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from services.auth_service import decode_access_token
from services.risk_assessment_service import RiskAssessmentService
from services.conversation_orchestrator import ConversationOrchestrator
from services.patient_service import PatientService
from core.ports import ProfileStore, SessionStore, STTProvider, LLMProvider, VectorStore

load_dotenv()

OLLAMA_HOST          = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_LLM1_MODEL    = os.getenv("OLLAMA_LLM1_MODEL", "phi4-mini")
OLLAMA_LLM2_MODEL    = os.getenv("OLLAMA_LLM2_MODEL", "qwen2.5:7b-instruct")
GROQ_LLM1_MODEL      = os.getenv("GROQ_LLM1_MODEL", "llama-3.1-8b-instant")
GROQ_LLM2_MODEL           = os.getenv("GROQ_LLM2_MODEL", "llama-3.3-70b-versatile")
EMBEDDING_MODEL      = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
CHROMA_PERSIST_DIR   = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION    = os.getenv("CHROMA_COLLECTION_NAME", "mhcva-knowledge")
VECTOR_STORE_TYPE    = os.getenv("VECTOR_STORE_TYPE", "chroma").lower()
PINECONE_API_KEY     = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME  = os.getenv("PINECONE_INDEX_NAME", "serinity-knowledge")
MEMORY_DB_PATH       = os.getenv("MEMORY_DB_PATH", "./data/serinity.db")
WORKING_MEMORY_TURNS = int(os.getenv("WORKING_MEMORY_TURNS", "20"))
CLOUD_MODE           = os.getenv("CLOUD_MODE", "false").lower() == "true"
# LLM_PROVIDER selects the cloud backend when CLOUD_MODE=true.
# Options: "groq" (default) | "hf" (HuggingFace Serverless Inference API)
LLM_PROVIDER         = os.getenv("LLM_PROVIDER", "groq").lower()
HF_LLM1_MODEL        = os.getenv("HF_LLM1_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
HF_LLM2_MODEL        = os.getenv("HF_LLM2_MODEL", "meta-llama/Llama-3.3-70B-Instruct")

_hf_home_raw = os.getenv("HF_HOME", "./models")
if not os.path.isabs(_hf_home_raw):
    _hf_home_raw = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), _hf_home_raw)
os.environ["HF_HOME"] = _hf_home_raw
os.makedirs(_hf_home_raw, exist_ok=True)

# Instantiate singleton infrastructure
ollama_provider = OllamaLLMProvider(host=OLLAMA_HOST, model1=OLLAMA_LLM1_MODEL, model2=OLLAMA_LLM2_MODEL)

if CLOUD_MODE:
    if LLM_PROVIDER == "hf":
        _cloud_provider = HuggingFaceLLMProvider(model1=HF_LLM1_MODEL, model2=HF_LLM2_MODEL)
        print(f"[STARTUP] LLM backend: HuggingFace ({HF_LLM1_MODEL} / {HF_LLM2_MODEL})")
    else:
        _cloud_provider = GroqLLMProvider(model1=GROQ_LLM1_MODEL, model2=GROQ_LLM2_MODEL)
        print(f"[STARTUP] LLM backend: Groq ({GROQ_LLM1_MODEL} / {GROQ_LLM2_MODEL})")
    llm_provider = FallbackLLMProvider(providers=[_cloud_provider])
    vector_store = PineconeVectorStore(
        host=OLLAMA_HOST,
        embedding_model=EMBEDDING_MODEL,
        index_name=PINECONE_INDEX_NAME,
        api_key=PINECONE_API_KEY
    )
else:
    llm_provider = FallbackLLMProvider(providers=[ollama_provider])
    vector_store = ChromaVectorStore(
        host=OLLAMA_HOST,
        embedding_model=EMBEDDING_MODEL,
        persist_dir=CHROMA_PERSIST_DIR,
        collection_name=CHROMA_COLLECTION
    )
profile_store = SQLiteProfileStore(db_path=MEMORY_DB_PATH)
session_store = SQLiteSessionStore(db_path=MEMORY_DB_PATH, working_memory_turns=WORKING_MEMORY_TURNS)
user_store = SQLiteUserStore(db_path=MEMORY_DB_PATH)

stt_provider = SenseVoiceSTTProvider()

# Setup DI dependencies for FastAPI routes
def get_llm_provider() -> FallbackLLMProvider:
    return llm_provider

def get_vector_store():
    return vector_store

def get_profile_store() -> SQLiteProfileStore:
    return profile_store

def get_session_store() -> SQLiteSessionStore:
    return session_store
    
def get_user_store() -> SQLiteUserStore:
    return user_store

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), store: SQLiteUserStore = Depends(get_user_store)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception
        
    user = store.get_user_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user

# Instantiate Risk Service
risk_service = RiskAssessmentService([
    CascadeRiskSignal(
        filter_signal=KeywordRiskSignal(),
        verify_signal=BertRiskSignal()
    ),
    LLMRiskSignal(),
    ClinicalRiskSignal()
])

# Instantiate Domain Services
conversation_orchestrator = ConversationOrchestrator(
    llm_provider=llm_provider,
    vector_store=vector_store,
    session_store=session_store,
    profile_store=profile_store,
    risk_service=risk_service
)

patient_service = PatientService(
    profile_store=profile_store,
    session_store=session_store,
    llm_provider=llm_provider
)

# FastAPI dependency injection functions
def get_orchestrator(
    llm_provider: LLMProvider = Depends(get_llm_provider),
    vector_store: VectorStore = Depends(get_vector_store),
    session_store: SessionStore = Depends(get_session_store),
    profile_store: ProfileStore = Depends(get_profile_store)
) -> ConversationOrchestrator:
    return ConversationOrchestrator(
        llm_provider=llm_provider,
        vector_store=vector_store,
        session_store=session_store,
        profile_store=profile_store,
        risk_service=risk_service
    )

def get_patient_service(
    profile_store: ProfileStore = Depends(get_profile_store),
    session_store: SessionStore = Depends(get_session_store),
    llm_provider: LLMProvider = Depends(get_llm_provider)
) -> PatientService:
    return PatientService(
        profile_store=profile_store,
        session_store=session_store,
        llm_provider=llm_provider
    )

def get_stt_provider() -> STTProvider:
    return stt_provider

def get_profile_store() -> ProfileStore:
    return profile_store

def get_session_store() -> SessionStore:
    return session_store
