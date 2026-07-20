from typing import Optional
from core.ports import LLM1Output, LLM2Output

class LLMRiskSignal:
    """
    Risk signal that triggers based on the 'risk_flag' explicitly set by LLM1 
    during its generation of the conversational response.
    """
    def check(self, message: str, llm1_output: LLM1Output, llm2_output: Optional[LLM2Output] = None) -> bool:
        return llm1_output.risk_flag
