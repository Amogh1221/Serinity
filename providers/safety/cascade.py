from typing import Optional
from core.ports import RiskSignal, LLM1Output, LLM2Output
import logging

logger = logging.getLogger(__name__)

class CascadeRiskSignal:
    """
    Implements a Filter-Verify (Cascade) architecture for risk signals.
    Passes the message through a high-speed, high-recall filter first. 
    Only if the filter triggers does it pass the message to a slower, high-precision verifier.
    """
    def __init__(self, filter_signal: RiskSignal, verify_signal: RiskSignal):
        self.filter_signal = filter_signal
        self.verify_signal = verify_signal

    def check(self, message: str, llm1_output: LLM1Output, llm2_output: Optional[LLM2Output] = None) -> bool:
        # 1. FAST PASS
        if not self.filter_signal.check(message, llm1_output, llm2_output):
            return False
            
        logger.info("Fast-pass filter triggered. Verifying with secondary signal...")
        
        # 2. SLOW PASS (Verification)
        return self.verify_signal.check(message, llm1_output, llm2_output)
