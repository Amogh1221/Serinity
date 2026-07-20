import pytest
from unittest.mock import MagicMock, patch
from providers.speech_to_text_provider import _parse_sensevoice_output, SenseVoiceSTTProvider


# ────────────── Pure parsing function (no model needed) ──────────────────

class TestParseSenseVoiceOutput:
    """Tests for the pure _parse_sensevoice_output helper, no mocks needed."""

    def test_extracts_emotion_happy(self):
        raw = "<|HAPPY|><|Speech|>Today is a great day."
        text, emotion, event = _parse_sensevoice_output(raw)
        assert text == "Today is a great day."
        assert emotion == "happy"
        assert event == "Speech"

    def test_extracts_emotion_sad(self):
        raw = "<|SAD|>I feel terrible."
        text, emotion, event = _parse_sensevoice_output(raw)
        assert text == "I feel terrible."
        assert emotion == "sad"
        assert event is None

    def test_defaults_to_neutral_for_no_tag(self):
        raw = "Just a plain sentence."
        text, emotion, event = _parse_sensevoice_output(raw)
        assert text == "Just a plain sentence."
        assert emotion == "neutral"
        assert event is None

    def test_strips_multiple_tags(self):
        raw = "<|NEUTRAL|><|Laughter|>Ha ha ha."
        text, emotion, event = _parse_sensevoice_output(raw)
        assert text == "Ha ha ha."
        assert emotion == "neutral"
        assert event == "Laughter"


# ──────────────── SenseVoiceSTTProvider (mocked model) ───────────────────

class TestSenseVoiceSTTProvider:
    """Tests for SenseVoiceSTTProvider with FunASR mocked out."""

    def test_transcribe_returns_text_and_emotion(self, tmp_path):
        """Provider correctly calls the model and parses the output."""
        with patch("providers.speech_to_text_provider.SenseVoiceSTTProvider._init_stt") as mock_init:
            provider = SenseVoiceSTTProvider.__new__(SenseVoiceSTTProvider)
            provider._sense_voice = MagicMock()
            provider._sense_voice.generate.return_value = [
                {"text": "<|SAD|><|Speech|>I feel really low today."}
            ]

        result = provider.transcribe(b"fake_audio_bytes")
        assert result["text"] == "I feel really low today."
        assert result["emotion"] == "sad"
        assert result["event"] == "Speech"

    def test_transcribe_returns_empty_when_model_not_loaded(self):
        """If SenseVoice didn't load, transcribe gracefully returns empty."""
        provider = SenseVoiceSTTProvider.__new__(SenseVoiceSTTProvider)
        provider._sense_voice = None

        result = provider.transcribe(b"fake_audio_bytes")
        assert result["text"] == ""
        assert result["emotion"] == "unknown"

    def test_transcribe_returns_empty_on_empty_model_response(self):
        """Empty list from FunASR returns safe empty result."""
        provider = SenseVoiceSTTProvider.__new__(SenseVoiceSTTProvider)
        provider._sense_voice = MagicMock()
        provider._sense_voice.generate.return_value = []

        result = provider.transcribe(b"fake_audio_bytes")
        assert result["text"] == ""
        assert result["emotion"] == "neutral"

    def test_transcribe_handles_generate_exception(self):
        """If FunASR throws during generate, transcribe returns a safe fallback."""
        provider = SenseVoiceSTTProvider.__new__(SenseVoiceSTTProvider)
        provider._sense_voice = MagicMock()
        provider._sense_voice.generate.side_effect = RuntimeError("Model crash")

        result = provider.transcribe(b"fake_audio_bytes")
        assert result["text"] == ""
        assert result["emotion"] == "unknown"

    def test_init_handles_missing_funasr(self):
        """If funasr is not installed, provider initializes gracefully with _sense_voice=None."""
        with patch.dict("sys.modules", {"funasr": None, "funasr.utils.postprocess_utils": None}):
            provider = SenseVoiceSTTProvider()
        assert provider._sense_voice is None
