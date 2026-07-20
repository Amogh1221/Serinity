import os
import json
from groq import Groq
from core.ports import LLM1Output, LLM2Output, LLM3Output
from core.prompts import LLM1_SYSTEM_PROMPT, LLM2_SYSTEM_PROMPT, LLM3_SYSTEM_PROMPT

class GroqLLMProvider:
    """
    Concrete implementation of the LLMProvider protocol using the Groq API.
    Provides true asynchronous concurrency (no local GPU threading lock required).
    """
    def __init__(self, model1: str, model2: str):
        self.model1 = model1
        self.model2 = model2
        # Relies on the GROQ_API_KEY environment variable being set
        self.client = Groq()
        
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
        
    def psychiatrist_response(self, context: list, patient_info: dict = None) -> LLM1Output:
        try:
            sys_prompt = LLM1_SYSTEM_PROMPT
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
                
            messages = [{"role": "system", "content": sys_prompt}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.6,
                max_completion_tokens=1024,
            )
            raw = response.choices[0].message.content
            return LLM1Output.model_validate_json(raw)
        except Exception as e:
            print(f"[Groq LLM1 ERROR] {e}")
            raise e

    def internal_reasoning(self, context: list) -> LLM2Output:
        try:
            messages = [{"role": "system", "content": LLM2_SYSTEM_PROMPT}]
            for m in context:
                messages.append({"role": m["role"], "content": m["content"]})

            response = self.client.chat.completions.create(
                model=self.model2,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.1,
                max_completion_tokens=1024,
            )
            raw = response.choices[0].message.content
            return LLM2Output.model_validate_json(raw)
        except Exception as e:
            print(f"[Groq LLM2 ERROR] {e}")
            raise e

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

            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                temperature=0.5,
                max_completion_tokens=512,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Groq QUERY ERROR] {e}")
            raise e

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

            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_completion_tokens=1500,
            )
            raw = response.choices[0].message.content
            return LLM3Output.model_validate_json(raw)
        except Exception as e:
            print(f"[Groq LLM3 ERROR] {e}")
            raise e

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
            response = self.client.chat.completions.create(
                model=self.model1,
                messages=messages,
                temperature=0.3,
                max_completion_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Groq SUMMARIZE ERROR] {e}")
            raise e
