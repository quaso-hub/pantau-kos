"""
infrastructure/logger.py  (v5.0)
GCP Cloud Logging compatible structured JSON logging with Trace ID propagation.

Features:
  - JSON structured logs (Cloud Logging compatible)
  - Trace ID from Telegram Update ID → propagated through all layers
  - Per-analysis error buffer → accessible via "View Logs" Telegram button
  - Context-aware: every log includes trace_id, component, severity

Usage:
  from infrastructure.logger import get_logger, set_trace_id, get_trace_id, get_analysis_logs

  log = get_logger("god-eye.handlers")
  set_trace_id("upd-123456")
  log.info("Processing message", extra={"chat_id": 12345})
  # Later: get_analysis_logs("upd-123456") → list of log entries
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

# ── Trace ID context var — set once per request, flows through all async calls
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="no-trace"
)

# ── Per-trace error/warning log buffer (in-memory, capped)
# Key: trace_id → list of log entry dicts
_analysis_logs: dict[str, list[dict]] = defaultdict(list)
_MAX_LOGS_PER_TRACE = 50
_MAX_TRACES = 200  # evict old traces when this is exceeded


def set_trace_id(trace_id: str) -> None:
    """Set trace ID for the current async context (call at request entry)."""
    _trace_id_var.set(trace_id)


def get_trace_id() -> str:
    """Get current trace ID."""
    return _trace_id_var.get()


def get_analysis_logs(trace_id: str) -> list[dict]:
    """Get all buffered log entries for a given trace/analysis."""
    return _analysis_logs.get(trace_id, [])


def clear_analysis_logs(trace_id: str) -> None:
    """Clear logs for a trace (after user views them)."""
    _analysis_logs.pop(trace_id, None)


def _evict_old_traces() -> None:
    """Evict oldest traces if buffer exceeds max."""
    if len(_analysis_logs) > _MAX_TRACES:
        # Remove oldest half
        keys = list(_analysis_logs.keys())
        for k in keys[: len(keys) // 2]:
            del _analysis_logs[k]


# ── GCP Cloud Logging severity mapping
_SEVERITY_MAP = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records as JSON objects compatible with GCP Cloud Logging.

    Output format:
    {
      "severity": "INFO",
      "message": "...",
      "timestamp": "2026-03-08T12:34:56.789Z",
      "logging.googleapis.com/trace": "upd-123456",
      "component": "god-eye.handlers",
      "module": "telegram_handlers",
      "function": "handle_message",
      "line": 42,
      ...extra fields...
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        trace_id = _trace_id_var.get("no-trace")

        entry = {
            "severity": _SEVERITY_MAP.get(record.levelno, "DEFAULT"),
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "logging.googleapis.com/trace": trace_id,
            "component": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Include any extra fields passed via `extra={...}`
        for key in ("chat_id", "listing_id", "agent", "phase", "attempt",
                     "duration_ms", "status_code", "error_code"):
            val = getattr(record, key, None)
            if val is not None:
                entry[key] = val

        # Buffer WARNING+ logs for the "View Logs" feature
        if record.levelno >= logging.WARNING and trace_id != "no-trace":
            _evict_old_traces()
            buf = _analysis_logs[trace_id]
            if len(buf) < _MAX_LOGS_PER_TRACE:
                buf.append({
                    "ts": entry["timestamp"],
                    "sev": entry["severity"],
                    "msg": entry["message"][:200],
                    "comp": record.name.split(".")[-1],
                    "func": record.funcName,
                })

        return json.dumps(entry, ensure_ascii=False, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    """
    Replace default logging with structured JSON logging.
    Call once at application startup (main.py).
    """
    root = logging.getLogger()
    root.setLevel(level)

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # JSON handler to stdout (Cloud Logging picks up stdout)
    json_handler = logging.StreamHandler(sys.stdout)
    json_handler.setFormatter(StructuredJsonFormatter())
    root.addHandler(json_handler)

    # Suppress noisy libraries
    for lib in ("httpx", "httpcore", "urllib3", "google.auth", "grpc"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger (convenience wrapper)."""
    return logging.getLogger(name)
