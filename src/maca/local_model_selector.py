"""Memory-aware local Gemma 4 model selector for Ollama."""

import argparse
import ctypes
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

OS_HEADROOM_GB: float = 10.0
DEFAULT_KV_CACHE_TYPE: str = "q8_0"
DEFAULT_FLASH_ATTENTION: bool = True
DEFAULT_OVERRIDE_NUM_CTX: int = 16384

MODEL_Q8_26B: str = "gemma4:26b-a4b-it-q8_0"
MODEL_Q4_26B: str = "gemma4:26b"
MODEL_REAP_Q3_26B: str = "hf.co/crucible-labs/Gemma4-26B-A4B-REAP-25-GGUF:Q3_K-mixed"
MODEL_E4B: str = "gemma4:e4b"
MODEL_E2B: str = "gemma4:e2b"

BYTES_PER_GIB: float = float(1024**3)


@dataclass(frozen=True)
class LocalModelSelection:
    """Resolved local Ollama Gemma 4 model and runtime tuning configuration."""

    total_memory_gb: Optional[float]
    os_headroom_gb: float
    model_budget_gb: float
    model: str
    num_ctx: int
    kv_cache_type: str
    flash_attention: bool
    tier: str
    reason: str
    overridden: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize selection details to a plain JSON-compatible dictionary."""
        return {
            "total_memory_gb": self.total_memory_gb,
            "os_headroom_gb": self.os_headroom_gb,
            "model_budget_gb": self.model_budget_gb,
            "model": self.model,
            "num_ctx": self.num_ctx,
            "kv_cache_type": self.kv_cache_type,
            "flash_attention": self.flash_attention,
            "tier": self.tier,
            "reason": self.reason,
            "overridden": self.overridden,
        }


class _MemoryStatusEx(ctypes.Structure):
    """Win32 MEMORYSTATUSEX structure for GlobalMemoryStatusEx."""

    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _detect_windows_memory_bytes() -> Optional[int]:
    """Detect total physical RAM on Windows via GlobalMemoryStatusEx."""
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        return None
    try:
        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        if windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total = int(status.ullTotalPhys)
            return total if total > 0 else None
    except Exception:
        return None
    return None


def _detect_proc_meminfo_bytes(proc_meminfo: Path = Path("/proc/meminfo")) -> Optional[int]:
    """Detect total physical RAM on Linux by reading /proc/meminfo."""
    try:
        if not proc_meminfo.is_file():
            return None
        with open(proc_meminfo, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        kb_val = int(parts[1])
                        return kb_val * 1024 if kb_val > 0 else None
    except Exception:
        return None
    return None


def _detect_sysconf_memory_bytes() -> Optional[int]:
    """Detect total physical RAM on POSIX systems via os.sysconf."""
    sysconf = getattr(os, "sysconf", None)
    if not callable(sysconf):
        return None
    try:
        page_size = int(sysconf("SC_PAGE_SIZE"))
        phys_pages = int(sysconf("SC_PHYS_PAGES"))
        if page_size > 0 and phys_pages > 0:
            return page_size * phys_pages
    except Exception:
        return None
    return None


def _detect_sysctl_memory_bytes() -> Optional[int]:
    """Fallback physical RAM detection via sysctl hw.memsize on Unix systems."""
    sysctl_exe = shutil.which("sysctl")
    if not sysctl_exe:
        return None
    try:
        res = subprocess.run(
            [sysctl_exe, "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            mem_bytes = int(res.stdout.strip())
            return mem_bytes if mem_bytes > 0 else None
    except Exception:
        return None
    return None


def detect_total_memory_gb() -> Optional[float]:
    """Detect total system physical memory in GiB across Windows, Linux, and Unix."""
    mem_bytes: Optional[int] = None
    if os.name == "nt" or sys.platform == "win32":
        mem_bytes = _detect_windows_memory_bytes()
    else:
        mem_bytes = _detect_proc_meminfo_bytes()
        if mem_bytes is None:
            mem_bytes = _detect_sysconf_memory_bytes()
        if mem_bytes is None:
            mem_bytes = _detect_sysctl_memory_bytes()

    if mem_bytes is None or mem_bytes <= 0:
        return None
    return round(mem_bytes / BYTES_PER_GIB, 2)


def _select_tier(total_memory_gb: Optional[float], headroom_gb: float) -> LocalModelSelection:
    """Select the optimal Gemma 4 tier while reserving OS headroom."""
    if total_memory_gb is None:
        return LocalModelSelection(
            total_memory_gb=None,
            os_headroom_gb=headroom_gb,
            model_budget_gb=0.0,
            model=MODEL_E2B,
            num_ctx=8192,
            kv_cache_type=DEFAULT_KV_CACHE_TYPE,
            flash_attention=DEFAULT_FLASH_ATTENTION,
            tier="unknown_fallback",
            reason="Unable to detect system memory; defaulting to lightweight gemma4:e2b.",
            overridden=False,
        )

    total_rounded = round(float(total_memory_gb), 2)
    budget_gb = round(max(0.0, total_rounded - headroom_gb), 2)
    effective_total = total_rounded - (headroom_gb - OS_HEADROOM_GB)

    if effective_total >= 40.0:
        return LocalModelSelection(
            total_memory_gb=total_rounded,
            os_headroom_gb=headroom_gb,
            model_budget_gb=budget_gb,
            model=MODEL_Q8_26B,
            num_ctx=32768,
            kv_cache_type=DEFAULT_KV_CACHE_TYPE,
            flash_attention=DEFAULT_FLASH_ATTENTION,
            tier=">=40GB",
            reason=">=40 GB tier: selects gemma4:26b-a4b-it-q8_0 (~28 GB) with 32K context.",
            overridden=False,
        )
    if effective_total >= 28.0:
        return LocalModelSelection(
            total_memory_gb=total_rounded,
            os_headroom_gb=headroom_gb,
            model_budget_gb=budget_gb,
            model=MODEL_Q4_26B,
            num_ctx=16384,
            kv_cache_type=DEFAULT_KV_CACHE_TYPE,
            flash_attention=DEFAULT_FLASH_ATTENTION,
            tier="28-39GB",
            reason="28-39 GB tier: selects gemma4:26b (Q4_K_M, ~16 GB) with 16K context.",
            overridden=False,
        )
    if effective_total >= 16.0:
        ctx_len = 16384 if effective_total >= 18.0 else 8192
        return LocalModelSelection(
            total_memory_gb=total_rounded,
            os_headroom_gb=headroom_gb,
            model_budget_gb=budget_gb,
            model=MODEL_REAP_Q3_26B,
            num_ctx=ctx_len,
            kv_cache_type=DEFAULT_KV_CACHE_TYPE,
            flash_attention=DEFAULT_FLASH_ATTENTION,
            tier="16-27GB",
            reason=(
                f"16-27 GB tier: selects Gemma4-26B-A4B-REAP-25 Q3_K-mixed (~10.3 GB) "
                f"with {ctx_len} context."
            ),
            overridden=False,
        )
    if effective_total >= 12.0:
        return LocalModelSelection(
            total_memory_gb=total_rounded,
            os_headroom_gb=headroom_gb,
            model_budget_gb=budget_gb,
            model=MODEL_E4B,
            num_ctx=8192,
            kv_cache_type=DEFAULT_KV_CACHE_TYPE,
            flash_attention=DEFAULT_FLASH_ATTENTION,
            tier="12-15GB",
            reason="12-15 GB tier: selects gemma4:e4b (~5 GB) with 8K context.",
            overridden=False,
        )

    return LocalModelSelection(
        total_memory_gb=total_rounded,
        os_headroom_gb=headroom_gb,
        model_budget_gb=budget_gb,
        model=MODEL_E2B,
        num_ctx=8192,
        kv_cache_type=DEFAULT_KV_CACHE_TYPE,
        flash_attention=DEFAULT_FLASH_ATTENTION,
        tier="<12GB",
        reason="<12 GB tier: selects gemma4:e2b (~4 GB) with 8K context.",
        overridden=False,
    )


def select_gemma_model(
    total_memory_gb: Optional[float] = None,
    headroom_gb: float = OS_HEADROOM_GB,
    override_model: Optional[str] = None,
) -> LocalModelSelection:
    """Choose the best local Gemma 4 model on Ollama for available system RAM."""
    effective_headroom = round(max(0.0, float(headroom_gb)), 2)
    if total_memory_gb is None:
        detected_memory = detect_total_memory_gb()
    else:
        detected_memory = float(total_memory_gb)
    tier_selection = _select_tier(detected_memory, effective_headroom)

    override_clean = (override_model or "").strip()
    if override_clean:
        override_ctx = (
            tier_selection.num_ctx
            if tier_selection.total_memory_gb is not None
            else DEFAULT_OVERRIDE_NUM_CTX
        )
        return LocalModelSelection(
            total_memory_gb=tier_selection.total_memory_gb,
            os_headroom_gb=tier_selection.os_headroom_gb,
            model_budget_gb=tier_selection.model_budget_gb,
            model=override_clean,
            num_ctx=override_ctx,
            kv_cache_type=DEFAULT_KV_CACHE_TYPE,
            flash_attention=DEFAULT_FLASH_ATTENTION,
            tier="override",
            reason=f"Explicit model override requested: {override_clean}.",
            overridden=True,
        )

    return tier_selection


def default_local_model_config_path() -> Path:
    """Return the path to the persisted local model env config file."""
    override_path = os.environ.get("MACA_LOCAL_MODEL_CONFIG", "").strip()
    if override_path:
        return Path(override_path).expanduser()
    return Path.home() / ".maca" / "local_model.env"


def write_local_model_config(
    selection: LocalModelSelection,
    path: Optional[Union[str, Path]] = None,
) -> Path:
    """Persist the selected local Ollama model and tuning settings as UTF-8 KEY=VALUE."""
    target = Path(path).expanduser() if path is not None else default_local_model_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    total_str = (
        f"{selection.total_memory_gb:.2f}" if selection.total_memory_gb is not None else "unknown"
    )
    lines = [
        "# Auto-generated by maca.local_model_selector",
        f"OLLAMA_MODEL={selection.model}",
        f"OLLAMA_NUM_CTX={selection.num_ctx}",
        f"OLLAMA_KV_CACHE_TYPE={selection.kv_cache_type}",
        f"OLLAMA_FLASH_ATTENTION={'1' if selection.flash_attention else '0'}",
        f"MACA_TOTAL_MEMORY_GB={total_str}",
        f"MACA_OS_HEADROOM_GB={selection.os_headroom_gb:.2f}",
        f"MACA_MODEL_BUDGET_GB={selection.model_budget_gb:.2f}",
    ]
    with open(target, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return target


def load_local_model_config(path: Optional[Union[str, Path]] = None) -> Dict[str, str]:
    """Load persisted UTF-8 KEY=VALUE local model settings, returning {} if absent."""
    target = Path(path).expanduser() if path is not None else default_local_model_config_path()
    if not target.is_file():
        return {}
    values: Dict[str, str] = {}
    try:
        with open(target, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                    val = val[1:-1]
                if key:
                    values[key] = val
    except OSError:
        return {}
    return values


def format_selection_shell(selection: LocalModelSelection) -> str:
    """Format a selection as safe POSIX shell variable assignments."""
    total_str = (
        f"{selection.total_memory_gb:.1f}" if selection.total_memory_gb is not None else "unknown"
    )
    pairs = [
        ("SELECTED_OLLAMA_MODEL", selection.model),
        ("SELECTED_OLLAMA_NUM_CTX", str(selection.num_ctx)),
        ("SELECTED_OLLAMA_KV_CACHE_TYPE", selection.kv_cache_type),
        ("SELECTED_OLLAMA_FLASH_ATTENTION", "1" if selection.flash_attention else "0"),
        ("SELECTED_TOTAL_MEM_GB", total_str),
        ("SELECTED_OS_HEADROOM_GB", f"{selection.os_headroom_gb:.1f}"),
        ("SELECTED_MODEL_BUDGET_GB", f"{selection.model_budget_gb:.1f}"),
    ]
    return "\n".join(f"{k}={shlex.quote(v)}" for k, v in pairs)


def format_selection_human(selection: LocalModelSelection) -> str:
    """Format a selection as a concise human-readable summary."""
    total_str = (
        f"{selection.total_memory_gb:.1f} GB"
        if selection.total_memory_gb is not None
        else "unknown"
    )
    return "\n".join(
        [
            f"Detected Total Memory : {total_str}",
            f"Reserved OS Headroom  : {selection.os_headroom_gb:.1f} GB",
            f"Model Memory Budget   : {selection.model_budget_gb:.1f} GB",
            f"Selected Tier         : {selection.tier}",
            f"Selected Gemma Model  : {selection.model}",
            f"Context Length        : {selection.num_ctx}",
            f"KV Cache Type         : {selection.kv_cache_type}",
            f"Flash Attention       : {'enabled' if selection.flash_attention else 'disabled'}",
            f"Reason                : {selection.reason}",
        ]
    )


def _parse_headroom_default() -> float:
    raw = os.environ.get("MACA_OS_HEADROOM_GB", "").strip()
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return OS_HEADROOM_GB


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for hardware memory detection and Gemma 4 model selection."""
    parser = argparse.ArgumentParser(
        description="Select the optimal local Ollama Gemma 4 model based on system memory."
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Explicit Ollama model override (also respects OLLAMA_MODEL env var).",
    )
    parser.add_argument(
        "--memory-gb",
        type=float,
        default=None,
        help="Override detected total system memory in GB.",
    )
    parser.add_argument(
        "--headroom-gb",
        type=float,
        default=_parse_headroom_default(),
        help="Memory in GB reserved for the OS and other applications (default: 10.0).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "shell", "human"],
        default="human",
        help="Output format (default: human).",
    )
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="Persist selected model settings to the local model config file.",
    )
    parser.add_argument(
        "--config-path",
        default=None,
        help="Custom path for persisting local model config when --write-config is set.",
    )
    args = parser.parse_args(argv)

    override_model = args.model
    if not override_model:
        override_model = os.environ.get("OLLAMA_MODEL", "").strip() or None

    selection = select_gemma_model(
        total_memory_gb=args.memory_gb,
        headroom_gb=args.headroom_gb,
        override_model=override_model,
    )

    if args.write_config:
        write_local_model_config(selection, path=args.config_path)

    if args.format == "json":
        print(json.dumps(selection.to_dict(), indent=2))
    elif args.format == "shell":
        print(format_selection_shell(selection))
    else:
        print(format_selection_human(selection))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
