import os
import threading
import ollama
from core.ports import LLM1Output, LLM2Output, LLM3Output
from core.prompts import LLM1_SYSTEM_PROMPT, LLM2_SYSTEM_PROMPT, LLM3_SYSTEM_PROMPT

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
        # Global lock to queue requests and prevent CUDA out-of-memory errors
        self._llm_lock = threading.Lock()
        
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
        
    def psychiatrist_response(self, context: list, patient_info: dict = None, medium_term_memory: str | None = None) -> LLM1Output:
        try:
            sys_prompt = LLM1_SYSTEM_PROMPT
            stable_parts = []
            if patient_info:
                stable_parts.append(
                    f"PATIENT DEMOGRAPHICS:\n"
                    f"- Name: {patient_info.get('name', 'Unknown')}\n"
                    f"- Age: {patient_info.get('age', 'Unknown')}\n"
                    f"- Gender: {patient_info.get('gender', 'Unknown')}\n"
                    f"- Nationality: {patient_info.get('nationality', 'Unknown')}\n"
                    f"- Primary Concern: {patient_info.get('primary_concern', 'Unknown')}"
                )
            if medium_term_memory:
                stable_parts.append(
                    f"PATIENT MEDIUM-TERM MEMORY (prior sessions & patterns — do not quote verbatim):\n"
                    f"{medium_term_memory}"
                )
            if stable_parts:
                sys_prompt = "\n\n".join(stable_parts) + "\n\n" + sys_prompt

            messages = [{"role": "system", "content": sys_prompt}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            with self._llm_lock:
                response = self._client().chat(
                    model=self.model1,
                    messages=messages,
                    format=LLM1Output.model_json_schema(),
                    options={"temperature": 0.6, "num_predict": 1024, "num_ctx": 8192},
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

    def internal_reasoning(self, context: list, stable_prefix: str | None = None) -> LLM2Output:
        try:
            messages = [{"role": "system", "content": LLM2_SYSTEM_PROMPT}]
            # For Ollama there is no caching concept; merge stable_prefix as a user message
            if stable_prefix:
                messages.append({"role": "user", "content": stable_prefix})
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            with self._llm_lock:
                response = self._client().chat(
                    model=self.model2,
                    messages=messages,
                    format=LLM2Output.model_json_schema(),
                    options={"temperature": 0.1, "num_predict": 1024, "num_ctx": 8192},
                    keep_alive=0,
                )
            raw = response.message.content
            return LLM2Output.model_validate_json(raw)
        except Exception as e:
            print(f"[LLM2 ERROR] {e}")
            return LLM2Output(
                assistant_message="I'm here, taking everything in. Please go on.",
                emotional_themes=[],
                thinking_patterns=[],
                behavioral_patterns=[],
                interpersonal_dynamics=[],
                stressors=[],
                unclear_areas=[],
                risk_assessment="Unable to complete risk assessment due to analysis error.",
                protective_factors=[]
            )

    def psychiatrist_query_response(self, context: list, retrieved_context: str) -> str:
        try:
            sys_prompt = (
                "You are a compassionate AI psychiatrist. The patient has asked for advice. "
                "Synthesize a thoughtful response using the following clinical guidelines:\n\n"
                f"{retrieved_context}\n\n"
                "Keep your response empathetic, natural, and under 4 sentences. Do not use markdown."
            )
            messages = [{"role": "system", "content": sys_prompt}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            with self._llm_lock:
                response = self._client().chat(
                    model=self.model1,
                    messages=messages,
                    options={"temperature": 0.5, "num_predict": 512, "num_ctx": 8192},
                )
            return response.message.content.strip()
        except Exception as e:
            print(f"[QUERY ERROR] {e}")
            return "I hear you, and we will find a way through this together. Let's keep exploring what might help."

    def generate_end_of_session_profile(self, old_profile: dict, session_history: list, patient_info: dict = None) -> LLM3Output:
        try:
            sys_prompt = LLM3_SYSTEM_PROMPT
            if patient_info:
                demographics = (
                    f"PATIENT DEMOGRAPHICS:\n"
                    f"- Name: {patient_info.get('name', 'Unknown')}\n"
                    f"- Age: {patient_info.get('age', 'Unknown')}\n"
                    f"- Gender: {patient_info.get('gender', 'Unknown')}\n"
                    f"- Nationality: {patient_info.get('nationality', 'Unknown')}\n"
                    f"- Primary Concern: {patient_info.get('primary_concern', 'Unknown')}\n\n"
                )
                sys_prompt = demographics + sys_prompt
            
            formatted_history = "\n".join(f"{t['role'].upper()}: {t['content']}" for t in session_history)
            user_prompt = (
                f"EXISTING PROFILE:\n{old_profile}\n\n"
                f"RECENT SESSION TRANSCRIPT:\n{formatted_history}\n\n"
                "Please generate the 100-200 word session_summary and the merged, deduplicated clinical profile."
            )
            messages = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt}
            ]

            with self._llm_lock:
                response = self._client().chat(
                    model=self.model1,
                    messages=messages,
                    format=LLM3Output.model_json_schema(),
                    options={"temperature": 0.2, "num_predict": 1500, "num_ctx": 8192},
                )
            raw = response.message.content
            return LLM3Output.model_validate_json(raw)
        except Exception as e:
            print(f"[LLM3 ERROR] {e}")
            return LLM3Output(
                session_summary="Error generating session summary.",
                emotional_themes=[],
                thinking_patterns=[],
                behavioral_patterns=[],
                interpersonal_dynamics=[],
                stressors=[],
                unclear_areas=[],
                risk_assessment="Error.",
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
            with self._llm_lock:
                response = self._client().chat(
                    model=self.model1,
                    messages=messages,
                    options={"temperature": 0.3, "num_predict": 300, "num_ctx": 8192},
                )
            return response.message.content.strip()
        except Exception as e:
            print(f"[SUMMARIZE ERROR] {e}")
            return "[Summary unavailable]"
