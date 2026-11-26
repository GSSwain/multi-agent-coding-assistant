import shutil
import subprocess
import sys
import urllib.request
from typing import Dict

from maca import maca_config as config
from maca.models.claude import ClaudeClient
from maca.models.gemini import GeminiClient


class BackendHealthService:
    """Probes and reports connectivity status for local and remote model backends."""

    @staticmethod
    def is_gemini_online() -> bool:
        key = config.get_gemini_api_key()
        if not key:
            return False
        if config.MOCK_GEMMA_FALLBACK:
            return True
        try:
            old_timeout = config.GEMINI_TIMEOUT
            config.GEMINI_TIMEOUT = 3
            try:
                client = GeminiClient()
                res = client.generate("Reply with only the word OK.")
                return bool(res)
            finally:
                config.GEMINI_TIMEOUT = old_timeout
        except Exception:
            return False

    @staticmethod
    def is_claude_online() -> bool:
        key = config.get_claude_api_key()
        if not key:
            return False
        if config.MOCK_GEMMA_FALLBACK:
            return True
        try:
            old_timeout = config.CLAUDE_TIMEOUT
            config.CLAUDE_TIMEOUT = 3
            try:
                client = ClaudeClient()
                res = client.generate("Reply with only the word OK.")
                return bool(res)
            finally:
                config.CLAUDE_TIMEOUT = old_timeout
        except Exception:
            return False

    @classmethod
    def check_backends_status(cls, run_handshakes: bool = False) -> Dict[str, str]:
        """Checks status of Gemma (Ollama), Gemini, and Claude backends."""
        status = {}

        # 1. Check Gemma
        gemma_url = config.OLLAMA_API_URL
        gemma_model = config.OLLAMA_MODEL
        gemma_status = "OFFLINE (Mock Mode Fallback)"

        def _detect_ollama() -> str:
            try:
                req = urllib.request.Request(f"{gemma_url}/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=2) as res:
                    if res.status in (200, 204):
                        return f"ONLINE (Ollama HTTP - {gemma_model})"
            except Exception:
                pass

            ollama_exe = shutil.which("ollama") or "ollama"
            try:
                res = subprocess.run(
                    [ollama_exe, "list"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=2,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return f"ONLINE (Ollama CLI - {gemma_model})"
            except Exception:
                pass

            try:
                if sys.platform == "win32":
                    res = subprocess.run(
                        ["tasklist", "/FI", "IMAGENAME eq ollama.exe", "/NH"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=2,
                    )
                    if res.returncode == 0 and "ollama.exe" in res.stdout.lower():
                        return f"ONLINE (Ollama Running - {gemma_model})"
                else:
                    res = subprocess.run(
                        ["pgrep", "-af", "ollama"],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=2,
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        return f"ONLINE (Ollama Running - {gemma_model})"
            except Exception:
                pass

            return "OFFLINE (Mock Mode Fallback)"

        gemma_status = _detect_ollama()
        status["Gemma"] = gemma_status

        # 2. Check Gemini
        gemini_key = config.get_gemini_api_key()
        if not gemini_key:
            status["Gemini"] = "UNCONFIGURED (Missing API Key)"
        else:
            if run_handshakes:
                try:
                    old_timeout = config.GEMINI_TIMEOUT
                    config.GEMINI_TIMEOUT = 3
                    try:
                        gemini_client = GeminiClient()
                        res = gemini_client.generate("Reply with only the word OK.")
                        if res:
                            status["Gemini"] = "ONLINE (Connected)"
                        else:
                            status["Gemini"] = f"ONLINE (Unexpected response: {res.strip()})"
                    except Exception as e:
                        status["Gemini"] = f"CONNECTION FAILED: {str(e)}"
                    finally:
                        config.GEMINI_TIMEOUT = old_timeout
                except Exception as e:
                    status["Gemini"] = f"CONNECTION FAILED: {str(e)}"
            else:
                status["Gemini"] = "CONFIGURED (Key Present)"

        # 3. Check Claude
        claude_key = config.get_claude_api_key()
        if not claude_key:
            status["Claude"] = "UNCONFIGURED (Missing API Key)"
        else:
            if run_handshakes:
                try:
                    old_timeout = config.CLAUDE_TIMEOUT
                    config.CLAUDE_TIMEOUT = 3
                    try:
                        claude_client = ClaudeClient()
                        res = claude_client.generate("Reply with only the word OK.")
                        if res:
                            status["Claude"] = "ONLINE (Connected)"
                        else:
                            status["Claude"] = f"ONLINE (Unexpected response: {res.strip()})"
                    except Exception as e:
                        status["Claude"] = f"CONNECTION FAILED: {str(e)}"
                    finally:
                        config.CLAUDE_TIMEOUT = old_timeout
                except Exception as e:
                    status["Claude"] = f"CONNECTION FAILED: {str(e)}"
            else:
                status["Claude"] = "CONFIGURED (Key Present)"

        return status
