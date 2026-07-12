from typing import Optional
from core.ports import LLM1Output, LLM2Output

class ClinicalRiskSignal:
    """
    Risk signal that triggers based on the 'risk_assessment' output from the 
    background LLM2 pattern analysis.
    """
    def check(self, message: str, llm1_output: LLM1Output, llm2_output: Optional[LLM2Output] = None) -> bool:
        if llm2_output is None:
            return False
        assessment = llm2_output.risk_assessment.strip().lower()
        if assessment.startswith("no safety concerns identified"):
            return False
        if assessment == "":
            return False
        return True
