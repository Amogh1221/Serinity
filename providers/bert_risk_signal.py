from typing import Optional
from transformers import pipeline
import logging

from core.ports import LLM1Output, LLM2Output

logger = logging.getLogger(__name__)

class BertRiskSignal:
    """
    NLP-based risk signal using a fine-tuned BERT model.
    Downloads and caches the model on initial run to the HF_HOME directory.
    Checks the patient's raw message for suicidal/self-harm ideation 
    with much higher contextual accuracy than regex keywords.
    """
    def __init__(self, model_name: str = "Akashpaul123/bert-suicide-detection"):
        logger.info(f"Loading BertRiskSignal with model: {model_name}. This may take a moment on first run to download...")
        # The pipeline handles downloading and caching automatically using HF_HOME
        self.classifier = pipeline("text-classification", model=model_name, truncation=True, max_length=512)
        logger.info("BertRiskSignal loaded successfully.")

    def check(self, message: str, llm1_output: LLM1Output, llm2_output: Optional[LLM2Output] = None) -> bool:
        if not message or not message.strip():
            return False
            
        try:
            result = self.classifier(message)
            label = result[0]['label'].lower()
            score = result[0]['score']
            
            logger.info(f"BERT raw output for '{message}': {label} (score: {score:.3f})")
            
            # Outputs 'label_1' for suicide/risk & 'label_0' for non-suicide
            if "label_1" in label:
                return True
                
            return False
        except Exception as e:
            logger.error(f"Error in BertRiskSignal: {e}")
            return False
