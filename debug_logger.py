# -*- coding: utf-8 -*-
"""
debug_logger.py — Structured debug logging for Serinity.

Writes two files per session into logs/:
  1. <session_id>.jsonl  — machine-parseable, one JSON object per event
  2. <session_id>.txt    — human-readable, easy to scan during debugging

Events logged:
  - session_start        : new session opened
  - user_message         : raw user text (before vocal tone prefix)
  - safety_check         : result of contains_risk_signal()
  - llm1_decision        : LLM1's full output (message + intent + clinical_summary)
  - analyze_triggered    : retrieval query sent to ChromaDB
  - retrieved_context    : top-k docs returned (truncated for readability)
  - llm2_output          : full LLM2 analysis across all 8 domains
  - llm1_final           : LLM1's synthesis response after ANALYZE
  - assistant_reply      : final message sent to user (after safety injection)
  - error                : any caught exception

Usage:
    from debug_logger import DebugLogger
    log = DebugLogger(session_id)
    log.user_message("I feel hopeless")
    log.llm1_decision(llm1_response)
    ...
    log.close()
"""

import os
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

LOG_DIR = os.getenv("LOG_DIR", "./logs")

# Maximum characters of retrieved context to write per retrieved doc
_CTX_SNIPPET_LEN = 400
# Max number of retrieved docs to log in full
_MAX_DOCS_LOGGED = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _divider(char="─", width=70) -> str:
    return char * width


class DebugLogger:
    """
    Per-session logger. Create one instance per session and call close() when done.
    The .txt file is the primary human-readable artifact; .jsonl is for tooling.
    """

    def __init__(self, session_id: str, user_name: str = "Unknown"):
        self.session_id = session_id
        os.makedirs(LOG_DIR, exist_ok=True)

        # Count existing session files to find the next index
        session_idx = 1
        try:
            files = os.listdir(LOG_DIR)
            session_nums = []
            for f in files:
                if "-session-" in f and (f.endswith(".txt") or f.endswith(".jsonl")):
                    # Extract the number part from "-session-X-"
                    parts = f.split("-session-")
                    if len(parts) > 1:
                        num_part = parts[1].split("-")[0]
                        if num_part.isdigit():
                            session_nums.append(int(num_part))
                elif f.startswith("session-") and (f.endswith(".txt") or f.endswith(".jsonl")):
                    parts = f.split("(")
                    if len(parts) > 0:
                        num_str = parts[0].replace("session-", "")
                        if num_str.isdigit():
                            session_nums.append(int(num_str))
            if session_nums:
                session_idx = max(session_nums) + 1
        except Exception as e:
            print(f"[DEBUG LOG WARNING] Failed to calculate session index: {e}")

        # Format date-time as YYYY-MM-DD_HH-MM-SS
        ts_slug = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_user_name = "".join(c for c in user_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(" ", "_")
        base = os.path.join(LOG_DIR, f"{safe_user_name}-session-{session_idx}-{ts_slug}")

        self._jsonl_path = base + ".jsonl"
        self._txt_path   = base + ".txt"

        self._jsonl = open(self._jsonl_path, "a", encoding="utf-8")
        self._txt   = open(self._txt_path,   "a", encoding="utf-8")
        self._turn  = 0

        self._write_txt(
            f"{'='*70}\n"
            f"  Serinity — DEBUG LOG\n"
            f"  Session : {session_id}\n"
            f"  Started : {_now()}\n"
            f"{'='*70}\n\n"
        )
        self._write_jsonl("session_start", {"session_id": session_id})

    # ------------------------------------------------------------------
    # Public logging methods — called from main.py
    # ------------------------------------------------------------------

    def session_start(self, patient_id: str | None):
        self._write_jsonl("session_start", {"patient_id": patient_id})
        self._write_txt(f"[SESSION] patient_id={patient_id}\n\n")

    def user_message(self, raw_text: str, emotion: str | None = None):
        self._turn += 1
        self._write_txt(
            f"{_divider()}\n"
            f"TURN {self._turn}\n"
            f"{_divider()}\n"
            f"[USER]  {raw_text}\n"
            + (f"[VOICE] emotion={emotion}\n" if emotion and emotion not in ("neutral", "unknown", "") else "")
            + "\n"
        )
        self._write_jsonl("user_message", {
            "turn":    self._turn,
            "text":    raw_text,
            "emotion": emotion,
        })

    def safety_check(self, text: str, risk_flagged: bool):
        status = "⚠️  RISK SIGNAL DETECTED" if risk_flagged else "✅ no risk signal"
        self._write_txt(f"[SAFETY] {status}\n\n")
        self._write_jsonl("safety_check", {
            "turn":        self._turn,
            "risk_flagged": risk_flagged,
            "text_snippet": text[:100],
        })

    def llm1_decision(self, llm1_output):
        """Log LLM1's response — always called, regardless of intent."""
        intent = llm1_output.intent
        msg = llm1_output.assistant_message
        self._write_txt(
            f"[LLM1 ► intent={intent}]\n"
            f"  message : {msg[:500]}{'...' if len(msg) > 500 else ''}\n\n"
        )
        if intent == "ANALYZE" and llm1_output.clinical_summary:
            self._write_txt(
                f"  clinical_summary :\n"
                + textwrap.indent(llm1_output.clinical_summary, "    ")
                + "\n\n"
            )

        self._write_jsonl("llm1_decision", {
            "turn":             self._turn,
            "intent":           intent,
            "message":          msg,
            "clinical_summary": llm1_output.clinical_summary,
        })

    def analyze_triggered(self, retrieval_query: str, query_source: str):
        """Log that ANALYZE path started and what query was sent to ChromaDB."""
        self._write_txt(
            f"[ANALYZE TRIGGERED]\n"
            f"  query_source   : {query_source}\n"
            f"  retrieval_query:\n"
            + textwrap.indent(retrieval_query, "    ")
            + "\n\n"
        )
        self._write_jsonl("analyze_triggered", {
            "turn":            self._turn,
            "query_source":    query_source,
            "retrieval_query": retrieval_query,
        })

    def retrieved_context(self, context_text: str):
        """Log a snippet of the retrieved ChromaDB context."""
        docs = context_text.split("\n\n") if context_text else []
        num_docs = len(docs)
        snippet_lines = []
        for i, doc in enumerate(docs[:_MAX_DOCS_LOGGED]):
            truncated = doc[:_CTX_SNIPPET_LEN] + ("..." if len(doc) > _CTX_SNIPPET_LEN else "")
            snippet_lines.append(f"  [{i+1}] {truncated}")
        snippet_block = "\n".join(snippet_lines) if snippet_lines else "  (no context retrieved)"

        self._write_txt(
            f"[RETRIEVED CONTEXT — {num_docs} doc(s)]\n"
            + snippet_block
            + ("\n  ..." if num_docs > _MAX_DOCS_LOGGED else "")
            + "\n\n"
        )
        self._write_jsonl("retrieved_context", {
            "turn":             self._turn,
            "num_docs":         num_docs,
            "context_snippet":  context_text[:800],
        })

    def llm2_output(self, llm2_response):
        """Log the full LLM2 analysis output."""
        self._write_txt(
            f"[LLM2 — CLINICAL ANALYSIS]\n"
            f"  emotional_themes       : {llm2_response.emotional_themes}\n"
            f"  thinking_patterns      : {llm2_response.thinking_patterns}\n"
            f"  behavioral_patterns    : {llm2_response.behavioral_patterns}\n"
            f"  interpersonal_dynamics : {llm2_response.interpersonal_dynamics}\n"
            f"  stressors              : {llm2_response.stressors}\n"
            f"  unclear_areas          : {llm2_response.unclear_areas}\n"
            f"  protective_factors     : {llm2_response.protective_factors}\n"
            f"  risk_assessment        : {llm2_response.risk_assessment}\n"
            f"\n"
        )
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
        msg = llm1_output.assistant_message
        self._write_txt(
            f"[LLM1 ► post-ANALYZE synthesis]\n"
            f"  message : {msg[:300]}{'...' if len(msg) > 300 else ''}\n\n"
        )
        self._write_jsonl("llm1_final", {
            "turn":    self._turn,
            "message": msg,
        })

    def assistant_reply(self, message: str, risk_injected: bool):
        """Log the final message sent back to the user."""
        self._write_txt(
            f"[ASSISTANT → USER]\n"
            + textwrap.indent(message[:400] + ("..." if len(message) > 400 else ""), "  ")
            + ("\n  [⚠️  Crisis resources injected]" if risk_injected else "")
            + "\n\n"
        )
        self._write_jsonl("assistant_reply", {
            "turn":           self._turn,
            "message":        message,
            "risk_injected":  risk_injected,
        })

    def error(self, context: str, exc: Exception):
        self._write_txt(f"[ERROR in {context}] {type(exc).__name__}: {exc}\n\n")
        self._write_jsonl("error", {
            "turn":      self._turn,
            "context":   context,
            "exception": f"{type(exc).__name__}: {exc}",
        })

    def close(self):
        if hasattr(self, "_txt") and not self._txt.closed:
            self._write_txt(f"\n{'='*70}\n  SESSION END — {_now()}\n{'='*70}\n")
            self._txt.close()
        if hasattr(self, "_jsonl") and not self._jsonl.closed:
            self._jsonl.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_jsonl(self, event: str, data: dict):
        record = {"ts": _now(), "event": event, **data}
        self._jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._jsonl.flush()

    def _write_txt(self, text: str):
        self._txt.write(text)
        self._txt.flush()


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
