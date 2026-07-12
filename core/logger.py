# -*- coding: utf-8 -*-
"""
debug_logger.py — Structured debug logging for Serinity.

Writes one file per session into logs/:
  1. <user_name>(hh-mm-ss_dd-mm-yyyy).jsonl  — machine-parseable, one JSON object per event

Events logged:
  - session_start        : new session opened
  - user_message         : raw user text (before vocal tone prefix)
  - safety_check         : result of contains_risk_signal()
  - llm1_decision        : LLM1's full output (message + intent + clinical_summary)
  - analyze_triggered    : retrieval query sent to ChromaDB
  - retrieved_context    : full retrieved context from ChromaDB
  - llm2_output          : full LLM2 analysis across all 8 domains
  - llm1_final           : LLM1's synthesis response after ANALYZE
  - assistant_reply      : final message sent to user (after safety injection)
  - error                : any caught exception

Usage:
    from core.logger import get_logger, close_logger
    log = get_logger(session_id)
    log.user_message("I feel hopeless")
    log.llm1_decision(llm1_response)
    ...
    close_logger(session_id)
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LOG_DIR = os.getenv("LOG_DIR", "./logs")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DebugLogger:
    """
    Per-session logger. Create one instance per session and call close() when done.
    """

    def __init__(self, session_id: str, user_name: str = "Unknown"):
        self.session_id = session_id
        os.makedirs(LOG_DIR, exist_ok=True)

        # Format date-time as HH-MM-SS_DD-MM-YYYY
        ts_slug = datetime.now().strftime("%H-%M-%S_%d-%m-%Y")
        safe_user_name = "".join(c for c in user_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        
        self._jsonl_path = os.path.join(LOG_DIR, f"{safe_user_name}({ts_slug}).jsonl")

        self._jsonl = open(self._jsonl_path, "a", encoding="utf-8")
        self._turn  = 0

        self._write_jsonl("session_start", {"session_id": session_id})

    # ------------------------------------------------------------------
    # Public logging methods
    # ------------------------------------------------------------------

    def session_start(self, patient_id: str | None):
        self._write_jsonl("session_start", {"patient_id": patient_id})

    def user_message(self, raw_text: str, emotion: str | None = None):
        self._turn += 1
        self._write_jsonl("user_message", {
            "turn":    self._turn,
            "text":    raw_text,
            "emotion": emotion,
        })

    def safety_check(self, text: str, risk_flagged: bool):
        self._write_jsonl("safety_check", {
            "turn":        self._turn,
            "risk_flagged": risk_flagged,
            "text_snippet": text[:100],
        })

    def llm1_decision(self, llm1_output):
        """Log LLM1's response — always called, regardless of intent."""
        self._write_jsonl("llm1_decision", {
            "turn":             self._turn,
            "intent":           llm1_output.intent,
            "message":          llm1_output.assistant_message,
            "clinical_summary": llm1_output.clinical_summary,
        })

    def analyze_triggered(self, retrieval_query: str, query_source: str):
        """Log that ANALYZE path started and what query was sent to ChromaDB."""
        self._write_jsonl("analyze_triggered", {
            "turn":            self._turn,
            "query_source":    query_source,
            "retrieval_query": retrieval_query,
        })

    def retrieved_context(self, context_text: str):
        """Log the full retrieved ChromaDB context."""
        docs = context_text.split("\n\n") if context_text else []
        self._write_jsonl("retrieved_context", {
            "turn":             self._turn,
            "num_docs":         len(docs),
            "context":          context_text,
        })

    def llm2_output(self, llm2_response):
        """Log the full LLM2 analysis output."""
        self._write_jsonl("llm2_output", {
            "turn":                  self._turn,
            "emotional_themes":      llm2_response.emotional_themes,
            "thinking_patterns":     llm2_response.thinking_patterns,
            "behavioral_patterns":   llm2_response.behavioral_patterns,
            "interpersonal_dynamics":llm2_response.interpersonal_dynamics,
            "stressors":             llm2_response.stressors,
            "unclear_areas":         llm2_response.unclear_areas,
            "protective_factors":    llm2_response.protective_factors,
            "risk_assessment":       llm2_response.risk_assessment,
        })

    def llm1_final(self, llm1_output):
        """Log LLM1's post-analysis synthesis response."""
        self._write_jsonl("llm1_final", {
            "turn":    self._turn,
            "message": llm1_output.assistant_message,
        })

    def assistant_reply(self, message: str, risk_injected: bool):
        """Log the final message sent back to the user."""
        self._write_jsonl("assistant_reply", {
            "turn":           self._turn,
            "message":        message,
            "risk_injected":  risk_injected,
        })

    def error(self, context: str, exc: Exception):
        self._write_jsonl("error", {
            "turn":      self._turn,
            "context":   context,
            "exception": f"{type(exc).__name__}: {exc}",
        })

    def close(self):
        if hasattr(self, "_jsonl") and not self._jsonl.closed:
            self._write_jsonl("session_end", {"session_id": self.session_id})
            self._jsonl.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_jsonl(self, event: str, data: dict):
        record = {"ts": _now(), "event": event, **data}
        self._jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._jsonl.flush()


# ---------------------------------------------------------------------------
# Convenience: session-keyed registry so main.py can look up loggers by session
# ---------------------------------------------------------------------------
_active_loggers: dict[str, DebugLogger] = {}


def get_logger(session_id: str, user_name: str = "Unknown") -> DebugLogger:
    """Get or create a DebugLogger for the given session."""
    if session_id not in _active_loggers:
        _active_loggers[session_id] = DebugLogger(session_id, user_name)
    return _active_loggers[session_id]


def close_logger(session_id: str):
    """Close and remove the logger for a session."""
    if session_id in _active_loggers:
        _active_loggers[session_id].close()
        del _active_loggers[session_id]
