import os
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

HistoryEntry = Union[str, Dict[str, Any]]

DEFAULT_RECENT_TURNS = 3
DEFAULT_MAX_SUMMARY_CHARS = 1200
_MAX_SINGLE_BULLET_CHARS = 220
_SUMMARY_HEADER_PREFIX = "Compacted history summary"

_URL_RE = re.compile(r"https?://\S+")
_KNOWN_EXTENSIONS = (
    r"py|pyi|js|jsx|ts|tsx|java|kt|kts|go|rs|rb|php|c|cc|cpp|h|hpp|cs|swift|"
    r"md|txt|rst|json|ya?ml|toml|ini|cfg|conf|xml|html|css|scss|sql|sh|bash|zsh|"
    r"gradle|properties|todo|env|lock"
)
_FILE_PATH_RE = re.compile(
    r"(?<![\w/@])"
    rf"((?:\.?\.?/)?(?:[\w.-]+/)*(?:\.?[\w-]+(?:\.[\w-]+)*)\.(?:{_KNOWN_EXTENSIONS}))"
    r"(?![\w/])"
)
_CONSTRAINT_RE = re.compile(
    r"\b(?:must not|must|do not|don't|never|constraint|constraints|"
    r"require|required|requires|avoid|without|strictly|cannot|forbid|forbidden|only)\b",
    re.IGNORECASE,
)
_DECISION_RE = re.compile(
    r"\b(?:decided|decision|approved|rejected|selected|chose|chosen|"
    r"resolved|switched to|revision_failed|revisions requested)\b",
    re.IGNORECASE,
)


def get_recent_turns_limit(default: int = DEFAULT_RECENT_TURNS) -> int:
    """Return the configured number of recent turns to retain verbatim."""
    raw = os.environ.get("MACA_HISTORY_RECENT_TURNS", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _normalize_whitespace(text: str) -> str:
    """Collapse internal newlines and repeated whitespace into single spaces."""
    return " ".join(text.split())


def _truncate_text(text: str, max_len: int) -> str:
    """Truncate text cleanly within max_len, preferring word boundaries."""
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    cutoff = max_len - 3
    clipped = text[:cutoff]
    last_space = clipped.rfind(" ")
    if last_space >= int(cutoff * 0.6):
        clipped = clipped[:last_space]
    clipped = clipped.rstrip(" ,;:-")
    if not clipped:
        clipped = text[:cutoff].rstrip()
    return f"{clipped}..."


def _extract_text_and_role(entry: HistoryEntry) -> Tuple[str, str]:
    """Normalize a string or dict history entry into (role, text)."""
    if isinstance(entry, dict):
        role = str(entry.get("role", "")).strip().lower()
        content = entry.get("content")
        if content is None:
            content = entry.get("text")
        if content is None:
            content = entry.get("message", "")
        return role, str(content).strip()
    return "", str(entry).strip()


def _extract_file_paths(text: str) -> List[str]:
    """Extract unique file paths referenced in text while ignoring URLs."""
    cleaned = _URL_RE.sub(" ", text)
    seen: List[str] = []
    for match in _FILE_PATH_RE.finditer(cleaned):
        path = match.group(1)
        if path not in seen:
            seen.append(path)
    return seen


def _extract_constraint_clauses(text: str) -> List[str]:
    """Extract concise lines or sentences expressing explicit constraints."""
    clauses: List[str] = []
    for raw_line in text.splitlines():
        line = _normalize_whitespace(raw_line).lstrip("-* ").strip()
        if not line or not _CONSTRAINT_RE.search(line):
            continue
        if len(line) <= _MAX_SINGLE_BULLET_CHARS:
            clauses.append(line)
        else:
            for sentence in re.split(r"(?<=[.!?])\s+", line):
                sentence = sentence.strip()
                if sentence and _CONSTRAINT_RE.search(sentence):
                    clauses.append(sentence)
    return clauses


def _strip_prefix(text: str, prefix: str) -> str:
    """Strip a case-insensitive leading prefix and surrounding whitespace."""
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix) :].strip()
    return text.strip()


def _dedupe_bullets(bullets: Sequence[str]) -> List[str]:
    """Deduplicate bullets case-insensitively while preserving order."""
    result: List[str] = []
    seen: Set[str] = set()
    for bullet in bullets:
        key = bullet.lower()
        if key not in seen:
            seen.add(key)
            result.append(bullet)
    return result


def _ingest_prior_summary(
    raw_text: str,
    user_bullets: List[str],
    constraint_bullets: List[str],
    decision_bullets: List[str],
    other_bullets: List[str],
) -> None:
    """Re-ingest bullets from an already-compacted rolling summary entry."""
    for line in raw_text.splitlines()[1:]:
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        lower = stripped.lower()
        if lower.startswith("- referenced files:"):
            continue
        if lower.startswith("- user request:"):
            user_bullets.append(stripped)
        elif lower.startswith("- constraint:"):
            constraint_bullets.append(stripped)
        elif lower.startswith(
            ("- decision:", "- reviewer decision:", "- plan:", "- files changed:")
        ):
            decision_bullets.append(stripped)
        else:
            other_bullets.append(stripped)


def _build_rolling_summary(older: Sequence[HistoryEntry], max_summary_chars: int) -> str:
    """Deterministically summarize older history turns within max_summary_chars."""
    if max_summary_chars <= 0:
        return ""

    user_bullets: List[str] = []
    constraint_bullets: List[str] = []
    decision_bullets: List[str] = []
    other_bullets: List[str] = []
    referenced_files: List[str] = []

    for entry in older:
        role, raw_text = _extract_text_and_role(entry)
        if not raw_text:
            continue

        for path in _extract_file_paths(raw_text):
            if path not in referenced_files:
                referenced_files.append(path)

        summary_prefixes = (_SUMMARY_HEADER_PREFIX, f"[{_SUMMARY_HEADER_PREFIX}")
        if raw_text.startswith(summary_prefixes):
            _ingest_prior_summary(
                raw_text, user_bullets, constraint_bullets, decision_bullets, other_bullets
            )
            continue

        lower_text = raw_text.lower()
        compact_text = _normalize_whitespace(raw_text)

        if role == "user" or lower_text.startswith("user request:"):
            body = _normalize_whitespace(_strip_prefix(raw_text, "user request:"))
            if body:
                clipped = _truncate_text(body, _MAX_SINGLE_BULLET_CHARS)
                user_bullets.append(f"- User request: {clipped}")
            if len(body) > _MAX_SINGLE_BULLET_CHARS:
                for clause in _extract_constraint_clauses(raw_text):
                    clipped = _truncate_text(clause, _MAX_SINGLE_BULLET_CHARS)
                    constraint_bullets.append(f"- Constraint: {clipped}")
        elif role == "system":
            clipped = _truncate_text(compact_text, _MAX_SINGLE_BULLET_CHARS)
            constraint_bullets.append(f"- Constraint: {clipped}")
        elif lower_text.startswith("reviewer decision:"):
            body = _normalize_whitespace(_strip_prefix(raw_text, "reviewer decision:"))
            clipped = _truncate_text(body, _MAX_SINGLE_BULLET_CHARS)
            decision_bullets.append(f"- Reviewer decision: {clipped}")
        elif lower_text.startswith("decision:"):
            body = _normalize_whitespace(_strip_prefix(raw_text, "decision:"))
            clipped = _truncate_text(body, _MAX_SINGLE_BULLET_CHARS)
            decision_bullets.append(f"- Decision: {clipped}")
        elif lower_text.startswith("planner implementation steps:"):
            step_lines = [
                _normalize_whitespace(ln) for ln in raw_text.splitlines()[1:] if ln.strip()
            ]
            if step_lines:
                steps_text = "; ".join(step_lines)
            else:
                steps_text = _strip_prefix(compact_text, "planner implementation steps:")
            if steps_text:
                clipped = _truncate_text(steps_text, _MAX_SINGLE_BULLET_CHARS)
                decision_bullets.append(f"- Plan: {clipped}")
        elif lower_text.startswith(("files modified/created:", "files created/modified")):
            _, _, remainder = raw_text.partition(":")
            body = _normalize_whitespace(remainder)
            if body:
                clipped = _truncate_text(body, _MAX_SINGLE_BULLET_CHARS)
                decision_bullets.append(f"- Files changed: {clipped}")
        else:
            if _DECISION_RE.search(compact_text):
                clipped = _truncate_text(compact_text, _MAX_SINGLE_BULLET_CHARS)
                decision_bullets.append(f"- Decision: {clipped}")
            elif _CONSTRAINT_RE.search(compact_text):
                clipped = _truncate_text(compact_text, _MAX_SINGLE_BULLET_CHARS)
                constraint_bullets.append(f"- Constraint: {clipped}")
            else:
                label = role.capitalize() if role else "Context"
                clipped = _truncate_text(compact_text, _MAX_SINGLE_BULLET_CHARS)
                other_bullets.append(f"- {label}: {clipped}")
            if len(compact_text) > _MAX_SINGLE_BULLET_CHARS:
                for clause in _extract_constraint_clauses(raw_text):
                    clipped = _truncate_text(clause, _MAX_SINGLE_BULLET_CHARS)
                    constraint_bullets.append(f"- Constraint: {clipped}")

    ordered_bullets = _dedupe_bullets(
        user_bullets + constraint_bullets + decision_bullets + other_bullets
    )
    turn_label = "turn" if len(older) == 1 else "turns"
    header = f"{_SUMMARY_HEADER_PREFIX} ({len(older)} earlier {turn_label}):"
    files_bullet = f"- Referenced files: {', '.join(referenced_files)}" if referenced_files else ""

    if len(header) >= max_summary_chars:
        return _truncate_text(header, max_summary_chars)

    remaining = max_summary_chars - len(header)
    reserved_files_line = ""
    if files_bullet and remaining > 1:
        if ordered_bullets and remaining >= 80:
            files_budget = min(len(files_bullet), max(40, remaining // 2))
        else:
            files_budget = min(len(files_bullet), remaining - 1)
        if files_budget >= 10:
            reserved_files_line = _truncate_text(files_bullet, files_budget)

    files_cost = len(reserved_files_line) + 1 if reserved_files_line else 0
    bullet_budget = remaining - files_cost
    chosen_bullets: List[str] = []
    for bullet in ordered_bullets:
        needed = 1 + len(bullet)
        if needed <= bullet_budget:
            chosen_bullets.append(bullet)
            bullet_budget -= needed
        elif bullet_budget >= 20:
            chosen_bullets.append(_truncate_text(bullet, bullet_budget - 1))
            bullet_budget = 0
            break
        else:
            break

    if files_bullet and reserved_files_line and bullet_budget > 0:
        if len(reserved_files_line) < len(files_bullet):
            expanded_budget = min(len(files_bullet), len(reserved_files_line) + bullet_budget)
            reserved_files_line = _truncate_text(files_bullet, expanded_budget)

    lines: List[str] = [header] + chosen_bullets
    if reserved_files_line:
        lines.append(reserved_files_line)

    summary = "\n".join(lines)
    if len(summary) > max_summary_chars:
        return _truncate_text(summary, max_summary_chars)
    return summary


class HistoryCompactor:
    """Deterministically compacts older conversation turns into a bounded rolling summary."""

    def __init__(
        self,
        max_recent: Optional[int] = None,
        max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
    ) -> None:
        self.max_recent = max_recent
        self.max_summary_chars = max_summary_chars

    def compact(
        self,
        history: Sequence[HistoryEntry],
        max_recent: Optional[int] = None,
        max_summary_chars: Optional[int] = None,
    ) -> Tuple[List[HistoryEntry], str]:
        """Compact older entries while retaining the most recent turns verbatim."""
        effective_recent = max_recent if max_recent is not None else self.max_recent
        effective_chars = (
            max_summary_chars if max_summary_chars is not None else self.max_summary_chars
        )
        return compact_conversation_history(
            history,
            max_recent=effective_recent,
            max_summary_chars=effective_chars,
        )


def compact_conversation_history(
    history: Sequence[HistoryEntry],
    max_recent: Optional[int] = None,
    max_summary_chars: int = DEFAULT_MAX_SUMMARY_CHARS,
) -> Tuple[List[HistoryEntry], str]:
    """Compact conversation history into a rolling summary plus recent verbatim turns.

    Supports both string-based histories (``List[str]``) and message-dict histories
    (``List[Dict[str, Any]]`` with ``role``/``content`` keys), matching the input shape
    in the prepended synthetic summary entry.
    """
    effective_max_recent = get_recent_turns_limit() if max_recent is None else max(0, max_recent)
    if len(history) <= effective_max_recent:
        return list(history), ""

    if effective_max_recent == 0:
        older: Sequence[HistoryEntry] = history
        recent: Sequence[HistoryEntry] = []
    else:
        older = history[:-effective_max_recent]
        recent = history[-effective_max_recent:]

    summary_text = _build_rolling_summary(older, max_summary_chars=max_summary_chars)
    if not summary_text:
        return list(recent), ""

    is_dict_history = all(isinstance(item, dict) for item in history)
    synthetic_entry: HistoryEntry
    if is_dict_history:
        synthetic_entry = {"role": "system", "content": summary_text}
    else:
        synthetic_entry = summary_text

    compacted: List[HistoryEntry] = [synthetic_entry] + list(recent)
    return compacted, summary_text
