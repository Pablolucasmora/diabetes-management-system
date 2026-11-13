"""Claude API adapter of the assistant for logging meals (code_conventions.md
§8.5–§8.9, §8.12).

One operation: send the conversation and get one answer of the model. The
tool loop, the tools and what is stored live in services/assistant.py.

- Timeout: ASSISTANT_TIMEOUT_SECONDS per call (§8.6).
- Retries (§8.7, §8.8): the SDK's own, twice, with exponential backoff and
  `Retry-After`, only on 408, 409, 429, 5xx and network errors. Sending a
  message writes nothing on the provider's side, so repeating it is safe.
- Errors: any failure becomes ExternalServiceError with an internal reason
  (`assistant_timeout`, `assistant_rate_limited`...), never the provider's
  message. It never logs: its caller logs once (§8.3).
- Thinking is adaptive (the model's default) with `drop_block`: a stored photo
  is replaced by a text marker, which changes the history the earlier thinking
  blocks were bound to, and the API drops them instead of rejecting the call.
- Refusals: server-side fallback to the model the API chooses (`fallbacks:
  "default"`). A refusal of the whole chain is an answer with no text.
"""

import time
from dataclasses import dataclass

import anthropic

from DayBetes_food.config import (
    ANTHROPIC_API_KEY,
    ASSISTANT_EFFORT,
    ASSISTANT_MODEL,
    ASSISTANT_TIMEOUT_SECONDS,
)
from DayBetes_food.domain.assistant import AssistantUsage
from DayBetes_food.errors import ExternalServiceError

# Answers are short: a sentence and the tool calls. Non-streaming requests stay
# well under the SDK's HTTP limits with this ceiling.
_MAX_TOKENS = 4096
_BETAS = ["thinking-binding-controls-2026-08-01", "server-side-fallback-2026-07-01"]
# Blocks the API returns before a mid-output fallback that cannot be sent back
# (the echo rule of server-side fallbacks): only text survives before it.
_NOT_REPLAYED_BEFORE_FALLBACK = {"thinking", "redacted_thinking", "tool_use", "server_tool_use"}

_client: anthropic.Anthropic | None = None


@dataclass(frozen=True)
class ModelAnswer:
    """One answer of the model: its content blocks, ready to be stored and sent
    back unchanged, and its usage."""

    content: list[dict]
    stop_reason: str | None
    usage: AssistantUsage


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(
            api_key=ANTHROPIC_API_KEY,
            timeout=float(ASSISTANT_TIMEOUT_SECONDS),
            max_retries=2,
        )
    return _client


def _replayable(content: list[dict]) -> list[dict]:
    """The answer's blocks as they must be sent back: after a mid-output fallback,
    the thinking and tool calls before the last `fallback` block are left out, and
    the `fallback` block stays where it was."""
    boundary = max((i for i, block in enumerate(content) if block.get("type") == "fallback"), default=-1)
    if boundary < 0:
        return content
    return [
        block
        for i, block in enumerate(content)
        if i >= boundary or block.get("type") not in _NOT_REPLAYED_BEFORE_FALLBACK
    ]


def create_answer(*, system: str, tools: list[dict], messages: list[dict]) -> ModelAnswer:
    """Send the conversation and return the model's answer.

    `system` and `tools` must be the same on every call: with them first and
    the whole request cached, every round and every later message reads them
    from the cache (§8.12, cost).

    Raises:
        ExternalServiceError: timeout, network, rate limit, an error status or an
            answer that cannot be read.
    """
    started = time.monotonic()
    try:
        response = _get_client().beta.messages.create(
            model=ASSISTANT_MODEL,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": system}],
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive", "block_binding": {"prefix_mismatch_behavior": "drop_block"}},
            output_config={"effort": ASSISTANT_EFFORT},
            cache_control={"type": "ephemeral"},
            fallbacks="default",
            betas=_BETAS,
        )
    except anthropic.APITimeoutError as exc:
        raise ExternalServiceError("assistant_timeout") from exc
    except anthropic.APIConnectionError as exc:
        raise ExternalServiceError("assistant_network_error") from exc
    except anthropic.RateLimitError as exc:
        raise ExternalServiceError("assistant_rate_limited") from exc
    except anthropic.APIStatusError as exc:
        raise ExternalServiceError(f"assistant_status_{exc.status_code}") from exc
    duration_ms = int((time.monotonic() - started) * 1000)

    try:
        content = [block.to_dict(mode="json") for block in response.content]
        usage = response.usage
        answer_usage = AssistantUsage(
            input_tokens=int(usage.input_tokens or 0),
            cache_creation_input_tokens=int(usage.cache_creation_input_tokens or 0),
            cache_read_input_tokens=int(usage.cache_read_input_tokens or 0),
            output_tokens=int(usage.output_tokens or 0),
            duration_ms=duration_ms,
            stop_reason=response.stop_reason,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise ExternalServiceError("assistant_malformed_answer") from exc
    return ModelAnswer(content=_replayable(content), stop_reason=response.stop_reason, usage=answer_usage)
