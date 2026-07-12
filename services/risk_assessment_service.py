from typing import List, Optional
from core.ports import RiskSignal, LLM1Output, LLM2Output

class RiskAssessmentService:
    """
    Evaluates patient messages and LLM responses against a suite of RiskSignals.
    Ensures patient safety by identifying crisis or self-harm intents in real-time.
    """
    def __init__(self, signals: List[RiskSignal]):
        self._signals = signals

    def assess(self, message: str, llm1_output: LLM1Output, llm2_output: Optional[LLM2Output] = None) -> bool:
        """Evaluate all risk signals and return True if any indicate a risk."""
        return any(
            signal.check(message, llm1_output, llm2_output)
            for signal in self._signals
        )
