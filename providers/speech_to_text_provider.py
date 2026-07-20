import io
import re
import tempfile
from typing import Dict, Any

_EMOTION_MAP = {
    "HAPPY":     "happy",
    "SAD":       "sad",
    "ANGRY":     "angry",
    "NEUTRAL":   "neutral",
    "FEARFUL":   "fearful",
    "DISGUSTED": "disgusted",
    "SURPRISED": "surprised",
}
_KNOWN_EVENTS = {"Speech", "Laughter", "Cry", "Cough", "Sneeze", "Breath", "Noise"}
_TAG_RE = re.compile(r"<\|([^|]+)\|>")

def _parse_sensevoice_output(raw_text: str) -> tuple[str, str, str | None]:
    tags = _TAG_RE.findall(raw_text)
    clean = _TAG_RE.sub("", raw_text).strip()

    emotion = "neutral"
    event: str | None = None

    for tag in tags:
        upper = tag.upper()
        if upper in _EMOTION_MAP:
            emotion = _EMOTION_MAP[upper]
        if tag in _KNOWN_EVENTS:
            event = tag

    return clean, emotion, event

class SenseVoiceSTTProvider:
    """
    Concrete implementation of the STTProvider protocol using FunASR's SenseVoiceSmall model.
    Transcribes audio into text while simultaneously extracting vocal emotional tone 
    (e.g., happy, sad, angry) and acoustic events (e.g., laughter, crying).
    """
    def __init__(self):
        self._sense_voice = None
        self._init_stt()

    def _init_stt(self):
        try:
            from funasr import AutoModel
            from funasr.utils.postprocess_utils import rich_transcription_postprocess

            self._sense_voice = AutoModel(
                model="iic/SenseVoiceSmall",
                trust_remote_code=True,
                remote_code="./model.py",
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                device="cpu",
                disable_update=True
            )
            print("[STARTUP] SenseVoice-Small loaded successfully.")
        except Exception as e:
            print(f"[WARNING] Failed to load SenseVoice: {e}")
            self._sense_voice = None

    def transcribe(self, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Takes raw webm/ogg bytes, runs them through SenseVoice,
        and returns {text, emotion, event}.
        """
        if not self._sense_voice:
            print("[WARNING] STT requested but SenseVoice is not loaded.")
            return {"text": "", "emotion": "unknown", "event": None}

        # funasr expects a file path
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tf:
            tf.write(audio_bytes)
            tf.flush()
            temp_path = tf.name

        try:
            res = self._sense_voice.generate(
                input=temp_path,
                cache={},
                language="auto", 
                use_itn=True,
                batch_size_s=60,
                merge_vad=True, 
                merge_length_s=15,
            )
            if not res or len(res) == 0:
                return {"text": "", "emotion": "neutral", "event": None}

            raw_text = res[0].get("text", "")
            clean, emotion, event = _parse_sensevoice_output(raw_text)

            return {
                "text": clean,
                "emotion": emotion,
                "event": event
            }
        except Exception as e:
            print(f"[ERROR] SenseVoice transcription failed: {e}")
            return {"text": "", "emotion": "unknown", "event": None}
        finally:
            import os
            try:
                os.remove(temp_path)
            except OSError:
                pass
