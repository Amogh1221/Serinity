# -*- coding: utf-8 -*-
"""
logger.py — Structured logging for Serinity (BetterStack + Local Rotation).

Writes logs to a single rolling file (logs/serinity.log) max 10MB each.
Streams logs to BetterStack if BETTERSTACK_SOURCE_TOKEN is set.
"""

import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

try:
    from logtail import LogtailHandler
except ImportError:
    LogtailHandler = None

load_dotenv()

LOG_DIR = os.getenv("LOG_DIR", "./logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Set up global logger
serinity_logger = logging.getLogger("serinity")
serinity_logger.setLevel(logging.INFO)
serinity_logger.propagate = False # Prevent double logging if root logger is active

# 1. Local Rotating File Handler (Max 10MB, Keep 5)
file_path = os.path.join(LOG_DIR, "serinity.log")
file_handler = RotatingFileHandler(file_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(file_formatter)
serinity_logger.addHandler(file_handler)

# 2. BetterStack Handler
CLOUD_MODE = os.getenv("CLOUD_MODE", "false").lower() == "true"
source_token = os.getenv("BETTERSTACK_SOURCE_TOKEN")

if CLOUD_MODE and source_token and LogtailHandler:
    logtail_handler = LogtailHandler(source_token=source_token)
    serinity_logger.addHandler(logtail_handler)

class DebugLogger:
    """
    Per-session logger instance wrapper.
    Formats structured events and pushes them to the global logger.
    """

    def __init__(self, session_id: str, user_name: str = "Unknown", session_number: int = 1):
        self.session_id = session_id
        self.user_name = user_name
        self._turn = 0

    def _log_event(self, event_type: str, data: dict):
        payload = {
            "session_id": self.session_id,
            "user_name": self.user_name,
            "event_type": event_type,
            **data
        }
        # Dump to JSON for local file, and pass 'extra' for BetterStack structuring
        log_message = json.dumps(payload, ensure_ascii=False)
        serinity_logger.info(log_message, extra=payload)

    # Public logging methods

    def session_start(self, patient_id: str | None):
        # We defer logging empty sessions until the first user message.
        pass

    def user_message(self, raw_text: str, emotion: str | None = None):
        if self._turn == 0:
            # Lazy-log the session start now that we know they actually sent a message
            self._log_event("session_start", {"patient_id": "active"})
        
        self._turn += 1
        self._log_event("user_message", {
            "turn":    self._turn,
            "text":    raw_text,
            "emotion": emotion,
        })

    def safety_check(self, text: str, risk_flagged: bool):
        self._log_event("safety_check", {
            "turn":        self._turn,
            "risk_flagged": risk_flagged,
            "text_snippet": text[:100],
        })

    def llm1_decision(self, llm1_output):
        self._log_event("llm1_decision", {
            "turn":             self._turn,
            "intent":           llm1_output.intent if hasattr(llm1_output, 'intent') else "unknown",
            "llm_message":      llm1_output.assistant_message if hasattr(llm1_output, 'assistant_message') else "",
        })

    def analyze_triggered(self, retrieval_query: str, query_source: str):
        self._log_event("analyze_triggered", {
            "turn":            self._turn,
            "query_source":    query_source,
            "retrieval_query": retrieval_query,
        })

    def retrieved_context(self, context_str: str):
        self._log_event("retrieved_context", {
            "turn":           self._turn,
            "context_length": len(context_str),
        })

    def llm2_output(self, llm2_analysis):
        self._log_event("llm2_output", {
            "turn":           self._turn,
            "analysis_dump":  str(llm2_analysis),
        })

    def llm1_final(self, final_text: str):
        self._log_event("llm1_final", {
            "turn": self._turn,
        })

    def llm3_output(self, llm3_response):
        """Log the full post-session LLM3 analysis."""
        self._log_event("llm3_output", {
            "session_summary":       getattr(llm3_response, "session_summary", ""),
            "emotional_themes":      getattr(llm3_response, "emotional_themes", []),
            "thinking_patterns":     getattr(llm3_response, "thinking_patterns", []),
            "behavioral_patterns":   getattr(llm3_response, "behavioral_patterns", []),
            "interpersonal_dynamics":getattr(llm3_response, "interpersonal_dynamics", []),
            "stressors":             getattr(llm3_response, "stressors", []),
        })

    def assistant_reply(self, message: str, risk_injected: bool = False, latency_ms: int = 0):
        self._log_event("assistant_reply", {
            "turn":        self._turn,
            "message_length": len(message),
            "risk_injected": risk_injected,
            "latency_ms": latency_ms,
        })

    def error(self, context: str, exc: Exception):
        self._log_event("error", {
            "turn":    self._turn,
            "context": context,
            "error":   str(exc),
        })

    def close(self):
        # We no longer need to manually close file handlers since logging manages it
        pass

# Global dictionary to hold active loggers
_active_loggers: dict[str, DebugLogger] = {}

def get_logger(session_id: str, user_name: str = "Unknown", session_number: int = 1) -> DebugLogger:
    if session_id not in _active_loggers:
        _active_loggers[session_id] = DebugLogger(session_id, user_name, session_number)
    return _active_loggers[session_id]

def close_logger(session_id: str):
    if session_id in _active_loggers:
        _active_loggers[session_id].close()
        del _active_loggers[session_id]
