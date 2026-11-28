import ast
import os
import re
from typing import Callable, List, Optional, Set, Tuple, Union

_BINARY_EXTENSIONS: Set[str] = {
    ".7z",
    ".bin",
    ".bmp",
    ".bz2",
    ".class",
    ".db",
    ".dll",
    ".dylib",
    ".ear",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".otf",
    ".pdf",
    ".png",
    ".pyc",
    ".pyd",
    ".pyo",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".svg",
    ".tar",
    ".tgz",
    ".ttf",
    ".war",
    ".webp",
    ".woff",
    ".woff2",
    ".xz",
    ".zip",
}

_CODE_EXTENSIONS: Set[str] = {
    ".c",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".swift",
    ".ts",
    ".tsx",
}

_JS_TS_EXTENSIONS: Set[str] = {".js", ".jsx", ".ts", ".tsx"}

_CONTROL_KEYWORDS: Set[str] = {
    "await",
    "case",
    "catch",
    "do",
    "else",
    "finally",
    "for",
    "if",
    "new",
    "return",
    "switch",
    "throw",
    "try",
    "typeof",
    "while",
    "yield",
}

# JS / TS signature patterns
_JS_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+.+|(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*require\(.+\))"
)
_JS_TYPE_OR_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?"
    r"(?:class|interface|type|enum)\s+[A-Za-z_$][\w$]*"
)
_JS_FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*[A-Za-z_$][\w$]*\s*[\(<]"
)
_JS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?const\s+[A-Za-z_$][\w$]*\s*(?::[^=]+)?=\s*(?:async\s+)?"
    r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=>"
)
_JS_MODIFIER_METHOD_RE = re.compile(
    r"^\s+(?:(?:public|private|protected|static|readonly|override|async|get|set)\s+)+"
    r"([A-Za-z_$][\w$]*)\s*[\(<]"
)
_JS_PLAIN_METHOD_RE = re.compile(
    r"^\s+(?:async\s+)?([A-Za-z_$][\w$]*)\s*(?:<[^>]+>)?\s*\([^)]*\)\s*(?::\s*[^\{;]+)?\s*\{"
)

# Java signature patterns
_JAVA_PKG_IMPORT_RE = re.compile(r"^\s*(?:package\s+[\w.]+;|import\s+(?:static\s+)?[\w.*]+;)")
_JAVA_TYPE_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|abstract|final|static|sealed|non-sealed)\s+)*"
    r"(?:class|interface|enum|record)\s+[A-Za-z_]\w*"
)
_JAVA_METHOD_RE = re.compile(
    r"^\s*(?:(?:public|protected|private|static|final|abstract|synchronized|default|native)\s+)+"
    r"(?:<[^>]+>\s+)?(?:[\w.<>\[\]?]+\s+)?([A-Za-z_]\w*)\s*\("
)
_JAVA_IFACE_METHOD_RE = re.compile(
    r"^\s+([\w.<>\[\]?]+)\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*(?:throws\s+[\w.,\s]+)?;"
)

# Go signature patterns
_GO_PKG_RE = re.compile(r"^\s*package\s+[A-Za-z_]\w*")
_GO_SINGLE_IMPORT_RE = re.compile(r'^\s*import\s+(?:[A-Za-z_.]\w*\s+)?"[^"]+"')
_GO_IMPORT_BLOCK_START_RE = re.compile(r"^\s*import\s*\(\s*$")
_GO_TYPE_RE = re.compile(r"^\s*type\s+[A-Za-z_]\w*\s+")
_GO_FUNC_RE = re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?[A-Za-z_]\w*\s*(?:\[[^\]]*\])?\s*\(")

# Rust signature patterns
_RS_USE_MOD_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:use\s+|mod\s+[A-Za-z_]\w*)")
_RS_TYPE_RE = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|type)\s+[A-Za-z_]\w*")
_RS_IMPL_RE = re.compile(r"^\s*(?:unsafe\s+)?impl\b")
_RS_FN_RE = re.compile(
    r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?"
    r'(?:extern\s+"[^"]+"\s+)?fn\s+[A-Za-z_]\w*'
)

# Target vs reference classification patterns
_TARGET_TAG_RE = re.compile(
    r"\[(?:MODIFY|EDIT|UPDATE|NEW|CREATE|DELETE|REMOVE|FIX|REFACTOR)\]",
    re.IGNORECASE,
)
_EXPLICIT_EDIT_TAG_RE = re.compile(r"\[(?:MODIFY|EDIT|UPDATE)\]", re.IGNORECASE)
_TARGET_VERB_RE = re.compile(
    r"\b(?:modify|edit|update|change|rewrite|refactor|fix|patch|create|delete|remove|"
    r"add\s+to|implement\s+in)\b",
    re.IGNORECASE,
)
_REFERENCE_TAG_RE = re.compile(
    r"\[(?:REF|REFERENCE|READ|READ-ONLY|READONLY|CONTEXT)\]",
    re.IGNORECASE,
)
_REFERENCE_PHRASE_RE = re.compile(
    r"\b(?:reference|references|referencing|read-only|readonly|inspect|consult|"
    r"see|imports?\s+from|defined\s+in|for\s+context|for\s+reference)\b",
    re.IGNORECASE,
)


def _safe_unparse(node: Optional[ast.AST]) -> str:
    """Safely unparse an AST node to source text."""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _compact_expr(text: str, max_len: int = 80) -> str:
    """Collapse whitespace/newlines and bound length for inline display."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3].rstrip() + "..."


def _truncate_lines(lines: List[str], max_lines: int) -> str:
    """Truncate a list of output lines to at most max_lines lines."""
    if max_lines <= 0 or not lines:
        return ""
    if len(lines) <= max_lines:
        return "\n".join(lines)
    if max_lines == 1:
        return lines[0]
    omitted = len(lines) - (max_lines - 1)
    kept = lines[: max_lines - 1]
    kept.append(f"... ({omitted} more lines omitted)")
    return "\n".join(kept)


def _fallback_head_excerpt(source: str, max_lines: int = 40) -> str:
    """Return a concise head excerpt of raw text lines."""
    if not source or not source.strip() or max_lines <= 0:
        return ""
    raw_lines = [line.rstrip() for line in source.splitlines()]
    while raw_lines and not raw_lines[0]:
        raw_lines.pop(0)
    while raw_lines and not raw_lines[-1]:
        raw_lines.pop()
    return _truncate_lines(raw_lines, max_lines)


def _first_docstring_line(
    node: Union[ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef],
) -> str:
    """Extract the first non-empty line of an AST node's docstring."""
    doc = ast.get_docstring(node, clean=True)
    if not doc:
        return ""
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _format_constant_assign(node: ast.Assign, indent: str = "") -> str:
    """Format an UPPER_CASE constant or __all__ assignment compactly."""
    names: List[str] = []
    for target in node.targets:
        if isinstance(target, ast.Name) and (target.id.isupper() or target.id == "__all__"):
            names.append(target.id)
    if not names:
        return ""
    val_str = _compact_expr(_safe_unparse(node.value), max_len=60) or "..."
    lhs = " = ".join(names)
    return f"{indent}{lhs} = {val_str}"


def _format_function(
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
    indent: str = "",
) -> List[str]:
    """Emit a compact skeleton for a function or method definition."""
    lines: List[str] = []
    for dec in node.decorator_list:
        dec_str = _compact_expr(_safe_unparse(dec), max_len=80)
        if dec_str:
            lines.append(f"{indent}@{dec_str}")
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    args_str = _compact_expr(_safe_unparse(node.args), max_len=120)
    ret_str = ""
    if node.returns is not None:
        ret_unparsed = _compact_expr(_safe_unparse(node.returns), max_len=80)
        if ret_unparsed:
            ret_str = f" -> {ret_unparsed}"
    sig = f"{indent}{prefix}{node.name}({args_str}){ret_str}:"
    doc_line = _first_docstring_line(node)
    if doc_line:
        safe_doc = doc_line.replace('"""', "'''")
        lines.append(sig)
        lines.append(f'{indent}    """{safe_doc}"""')
        lines.append(f"{indent}    ...")
    else:
        lines.append(f"{sig} ...")
    return lines


def _format_class(node: ast.ClassDef) -> List[str]:
    """Emit a compact skeleton for a class definition and its members."""
    lines: List[str] = []
    for dec in node.decorator_list:
        dec_str = _compact_expr(_safe_unparse(dec), max_len=80)
        if dec_str:
            lines.append(f"@{dec_str}")

    bases: List[str] = []
    for base in node.bases:
        base_str = _compact_expr(_safe_unparse(base), max_len=60)
        if base_str:
            bases.append(base_str)
    for kw in node.keywords:
        kw_val = _compact_expr(_safe_unparse(kw.value), max_len=60)
        if kw.arg and kw_val:
            bases.append(f"{kw.arg}={kw_val}")
        elif kw_val:
            bases.append(f"**{kw_val}")
    bases_str = f"({', '.join(bases)})" if bases else ""
    header = f"class {node.name}{bases_str}:"

    doc_line = _first_docstring_line(node)
    body_lines: List[str] = []
    if doc_line:
        safe_doc = doc_line.replace('"""', "'''")
        body_lines.append(f'    """{safe_doc}"""')

    has_members = False
    for stmt in node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body_lines.extend(_format_function(stmt, indent="    "))
            has_members = True
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            ann = _compact_expr(_safe_unparse(stmt.annotation), max_len=60)
            if stmt.value is not None:
                val = _compact_expr(_safe_unparse(stmt.value), max_len=40)
                body_lines.append(f"    {stmt.target.id}: {ann} = {val}")
            else:
                body_lines.append(f"    {stmt.target.id}: {ann}")
            has_members = True
        elif isinstance(stmt, ast.Assign):
            const_line = _format_constant_assign(stmt, indent="    ")
            if const_line:
                body_lines.append(const_line)
                has_members = True

    if body_lines:
        lines.append(header)
        lines.extend(body_lines)
        if not has_members:
            lines.append("    ...")
    else:
        lines.append(f"{header} ...")
    return lines


def summarize_python_source(source: str) -> str:
    """Produce a compact AST skeleton of Python source code.

    Emits module docstring first line, imports, top-level constants, class
    definitions with bases/first-line docstrings/members, and function/method
    signatures with type annotations and first-line docstrings while stripping
    function bodies to ``...``. Falls back to a concise head excerpt on
    ``SyntaxError``.
    """
    if not source or not source.strip():
        return ""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return _fallback_head_excerpt(source, max_lines=40)

    lines: List[str] = []
    mod_doc = _first_docstring_line(tree)
    if mod_doc:
        safe_doc = mod_doc.replace('"""', "'''")
        lines.append(f'"""{safe_doc}"""')

    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            imp_str = _safe_unparse(stmt)
            if imp_str:
                lines.append(imp_str)
        elif isinstance(stmt, ast.Assign):
            const_line = _format_constant_assign(stmt)
            if const_line:
                lines.append(const_line)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            ann = _compact_expr(_safe_unparse(stmt.annotation), max_len=60)
            if stmt.value is not None:
                val = _compact_expr(_safe_unparse(stmt.value), max_len=60)
                lines.append(f"{stmt.target.id}: {ann} = {val}")
            else:
                lines.append(f"{stmt.target.id}: {ann}")
        elif isinstance(stmt, ast.ClassDef):
            lines.extend(_format_class(stmt))
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.extend(_format_function(stmt))

    if not lines:
        return _fallback_head_excerpt(source, max_lines=40)
    return "\n".join(lines)


def _strip_trailing_brace(line: str) -> str:
    """Remove trailing opening brace and inline body from a declaration line."""
    return re.sub(r"\s*\{.*$", "", line).rstrip()


def _summarize_js_ts(source: str) -> List[str]:
    """Extract imports, types, classes, functions, and methods from JS/TS source."""
    out: List[str] = []
    for raw_line in source.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if _JS_IMPORT_RE.match(line):
            out.append(line)
        elif _JS_TYPE_OR_CLASS_RE.match(line):
            if re.match(r"^\s*(?:export\s+)?type\s+", line):
                out.append(line)
            else:
                out.append(_strip_trailing_brace(line))
        elif _JS_FUNC_RE.match(line) or _JS_ARROW_RE.match(line):
            out.append(_strip_trailing_brace(line))
        else:
            mod_match = _JS_MODIFIER_METHOD_RE.match(line)
            if mod_match and mod_match.group(1) not in _CONTROL_KEYWORDS:
                out.append(_strip_trailing_brace(line))
                continue
            plain_match = _JS_PLAIN_METHOD_RE.match(line)
            if plain_match and plain_match.group(1) not in _CONTROL_KEYWORDS:
                out.append(_strip_trailing_brace(line))
    return out


def _summarize_java(source: str) -> List[str]:
    """Extract package, imports, type declarations, and method signatures from Java source."""
    out: List[str] = []
    for raw_line in source.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if _JAVA_PKG_IMPORT_RE.match(line):
            out.append(line)
        elif _JAVA_TYPE_RE.match(line):
            out.append(_strip_trailing_brace(line))
        else:
            before_paren = line.split("(", 1)[0]
            if "=" in before_paren:
                continue
            method_match = _JAVA_METHOD_RE.match(line)
            if method_match and method_match.group(1) not in _CONTROL_KEYWORDS:
                out.append(_strip_trailing_brace(line))
                continue
            iface_match = _JAVA_IFACE_METHOD_RE.match(line)
            if (
                iface_match
                and iface_match.group(1) not in _CONTROL_KEYWORDS
                and iface_match.group(2) not in _CONTROL_KEYWORDS
            ):
                out.append(line)
    return out


def _summarize_go(source: str) -> List[str]:
    """Extract package, imports, type definitions, and func signatures from Go source."""
    out: List[str] = []
    in_import_block = False
    for raw_line in source.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if in_import_block:
            out.append(line)
            if stripped == ")":
                in_import_block = False
            continue
        if _GO_IMPORT_BLOCK_START_RE.match(line):
            in_import_block = True
            out.append(line)
        elif _GO_PKG_RE.match(line) or _GO_SINGLE_IMPORT_RE.match(line):
            out.append(line)
        elif _GO_TYPE_RE.match(line) or _GO_FUNC_RE.match(line):
            out.append(_strip_trailing_brace(line))
    return out


def _summarize_rust(source: str) -> List[str]:
    """Extract use/mod items, type declarations, impl headers, and fn signatures from Rust."""
    out: List[str] = []
    for raw_line in source.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if _RS_USE_MOD_RE.match(line):
            out.append(line)
        elif _RS_TYPE_RE.match(line) or _RS_IMPL_RE.match(line) or _RS_FN_RE.match(line):
            out.append(_strip_trailing_brace(line))
    return out


def summarize_file_source(filepath: str, source: str, max_lines: int = 40) -> str:
    """Summarize a source file into a compact structural skeleton.

    Dispatches ``.py`` files to :func:`summarize_python_source`, extracts
    imports and symbol signatures via lightweight regex for JS/TS, Java, Go,
    and Rust files, and falls back to a concise head excerpt for other text
    files. Output is capped to ``max_lines`` lines.
    """
    if not source or not source.strip() or max_lines <= 0:
        return ""

    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".py":
        skeleton = summarize_python_source(source)
        return _truncate_lines(skeleton.splitlines(), max_lines)

    extracted: List[str] = []
    if ext in _JS_TS_EXTENSIONS:
        extracted = _summarize_js_ts(source)
    elif ext == ".java":
        extracted = _summarize_java(source)
    elif ext == ".go":
        extracted = _summarize_go(source)
    elif ext == ".rs":
        extracted = _summarize_rust(source)

    if extracted:
        return _truncate_lines(extracted, max_lines)
    return _fallback_head_excerpt(source, max_lines=max_lines)


def _is_skippable_path(filepath: str) -> bool:
    """Return True for metadata or binary files excluded from structural maps."""
    norm = filepath.replace("\\", "/")
    while norm.startswith("./"):
        norm = norm[2:]
    norm = norm.lstrip("/")
    if norm.startswith(".maca/") or "/.maca/" in norm:
        return True
    ext = os.path.splitext(norm)[1].lower()
    return ext in _BINARY_EXTENSIONS


def build_repo_map(
    repo_files: List[str],
    read_fn: Callable[[str], str],
    max_files: int = 40,
    max_chars: int = 8000,
) -> str:
    """Build a compact structural repository map across source files.

    Prioritizes recognized source code files, summarizes each via
    :func:`summarize_file_source`, and enforces ``max_files`` and
    ``max_chars`` budgets strictly.
    """
    if not repo_files or max_files <= 0 or max_chars <= 0:
        return ""

    code_files: List[str] = []
    other_files: List[str] = []
    for filepath in repo_files:
        if _is_skippable_path(filepath):
            continue
        ext = os.path.splitext(filepath)[1].lower()
        if ext in _CODE_EXTENSIONS:
            code_files.append(filepath)
        else:
            other_files.append(filepath)

    candidates = code_files + other_files
    if not candidates:
        return ""

    sections: List[str] = []
    current_len = 0
    included_files = 0
    truncated = False

    for filepath in candidates:
        if included_files >= max_files:
            truncated = True
            break
        try:
            content = read_fn(filepath)
        except Exception:
            content = ""
        if not isinstance(content, str) or not content.strip() or content.startswith("Error"):
            continue
        summary = summarize_file_source(filepath, content)
        if not summary.strip():
            continue

        section = f"### {filepath}\n{summary}"
        sep_len = 2 if sections else 0
        if current_len + sep_len + len(section) <= max_chars:
            sections.append(section)
            current_len += sep_len + len(section)
            included_files += 1
        else:
            truncated = True
            if not sections:
                marker = "\n... (truncated)"
                if max_chars > len(marker):
                    return section[: max_chars - len(marker)].rstrip() + marker
                return section[:max_chars]
            break

    if not sections:
        return ""

    result = "\n\n".join(sections)
    if truncated:
        note = "\n\n... (repository map truncated)"
        if len(result) + len(note) <= max_chars:
            result += note
    return result[:max_chars]


def classify_target_vs_reference_files(
    repo_files: List[str],
    plan: str,
    spec: str,
) -> Tuple[List[str], List[str]]:
    """Classify mentioned repository files into target (editable) vs reference (read-only).

    Files explicitly marked with modification tags (``[MODIFY]``, ``[EDIT]``,
    ``[UPDATE]``, etc.) or edit verbs are classified as targets. Files marked
    with reference tags/phrasing (or untagged when explicit edit tags are used
    elsewhere in the plan/spec) are classified as read-only references. When
    mentions are ambiguous without explicit edit/reference markers, files are
    conservatively treated as targets so edit context is never lost.
    """
    combined = f"{plan or ''}\n{spec or ''}"
    combined_lower = combined.lower()
    lines = combined.splitlines()
    has_explicit_edit_tags = bool(_EXPLICIT_EDIT_TAG_RE.search(combined))

    target_files: List[str] = []
    reference_files: List[str] = []

    for filepath in repo_files:
        fp_lower = filepath.lower()
        if not fp_lower or fp_lower not in combined_lower:
            continue

        matching_lines = [line for line in lines if fp_lower in line.lower()]
        has_target_tag = any(_TARGET_TAG_RE.search(line) for line in matching_lines)
        has_reference_tag = any(_REFERENCE_TAG_RE.search(line) for line in matching_lines)
        has_target_verb = any(_TARGET_VERB_RE.search(line) for line in matching_lines)
        has_reference_phrase = any(_REFERENCE_PHRASE_RE.search(line) for line in matching_lines)

        if has_target_tag:
            target_files.append(filepath)
        elif has_reference_tag:
            reference_files.append(filepath)
        elif has_target_verb:
            target_files.append(filepath)
        elif has_reference_phrase:
            reference_files.append(filepath)
        elif has_explicit_edit_tags:
            reference_files.append(filepath)
        else:
            target_files.append(filepath)

    return target_files, reference_files
