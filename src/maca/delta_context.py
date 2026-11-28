import ast
import difflib
import os
import re
from typing import Dict, Iterable, List, Set, Tuple

_TOP_LEVEL_SYMBOL_RE = re.compile(
    r"^(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]",
    flags=re.MULTILINE,
)
_MAX_SUMMARY_SYMBOLS = 20


def _normalize_path(path: str) -> str:
    """Normalize a file path to forward slashes without leading './' or '/'."""
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _token_in_text(token: str, text: str) -> bool:
    """Return True if token appears in text at path/word boundaries (case-insensitive)."""
    if not token or not text:
        return False
    pattern = r"(?<![A-Za-z0-9_\-.])" + re.escape(token) + r"(?![A-Za-z0-9_\-]|\.[A-Za-z0-9_])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _standalone_basename_in_text(basename: str, text: str) -> bool:
    """Return True if basename appears in text without a preceding path separator."""
    if not basename or not text:
        return False
    pattern = r"(?<![A-Za-z0-9_\-./])" + re.escape(basename) + r"(?![A-Za-z0-9_\-]|\.[A-Za-z0-9_])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _extract_top_level_symbols(content: str) -> List[str]:
    """Extract top-level Python function and class names via AST with regex fallback."""
    if not content.strip():
        return []
    try:
        tree = ast.parse(content)
        symbols: List[str] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(node.name)
        return symbols
    except (SyntaxError, ValueError, TypeError):
        return [str(match.group(1)) for match in _TOP_LEVEL_SYMBOL_RE.finditer(content)]


def extract_mentioned_files(feedback: str, candidate_files: Iterable[str]) -> Set[str]:
    """Identify which candidate files are referenced by path or basename in feedback."""
    if not feedback or not feedback.strip():
        return set()

    normalized_feedback = feedback.replace("\\", "/")
    candidates = [c for c in candidate_files if c]
    if not candidates:
        return set()

    mentioned: Set[str] = set()
    matched_basenames_by_path: Set[str] = set()
    candidate_info: List[Tuple[str, str, str]] = []

    for candidate in candidates:
        norm_path = _normalize_path(candidate)
        if not norm_path:
            continue
        basename = os.path.basename(norm_path)
        candidate_info.append((candidate, norm_path, basename))
        if _token_in_text(norm_path, normalized_feedback):
            mentioned.add(candidate)
            if "/" in norm_path and basename:
                matched_basenames_by_path.add(basename.lower())

    for candidate, _, basename in candidate_info:
        if candidate in mentioned or not basename:
            continue
        if basename.lower() in matched_basenames_by_path:
            if _standalone_basename_in_text(basename, normalized_feedback):
                mentioned.add(candidate)
        elif _token_in_text(basename, normalized_feedback):
            mentioned.add(candidate)

    return mentioned


def summarize_unchanged_file(filepath: str, content: str) -> str:
    """Produce a compact single-line summary stub for an unchanged/unmentioned file."""
    line_count = len(content.splitlines())
    symbols = _extract_top_level_symbols(content)
    if symbols:
        if len(symbols) > _MAX_SUMMARY_SYMBOLS:
            displayed = ", ".join(symbols[:_MAX_SUMMARY_SYMBOLS])
            extra = len(symbols) - _MAX_SUMMARY_SYMBOLS
            symbols_str = f"{displayed}, ... (+{extra} more)"
        else:
            symbols_str = ", ".join(symbols)
    else:
        symbols_str = "none"
    return f"# [UNCHANGED SUMMARY: {filepath} | {line_count} lines | symbols: {symbols_str}]"


def build_delta_file_context(
    repo_files_content: Dict[str, str],
    generated_files: Dict[str, str],
    feedback: str,
) -> Dict[str, str]:
    """Build delta file context keeping mentioned files in full and summarizing others.

    Files referenced in ``feedback`` retain their full content (with ``generated_files``
    taking precedence over ``repo_files_content``). Unmentioned files are replaced with
    compact one-line summaries. When ``feedback`` mentions no specific files, all
    ``generated_files`` are kept in full for safety while unchanged ``repo_files_content``
    entries are summarized.
    """
    merged: Dict[str, str] = {**repo_files_content, **generated_files}
    if not merged:
        return {}

    mentioned = extract_mentioned_files(feedback, merged.keys())
    delta_context: Dict[str, str] = {}

    if mentioned:
        for filepath, content in merged.items():
            if filepath in mentioned:
                delta_context[filepath] = content
            else:
                delta_context[filepath] = summarize_unchanged_file(filepath, content)
    else:
        for filepath, content in merged.items():
            if filepath in generated_files:
                delta_context[filepath] = content
            else:
                delta_context[filepath] = summarize_unchanged_file(filepath, content)

    return delta_context


def build_targeted_diff_context(
    file_path: str,
    old_content: str,
    new_content: str,
    context_lines: int = 10,
) -> str:
    """Generate a compact unified diff when both versions exist, or full content if small/new."""
    if not old_content or not new_content:
        return new_content

    safe_context = max(0, context_lines)
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    if len(old_lines) <= safe_context and len(new_lines) <= safe_context:
        return new_content

    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
            n=safe_context,
            lineterm="",
        )
    )
    if not diff_lines:
        return summarize_unchanged_file(file_path, new_content)

    return "\n".join(diff_lines)
