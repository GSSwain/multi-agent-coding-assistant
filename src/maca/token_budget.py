"""Pre-flight token budgeting to prevent silent local context truncation."""

import math
from dataclasses import dataclass

DEFAULT_MAX_CONTEXT_TOKENS = 16384
DEFAULT_OUTPUT_RESERVE_RATIO = 0.30
MIN_OUTPUT_RESERVE_RATIO = 0.05
MAX_OUTPUT_RESERVE_RATIO = 0.80
_CHARS_PER_TOKEN = 4
_HEAD_KEEP_RATIO = 0.60


@dataclass(frozen=True)
class TokenBudgetResult:
    """Outcome of pre-flight context token budget enforcement."""

    prompt: str
    system_instruction: str
    estimated_input_tokens: int
    input_budget_tokens: int
    max_context_tokens: int
    trimmed: bool
    warning: str


def estimate_tokens(text: str) -> int:
    """Return a fast, deterministic token estimate (~4 characters per token)."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // _CHARS_PER_TOKEN)


def _clamp_reserve_ratio(output_reserve_ratio: float) -> float:
    """Clamp completion reserve ratio safely into [0.05, 0.80]."""
    ratio = float(output_reserve_ratio)
    if math.isnan(ratio):
        return DEFAULT_OUTPUT_RESERVE_RATIO
    return min(MAX_OUTPUT_RESERVE_RATIO, max(MIN_OUTPUT_RESERVE_RATIO, ratio))


def compute_input_budget(
    max_context_tokens: int,
    output_reserve_ratio: float = DEFAULT_OUTPUT_RESERVE_RATIO,
) -> int:
    """Compute available input tokens after reserving completion headroom."""
    if max_context_tokens <= 0:
        return 0
    ratio = _clamp_reserve_ratio(output_reserve_ratio)
    reserve_tokens = int(round(max_context_tokens * ratio))
    return max(1, max_context_tokens - reserve_tokens)


def _trim_text_head_tail(text: str, max_chars: int) -> str:
    """Trim text to at most max_chars while preserving head and tail sections."""
    if max_chars <= 0:
        return ""
    text_len = len(text)
    if text_len <= max_chars:
        return text

    sample_marker = f"\n[... truncated {text_len} chars to fit context budget ...]\n"
    if max_chars < len(sample_marker):
        compact_marker = " [...] "
        if max_chars >= len(compact_marker) + 2:
            available = max_chars - len(compact_marker)
            head_chars = max(1, int(available * _HEAD_KEEP_RATIO))
            tail_chars = available - head_chars
            head = text[:head_chars]
            tail_start = text_len - tail_chars
            tail = text[tail_start:] if tail_chars > 0 else ""
            return f"{head}{compact_marker}{tail}"
        return text[:max_chars]

    available = max_chars - len(sample_marker)
    if available == 0:
        return f"\n[... truncated {text_len} chars to fit context budget ...]\n"

    head_chars = max(1, int(available * _HEAD_KEEP_RATIO))
    tail_chars = available - head_chars
    omitted_chars = text_len - head_chars - tail_chars
    marker = f"\n[... truncated {omitted_chars} chars to fit context budget ...]\n"
    head = text[:head_chars]
    tail_start = text_len - tail_chars
    tail = text[tail_start:] if tail_chars > 0 else ""
    return f"{head}{marker}{tail}"


def enforce_token_budget(
    prompt: str,
    system_instruction: str = "",
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
    output_reserve_ratio: float = DEFAULT_OUTPUT_RESERVE_RATIO,
) -> TokenBudgetResult:
    """Enforce a pre-flight input token budget on prompt and system instruction.

    When estimated input tokens fit within the computed input budget, inputs are
    returned unchanged. Otherwise, the prompt (and, in extreme cases where
    system_instruction alone exceeds the budget, the system_instruction as well)
    is head+tail trimmed with an explicit truncation marker and actionable warning.
    """
    prompt_tokens = estimate_tokens(prompt)
    system_tokens = estimate_tokens(system_instruction)
    estimated_input_tokens = prompt_tokens + system_tokens

    if max_context_tokens <= 0:
        return TokenBudgetResult(
            prompt=prompt,
            system_instruction=system_instruction,
            estimated_input_tokens=estimated_input_tokens,
            input_budget_tokens=0,
            max_context_tokens=max_context_tokens,
            trimmed=False,
            warning="",
        )

    clamped_ratio = _clamp_reserve_ratio(output_reserve_ratio)
    input_budget = compute_input_budget(max_context_tokens, clamped_ratio)

    if estimated_input_tokens <= input_budget:
        return TokenBudgetResult(
            prompt=prompt,
            system_instruction=system_instruction,
            estimated_input_tokens=estimated_input_tokens,
            input_budget_tokens=input_budget,
            max_context_tokens=max_context_tokens,
            trimmed=False,
            warning="",
        )

    if system_tokens < input_budget:
        remaining_prompt_tokens = input_budget - system_tokens
        prompt_max_chars = remaining_prompt_tokens * _CHARS_PER_TOKEN
        trimmed_prompt = _trim_text_head_tail(prompt, prompt_max_chars)
        trimmed_system = system_instruction
        warning = (
            f"Pre-flight token budget exceeded: estimated ~{estimated_input_tokens} input tokens "
            f"exceeds input budget of {input_budget} tokens "
            f"(max_context={max_context_tokens}, reserve={clamped_ratio:.0%}). "
            "Prompt was trimmed to prevent silent context truncation. "
            "Increase CONTEXT_TOKEN_BUDGET (MACA_CONTEXT_TOKEN_BUDGET) or OLLAMA_NUM_CTX "
            "to allow larger prompts."
        )
    else:
        if prompt:
            prompt_budget = min(prompt_tokens, input_budget // 2)
            system_budget = input_budget - prompt_budget
        else:
            prompt_budget = 0
            system_budget = input_budget

        system_max_chars = system_budget * _CHARS_PER_TOKEN
        prompt_max_chars = prompt_budget * _CHARS_PER_TOKEN
        trimmed_system = _trim_text_head_tail(system_instruction, system_max_chars)
        trimmed_prompt = _trim_text_head_tail(prompt, prompt_max_chars)
        trimmed_target = (
            "Both system_instruction and prompt were trimmed"
            if trimmed_prompt != prompt
            else "system_instruction was trimmed"
        )
        warning = (
            "Pre-flight token budget exceeded: system_instruction alone "
            f"(~{system_tokens} tokens) exceeds input budget of {input_budget} tokens "
            f"(total estimated ~{estimated_input_tokens}, max_context={max_context_tokens}, "
            f"reserve={clamped_ratio:.0%}). {trimmed_target} to fit context budget. "
            "Increase CONTEXT_TOKEN_BUDGET (MACA_CONTEXT_TOKEN_BUDGET) or OLLAMA_NUM_CTX "
            "to allow larger prompts."
        )

    return TokenBudgetResult(
        prompt=trimmed_prompt,
        system_instruction=trimmed_system,
        estimated_input_tokens=estimated_input_tokens,
        input_budget_tokens=input_budget,
        max_context_tokens=max_context_tokens,
        trimmed=True,
        warning=warning,
    )
