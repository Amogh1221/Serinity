import pytest
from unittest.mock import MagicMock, patch
from providers.safety.bert import BertRiskSignal
from providers.safety.clinical import ClinicalRiskSignal
from providers.safety.keyword import KeywordRiskSignal
from providers.safety.cascade import CascadeRiskSignal
from core.ports import LLM1Output, LLM2Output


def _make_llm1(intent="CONTINUE", msg="", summary=""):
    return LLM1Output(intent=intent, assistant_message=msg, clinical_summary=summary)


def _make_llm2(risk="No safety concerns identified."):
    return LLM2Output(
        assistant_message="Internal analysis.",
        emotional_themes=[],
        thinking_patterns=[],
        behavioral_patterns=[],
        interpersonal_dynamics=[],
        stressors=[],
        unclear_areas=[],
        protective_factors=[],
        risk_assessment=risk
    )


# ───────────────────────── BERT Safety ──────────────────────────────────────

class TestBertRiskSignal:

    def test_bert_flags_suicidal_message(self):
        """BERT model returning 'label_1' triggers a risk flag."""
        with patch("providers.safety.bert.pipeline") as mock_pipeline:
            mock_classifier = MagicMock()
            mock_classifier.return_value = [{"label": "LABEL_1", "score": 0.98}]
            mock_pipeline.return_value = mock_classifier

            signal = BertRiskSignal()

        result = signal.check("I want to end my life", _make_llm1())
        assert result is True

    def test_bert_clears_normal_message(self):
        """BERT model returning 'label_0' does not trigger a risk flag."""
        with patch("providers.safety.bert.pipeline") as mock_pipeline:
            mock_classifier = MagicMock()
            mock_classifier.return_value = [{"label": "LABEL_0", "score": 0.95}]
            mock_pipeline.return_value = mock_classifier

            signal = BertRiskSignal()

        result = signal.check("I'm feeling a bit tired today", _make_llm1())
        assert result is False

    def test_bert_ignores_empty_message(self):
        """An empty message string bypasses BERT classification and returns False."""
        with patch("providers.safety.bert.pipeline") as mock_pipeline:
            mock_classifier = MagicMock()
            mock_pipeline.return_value = mock_classifier
            signal = BertRiskSignal()

        result = signal.check("", _make_llm1())
        assert result is False
        mock_classifier.assert_not_called()

    def test_bert_returns_false_on_exception(self):
        """If BERT classifier throws, check() returns False and does not crash."""
        with patch("providers.safety.bert.pipeline") as mock_pipeline:
            mock_classifier = MagicMock()
            mock_classifier.side_effect = RuntimeError("GPU OOM")
            mock_pipeline.return_value = mock_classifier
            signal = BertRiskSignal()

        result = signal.check("I am desperate", _make_llm1())
        assert result is False


# ──────────────────────── Clinical Safety ───────────────────────────────────

class TestClinicalRiskSignal:

    def test_no_llm2_output_returns_false(self):
        signal = ClinicalRiskSignal()
        assert signal.check("test", _make_llm1(), None) is False

    def test_safe_assessment_returns_false(self):
        signal = ClinicalRiskSignal()
        llm2 = _make_llm2(risk="No safety concerns identified. Patient is stable.")
        assert signal.check("test", _make_llm1(), llm2) is False

    def test_risk_assessment_triggers_flag(self):
        signal = ClinicalRiskSignal()
        llm2 = _make_llm2(risk="Patient has expressed suicidal ideation and requires immediate intervention.")
        assert signal.check("test", _make_llm1(), llm2) is True

    def test_empty_assessment_returns_false(self):
        signal = ClinicalRiskSignal()
        llm2 = _make_llm2(risk="")
        assert signal.check("test", _make_llm1(), llm2) is False


# ──────────────────────── Keyword Safety ────────────────────────────────────

class TestKeywordRiskSignal:

    def test_flags_suicidal_keyword(self):
        from providers.safety.keyword import KeywordRiskSignal
        signal = KeywordRiskSignal()
        assert signal.check("I want to kill myself", _make_llm1()) is True

    def test_clears_safe_message(self):
        from providers.safety.keyword import KeywordRiskSignal
        signal = KeywordRiskSignal()
        assert signal.check("I had a good day at work", _make_llm1()) is False


# ───────────────────────── Risk Cascade ─────────────────────────────────────

class TestCascadeRiskSignal:

    def test_cascade_returns_true_if_both_signals_fire(self):
        filter_signal = MagicMock()
        filter_signal.check.return_value = True

        verify_signal = MagicMock()
        verify_signal.check.return_value = True

        cascade = CascadeRiskSignal(filter_signal, verify_signal)
        assert cascade.check("msg", _make_llm1(), None) is True

    def test_cascade_returns_false_if_filter_fails(self):
        filter_signal = MagicMock()
        filter_signal.check.return_value = False

        verify_signal = MagicMock()

        cascade = CascadeRiskSignal(filter_signal, verify_signal)
        assert cascade.check("msg", _make_llm1(), None) is False
        verify_signal.check.assert_not_called()
