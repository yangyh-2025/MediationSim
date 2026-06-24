from __future__ import annotations

import json
import asyncio
import time
from typing import Type, Any

from openai import AsyncOpenAI, APIError, RateLimitError, APITimeoutError, APIConnectionError
from pydantic import BaseModel, ValidationError

from backend.config import config


class CacheMetrics:
    """Track prompt cache hit/miss across calls."""

    def __init__(self) -> None:
        self.total_calls: int = 0
        self.total_hit_tokens: int = 0
        self.total_miss_tokens: int = 0
        self.calls_with_hits: int = 0

    def record(self, hit_tokens: int, miss_tokens: int) -> None:
        self.total_calls += 1
        self.total_hit_tokens += hit_tokens
        self.total_miss_tokens += miss_tokens
        if hit_tokens > 0:
            self.calls_with_hits += 1

    @property
    def hit_rate(self) -> float:
        total = self.total_hit_tokens + self.total_miss_tokens
        if total == 0:
            return 0.0
        return self.total_hit_tokens / total

    @property
    def call_hit_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.calls_with_hits / self.total_calls

    @property
    def estimated_cost_saved_pct(self) -> float:
        if self.total_hit_tokens == 0:
            return 0.0
        miss_cost = (self.total_hit_tokens + self.total_miss_tokens) * 1.0
        actual = self.total_miss_tokens * 1.0 + self.total_hit_tokens * 0.02
        if miss_cost == 0:
            return 0.0
        return (1 - actual / miss_cost) * 100

    def summary(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "total_hit_tokens": self.total_hit_tokens,
            "total_miss_tokens": self.total_miss_tokens,
            "call_hit_rate": round(self.call_hit_rate * 100, 1),
            "token_hit_rate": round(self.hit_rate * 100, 1),
            "estimated_cost_saved_pct": round(self.estimated_cost_saved_pct, 1),
        }


cache_metrics = CacheMetrics()

# Global LLM concurrency limit — shared across all conditions
_llm_semaphore: asyncio.Semaphore | None = None


def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(config.llm_concurrency)
    return _llm_semaphore


class LLMClient:
    """OpenAI-compatible async LLM client with structured output, retry, cache metrics, and full logging."""

    def __init__(self, experiment_id: str = "") -> None:
        self.client = AsyncOpenAI(api_key=config.llm_api_key, base_url=config.llm_base_url)
        self.model = config.llm_model
        self.default_temperature = config.llm_temperature
        self.default_max_tokens = config.llm_max_tokens
        self.max_retries = 3
        self.experiment_id = experiment_id

    # ── Cache warming ─────────────────────────────────────

    async def warm_cache(self, system_prompt: str, schema: Type[BaseModel] | None = None) -> bool:
        try:
            kwargs: dict[str, Any] = {
                "model": self.model, "temperature": 0.0, "max_tokens": 4,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "[CACHE WARM]"},
                ],
            }
            if schema is not None:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
                }
            await self.client.chat.completions.create(**kwargs)
            return True
        except Exception:
            return False

    # ── Logging hook ──────────────────────────────────────

    def _log_call(self, messages: list[dict], response_text: str, parsed: Any,
                  hit: int, miss: int, duration_ms: float, error: str | None = None) -> None:
        try:
            from backend.llm.logger import get_logger
            logger = get_logger(self.experiment_id) if self.experiment_id else None
            if logger:
                logger.record(
                    messages=messages,
                    response_text=response_text,
                    parsed_output=parsed,
                    cache_hit_tokens=hit,
                    cache_miss_tokens=miss,
                    model=self.model,
                    temperature=self.default_temperature,
                    duration_ms=duration_ms,
                    error=error,
                )
        except Exception:
            pass  # logging failure must never break the experiment

    # ── Main chat method ──────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from LLM output, with truncation repair."""
        import re
        m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if m:
            text = m.group(1).strip()
        start = text.find('{')
        if start < 0:
            start = text.find('[')
        if start < 0:
            return text.strip()
        end = text.rfind('}') if text[start] == '{' else text.rfind(']')
        if end > start:
            return text[start:end + 1]
        # ── Truncated JSON repair ──
        json_str = text[start:]
        # Close unclosed strings
        in_string = False
        escape_next = False
        repaired = ""
        for ch in json_str:
            repaired += ch
            if escape_next:
                escape_next = False
            elif ch == '\\':
                escape_next = True
            elif ch == '"':
                in_string = not in_string
        if in_string:
            repaired += '"'
        # Close unclosed braces/brackets
        depth = 0
        for ch in repaired:
            if ch in '{[':
                depth += 1
            elif ch in '}]':
                depth -= 1
        close_stack = []
        for ch in repaired:
            if ch == '{':
                close_stack.append('}')
            elif ch == '[':
                close_stack.append(']')
            elif ch in '}]':
                if close_stack:
                    close_stack.pop()
        while close_stack:
            repaired += close_stack.pop()
        return repaired

    async def chat(
        self, messages: list[dict],
        response_schema: Type[BaseModel] | None = None,
        temperature: float | None = None, max_tokens: int | None = None,
    ) -> BaseModel | str:
        temp = temperature if temperature is not None else self.default_temperature
        max_tok = max_tokens if max_tokens is not None else self.default_max_tokens
        # DeepSeek: JSON-in-prompt generates longer output than raw text
        if response_schema is not None and max_tokens is None:
            max_tok = max_tok * 2

        # DeepSeek doesn't support response_format → schema is baked into system_prompt by BaseAgent
        msgs = list(messages)  # shallow copy — do NOT mutate caller's messages

        last_exception: Exception | None = None

        for attempt in range(self.max_retries):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model, "messages": msgs,
                    "temperature": temp, "max_tokens": max_tok,
                }
                # NO response_format — DeepSeek doesn't support it

                t0 = time.monotonic()
                async with _get_llm_semaphore():
                    response = await self.client.chat.completions.create(**kwargs)
                elapsed_ms = (time.monotonic() - t0) * 1000
                content = response.choices[0].message.content or ""

                # Cache metrics
                hit = 0; miss = 0
                if hasattr(response, "usage") and response.usage:
                    hit = getattr(response.usage, "prompt_cache_hit_tokens", 0) or 0
                    miss = (getattr(response.usage, "prompt_cache_miss_tokens", 0)
                            or response.usage.prompt_tokens - hit)
                    cache_metrics.record(hit, max(miss, 0))

                if response_schema is not None:
                    try:
                        extracted = self._extract_json(content)
                        parsed = json.loads(extracted)
                        result = response_schema.model_validate(parsed)
                        self._log_call(msgs, content, result.model_dump(), hit, max(miss, 0), elapsed_ms)
                        return result
                    except (json.JSONDecodeError, ValidationError) as e:
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        self._log_call(msgs, content, None, hit, max(miss, 0), elapsed_ms, error=f"parse_error: {str(e)[:200]}")
                        raise ValueError(
                            f"Failed to parse structured output after {self.max_retries} attempts. "
                            f"Last content (first 300 chars): {content[:300]}"
                        )
                else:
                    self._log_call(msgs, content, None, hit, max(miss, 0), elapsed_ms)
                    return content

            except RateLimitError:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(30); continue
                raise
            except (APITimeoutError, APIConnectionError):
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(5); continue
                raise
            except APIError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt); continue
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError("LLMClient.chat: unexpected retry loop exit")

    async def chat_raw(self, messages: list[dict], **kwargs: Any) -> str:
        result = await self.chat(messages, response_schema=None, **kwargs)
        assert isinstance(result, str)
        return result
