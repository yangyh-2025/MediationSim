"""
Structured LLM call logger — JSONL format.

Every API call is logged with:
- Full prompt messages (system + user)
- Full raw response text
- Parsed structured output (if any)
- Agent context: name, condition, round, run_id, experiment_id
- Cache metrics (hit tokens, miss tokens)
- Timestamps and duration

Files are organized by experiment_id under data/logs/
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import config


class CallContext:
    """Per-call metadata — set by the negotiation engine before each LLM call."""

    def __init__(self) -> None:
        self.agent_name: str = ""
        self.condition_code: str = ""
        self.round_number: int = 0
        self.run_id: str = ""
        self.experiment_id: str = ""

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "condition_code": self.condition_code,
            "round_number": self.round_number,
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
        }


# Global singleton — set by engine before each call
call_context = CallContext()


class LLMLogger:
    """Thread-safe JSONL logger for LLM API calls."""

    def __init__(self, experiment_id: str) -> None:
        self.experiment_id = experiment_id
        self._lock = threading.Lock()
        self._log_dir = config.data_dir / "logs" / experiment_id
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self) -> Path:
        """Rotate daily to keep files manageable."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._log_dir / f"llm_calls_{date_str}.jsonl"

    def record(
        self,
        *,
        messages: list[dict],
        response_text: str,
        parsed_output: Any = None,
        cache_hit_tokens: int = 0,
        cache_miss_tokens: int = 0,
        model: str = "",
        temperature: float = 0.0,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "experiment_id": self.experiment_id,
            "agent_name": call_context.agent_name,
            "condition_code": call_context.condition_code,
            "round_number": call_context.round_number,
            "run_id": call_context.run_id,
            "model": model,
            "temperature": temperature,
            "duration_ms": round(duration_ms, 1),
            "cache_hit_tokens": cache_hit_tokens,
            "cache_miss_tokens": cache_miss_tokens,
            "messages": messages,
            "response_text": response_text,
            "parsed_output": parsed_output,
            "error": error,
        }
        with self._lock:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def get_stats(self) -> dict:
        """Return aggregate stats from all log files for this experiment."""
        files = sorted(self._log_dir.glob("llm_calls_*.jsonl"))
        total_calls = 0
        total_hit = 0
        total_miss = 0
        total_duration = 0.0
        errors = 0

        for fp in files:
            for line in fp.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    total_calls += 1
                    total_hit += e.get("cache_hit_tokens", 0)
                    total_miss += e.get("cache_miss_tokens", 0)
                    total_duration += e.get("duration_ms", 0)
                    if e.get("error"):
                        errors += 1
                except json.JSONDecodeError:
                    pass

        return {
            "total_calls": total_calls,
            "cache_hit_tokens": total_hit,
            "cache_miss_tokens": total_miss,
            "cache_hit_rate": round(total_hit / max(total_hit + total_miss, 1) * 100, 1),
            "total_duration_ms": round(total_duration, 0),
            "errors": errors,
            "log_files": len(files),
        }

    def export_all(self) -> list[dict]:
        """Export all log entries as a list of dicts (for API)."""
        files = sorted(self._log_dir.glob("llm_calls_*.jsonl"))
        entries: list[dict] = []
        for fp in files:
            for line in fp.read_text(encoding="utf-8").strip().split("\n"):
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return entries


# Registry of active loggers by experiment_id
_loggers: dict[str, LLMLogger] = {}


def get_logger(experiment_id: str) -> LLMLogger:
    if experiment_id not in _loggers:
        _loggers[experiment_id] = LLMLogger(experiment_id)
    return _loggers[experiment_id]
