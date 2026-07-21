import json
import pytest
from unittest.mock import MagicMock, patch
from core.ports import LLM1Output, LLM2Output, LLM3Output


# ───────────────────────── Groq LLM Provider ──────────────────────────────

class TestGroqLLMProvider:
    """Tests for GroqLLMProvider, mocking the Groq client."""

    def _make_groq_response(self, content: str):
        """Build a fake groq chat completion object."""
        msg = MagicMock()
        msg.content = content
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    def test_psychiatrist_response(self):
        """LLM1 parses structured JSON into LLM1Output."""
        from providers.llms.groq_llm_provider import GroqLLMProvider

        llm1_json = json.dumps({
            "intent": "CONTINUE",
            "assistant_message": "Tell me more.",
            "clinical_summary": "Patient feels isolated.",
            "search_query": None
        })

        with patch("providers.llms.groq_llm_provider.Groq") as MockGroq:
            mock_client = MockGroq.return_value
            mock_client.chat.completions.create.return_value = self._make_groq_response(llm1_json)
            provider = GroqLLMProvider(model1="llama3-8b-8192", model2="llama3-8b-8192")

        result = provider.psychiatrist_response(context=[{"role": "user", "content": "I feel alone."}])

        assert isinstance(result, LLM1Output)
        assert result.intent == "CONTINUE"
        assert result.assistant_message == "Tell me more."

    def test_psychiatrist_response_with_patient_info(self):
        """Patient demographics are prepended to system prompt."""
        from providers.llms.groq_llm_provider import GroqLLMProvider

        llm1_json = json.dumps({
            "intent": "CONTINUE",
            "assistant_message": "I hear you.",
            "clinical_summary": "",
            "search_query": None
        })

        with patch("providers.llms.groq_llm_provider.Groq") as MockGroq:
            mock_client = MockGroq.return_value
            mock_client.chat.completions.create.return_value = self._make_groq_response(llm1_json)
            provider = GroqLLMProvider(model1="llama3-8b-8192", model2="llama3-8b-8192")

        patient_info = {"name": "Jane", "age": 28, "gender": "Female", "nationality": "US", "primary_concern": "Anxiety"}
        result = provider.psychiatrist_response(context=[], patient_info=patient_info)

        assert result.intent == "CONTINUE"
        # After caching refactor:
        #   messages[0] = cached LLM1_SYSTEM_PROMPT  (content is a list with cache_control)
        #   messages[1] = cached stable context block (demographics + MTM, also a list)
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs[1]["messages"]
        # Demographics are in the second message's text block
        stable_text = messages[1]["content"][0]["text"]
        assert "Jane" in stable_text


    def test_psychiatrist_query_response(self):
        """QUERY path returns a plain string from the LLM."""
        from providers.llms.groq_llm_provider import GroqLLMProvider

        with patch("providers.llms.groq_llm_provider.Groq") as MockGroq:
            mock_client = MockGroq.return_value
            mock_client.chat.completions.create.return_value = self._make_groq_response("Anxiety is characterized by...")
            provider = GroqLLMProvider(model1="llama3-8b-8192", model2="llama3-8b-8192")

        result = provider.psychiatrist_query_response(context=[], retrieved_context="Clinical guidelines on anxiety")

        assert result == "Anxiety is characterized by..."

    def test_internal_reasoning(self):
        """LLM2 parses structured JSON into LLM2Output."""
        from providers.llms.groq_llm_provider import GroqLLMProvider

        llm2_json = json.dumps({
            "assistant_message": "Analysis",
            "emotional_themes": [],
            "thinking_patterns": [],
            "behavioral_patterns": [],
            "interpersonal_dynamics": [],
            "stressors": [],
            "unclear_areas": [],
            "protective_factors": [],
            "risk_assessment": "No safety concerns identified."
        })

        with patch("providers.llms.groq_llm_provider.Groq") as MockGroq:
            mock_client = MockGroq.return_value
            mock_client.chat.completions.create.return_value = self._make_groq_response(llm2_json)
            provider = GroqLLMProvider(model1="llama3-8b-8192", model2="llama3-8b-8192")

        result = provider.internal_reasoning(context=[])
        assert isinstance(result, LLM2Output)
        assert result.risk_assessment == "No safety concerns identified."

    def test_generate_end_of_session_profile(self):
        """LLM3 parses structured JSON into LLM3Output."""
        from providers.llms.groq_llm_provider import GroqLLMProvider

        llm3_json = json.dumps({
            "session_summary": "Patient discussed stress.",
            "update_profile": True,
            "emotional_themes": ["stress"],
            "thinking_patterns": [],
            "behavioral_patterns": [],
            "interpersonal_dynamics": [],
            "stressors": [],
            "unclear_areas": [],
            "risk_assessment": "No safety concerns identified.",
            "protective_factors": [],
            "updated_primary_concern": None
        })

        with patch("providers.llms.groq_llm_provider.Groq") as MockGroq:
            mock_client = MockGroq.return_value
            mock_client.chat.completions.create.return_value = self._make_groq_response(llm3_json)
            provider = GroqLLMProvider(model1="llama3-8b-8192", model2="llama3-8b-8192")

        result = provider.generate_end_of_session_profile(old_profile={}, session_history=[])
        assert isinstance(result, LLM3Output)
        assert result.session_summary == "Patient discussed stress."

    def test_summarize_history_empty(self):
        """An empty history list returns an empty string without calling the API."""
        from providers.llms.groq_llm_provider import GroqLLMProvider

        with patch("providers.llms.groq_llm_provider.Groq") as MockGroq:
            mock_client = MockGroq.return_value
            provider = GroqLLMProvider(model1="llama3-8b-8192", model2="llama3-8b-8192")

        result = provider.summarize_history(turns=[])
        assert result == ""
        mock_client.chat.completions.create.assert_not_called()


# ───────────────────────── Ollama LLM Provider ──────────────────────────────

class TestOllamaLLMProvider:
    """Tests for OllamaLLMProvider, mocking requests.post."""

    def _make_ollama_response(self, content: str):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": content}}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_psychiatrist_response(self):
        from providers.llms.ollama_llm_provider import OllamaLLMProvider

        llm1_json = json.dumps({
            "intent": "CONTINUE",
            "assistant_message": "I hear you.",
            "clinical_summary": "",
            "search_query": None
        })

        with patch("providers.llms.ollama_llm_provider.ollama.Client") as MockClient:
            mock_client = MockClient.return_value
            # Mock the chat response
            mock_response = MagicMock()
            mock_response.message.content = llm1_json
            mock_client.chat.return_value = mock_response

            provider = OllamaLLMProvider(host="http://localhost:11434", model1="llama3.1", model2="llama3.1")
            result = provider.psychiatrist_response(context=[])

        assert isinstance(result, LLM1Output)
        assert result.intent == "CONTINUE"
        assert result.assistant_message == "I hear you."
