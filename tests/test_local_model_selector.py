import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest import mock

from maca import maca_config as config
from maca.local_model_selector import (
    MODEL_E2B,
    MODEL_E4B,
    MODEL_Q4_26B,
    MODEL_Q8_26B,
    MODEL_REAP_Q3_26B,
    OS_HEADROOM_GB,
    _detect_proc_meminfo_bytes,
    default_local_model_config_path,
    detect_total_memory_gb,
    load_local_model_config,
    main,
    select_gemma_model,
    write_local_model_config,
)
from maca.models.local_gemma import LocalGemmaClient


class TestLocalModelSelectionTiers(unittest.TestCase):
    def test_memory_tiers_with_default_headroom(self):
        cases = [
            (64.0, MODEL_Q8_26B, 32768, 54.0, ">=40GB"),
            (40.0, MODEL_Q8_26B, 32768, 30.0, ">=40GB"),
            (32.0, MODEL_Q4_26B, 16384, 22.0, "28-39GB"),
            (28.0, MODEL_Q4_26B, 16384, 18.0, "28-39GB"),
            (18.0, MODEL_REAP_Q3_26B, 16384, 8.0, "16-27GB"),
            (16.0, MODEL_REAP_Q3_26B, 8192, 6.0, "16-27GB"),
            (12.0, MODEL_E4B, 8192, 2.0, "12-15GB"),
            (8.0, MODEL_E2B, 8192, 0.0, "<12GB"),
        ]
        for total_gb, expected_model, expected_ctx, expected_budget, expected_tier in cases:
            with self.subTest(total_gb=total_gb):
                sel = select_gemma_model(total_memory_gb=total_gb)
                self.assertEqual(sel.total_memory_gb, total_gb)
                self.assertEqual(sel.os_headroom_gb, OS_HEADROOM_GB)
                self.assertEqual(sel.model_budget_gb, expected_budget)
                self.assertEqual(sel.model, expected_model)
                self.assertEqual(sel.num_ctx, expected_ctx)
                self.assertEqual(sel.kv_cache_type, "q8_0")
                self.assertTrue(sel.flash_attention)
                self.assertEqual(sel.tier, expected_tier)
                self.assertFalse(sel.overridden)

    def test_none_memory_falls_back_to_e2b(self):
        with mock.patch("maca.local_model_selector.detect_total_memory_gb", return_value=None):
            sel = select_gemma_model(total_memory_gb=None)
        self.assertIsNone(sel.total_memory_gb)
        self.assertEqual(sel.os_headroom_gb, OS_HEADROOM_GB)
        self.assertEqual(sel.model_budget_gb, 0.0)
        self.assertEqual(sel.model, MODEL_E2B)
        self.assertEqual(sel.num_ctx, 8192)
        self.assertEqual(sel.kv_cache_type, "q8_0")
        self.assertTrue(sel.flash_attention)
        self.assertFalse(sel.overridden)

    def test_custom_headroom_adjusts_budget_and_tier(self):
        sel = select_gemma_model(total_memory_gb=40.0, headroom_gb=16.0)
        self.assertEqual(sel.os_headroom_gb, 16.0)
        self.assertEqual(sel.model_budget_gb, 24.0)
        self.assertEqual(sel.model, MODEL_Q4_26B)
        self.assertEqual(sel.num_ctx, 16384)

    def test_override_model_sets_overridden_flag_and_context(self):
        sel_known = select_gemma_model(total_memory_gb=32.0, override_model="gemma4:custom")
        self.assertTrue(sel_known.overridden)
        self.assertEqual(sel_known.model, "gemma4:custom")
        self.assertEqual(sel_known.num_ctx, 16384)
        self.assertEqual(sel_known.kv_cache_type, "q8_0")
        self.assertTrue(sel_known.flash_attention)

        with mock.patch("maca.local_model_selector.detect_total_memory_gb", return_value=None):
            sel_unknown = select_gemma_model(total_memory_gb=None, override_model="gemma4:custom")
        self.assertTrue(sel_unknown.overridden)
        self.assertEqual(sel_unknown.model, "gemma4:custom")
        self.assertEqual(sel_unknown.num_ctx, 16384)


class TestMemoryDetectionProbes(unittest.TestCase):
    def test_proc_meminfo_parser(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            meminfo = Path(tmpdir) / "meminfo"
            meminfo.write_text(
                "MemTotal:       33554432 kB\nMemFree:        16777216 kB\n",
                encoding="utf-8",
            )
            detected_bytes = _detect_proc_meminfo_bytes(meminfo)
            self.assertEqual(detected_bytes, 33554432 * 1024)

    def test_detect_total_memory_gb_sysconf_and_sysctl_fallbacks(self):
        with ExitStack() as stack:
            stack.enter_context(mock.patch("maca.local_model_selector.os.name", "posix"))
            stack.enter_context(mock.patch("maca.local_model_selector.sys.platform", "linux"))
            stack.enter_context(
                mock.patch(
                    "maca.local_model_selector._detect_proc_meminfo_bytes",
                    return_value=None,
                )
            )
            stack.enter_context(
                mock.patch(
                    "maca.local_model_selector._detect_sysconf_memory_bytes",
                    return_value=16 * (1024**3),
                )
            )
            self.assertEqual(detect_total_memory_gb(), 16.0)

        sysctl_ok = subprocess.CompletedProcess(
            args=["sysctl", "-n", "hw.memsize"],
            returncode=0,
            stdout=str(32 * (1024**3)) + "\n",
            stderr="",
        )
        with ExitStack() as stack:
            stack.enter_context(mock.patch("maca.local_model_selector.os.name", "posix"))
            stack.enter_context(mock.patch("maca.local_model_selector.sys.platform", "unix"))
            stack.enter_context(
                mock.patch(
                    "maca.local_model_selector._detect_proc_meminfo_bytes",
                    return_value=None,
                )
            )
            stack.enter_context(
                mock.patch(
                    "maca.local_model_selector._detect_sysconf_memory_bytes",
                    return_value=None,
                )
            )
            stack.enter_context(mock.patch("shutil.which", return_value="/usr/sbin/sysctl"))
            stack.enter_context(mock.patch("subprocess.run", return_value=sysctl_ok))
            self.assertEqual(detect_total_memory_gb(), 32.0)

    def test_detect_total_memory_gb_windows_branch(self):
        with ExitStack() as stack:
            stack.enter_context(mock.patch("maca.local_model_selector.os.name", "nt"))
            stack.enter_context(
                mock.patch(
                    "maca.local_model_selector._detect_windows_memory_bytes",
                    return_value=24 * (1024**3),
                )
            )
            self.assertEqual(detect_total_memory_gb(), 24.0)


class TestConfigPersistenceAndCli(unittest.TestCase):
    def test_config_write_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "nested" / "local_model.env"
            sel = select_gemma_model(total_memory_gb=32.0)
            written = write_local_model_config(sel, path=cfg_path)
            self.assertEqual(written, cfg_path)
            self.assertTrue(cfg_path.is_file())

            loaded = load_local_model_config(path=cfg_path)
            self.assertEqual(loaded["OLLAMA_MODEL"], MODEL_Q4_26B)
            self.assertEqual(loaded["OLLAMA_NUM_CTX"], "16384")
            self.assertEqual(loaded["OLLAMA_KV_CACHE_TYPE"], "q8_0")
            self.assertEqual(loaded["OLLAMA_FLASH_ATTENTION"], "1")

            with mock.patch.dict(os.environ, {"MACA_LOCAL_MODEL_CONFIG": str(cfg_path)}):
                self.assertEqual(default_local_model_config_path(), cfg_path)
                self.assertEqual(load_local_model_config()["OLLAMA_MODEL"], MODEL_Q4_26B)

    def test_load_missing_config_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "does_not_exist.env"
            self.assertEqual(load_local_model_config(path=missing), {})

    def test_cli_formats_and_write_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "out.env"

            # JSON format + write-config
            buf_json = io.StringIO()
            with redirect_stdout(buf_json):
                rc = main(
                    [
                        "--memory-gb",
                        "40",
                        "--format",
                        "json",
                        "--write-config",
                        "--config-path",
                        str(cfg_path),
                    ]
                )
            self.assertEqual(rc, 0)
            data = json.loads(buf_json.getvalue())
            self.assertEqual(data["model"], MODEL_Q8_26B)
            self.assertEqual(data["num_ctx"], 32768)
            self.assertEqual(data["model_budget_gb"], 30.0)
            self.assertEqual(load_local_model_config(cfg_path)["OLLAMA_MODEL"], MODEL_Q8_26B)

            # Shell format
            buf_shell = io.StringIO()
            with redirect_stdout(buf_shell):
                rc_shell = main(["--memory-gb", "18", "--format", "shell"])
            self.assertEqual(rc_shell, 0)
            shell_out = buf_shell.getvalue()
            self.assertIn("SELECTED_OLLAMA_MODEL=", shell_out)
            self.assertIn(MODEL_REAP_Q3_26B, shell_out)
            self.assertIn("SELECTED_OLLAMA_NUM_CTX=16384", shell_out)
            self.assertIn("SELECTED_OLLAMA_KV_CACHE_TYPE=q8_0", shell_out)
            self.assertIn("SELECTED_OLLAMA_FLASH_ATTENTION=1", shell_out)
            self.assertIn("SELECTED_TOTAL_MEM_GB=18.0", shell_out)
            self.assertIn("SELECTED_OS_HEADROOM_GB=10.0", shell_out)
            self.assertIn("SELECTED_MODEL_BUDGET_GB=8.0", shell_out)

            # Human format + CLI --model override
            buf_human = io.StringIO()
            with redirect_stdout(buf_human):
                rc_human = main(
                    ["--memory-gb", "16", "--model", "gemma4:override", "--format", "human"]
                )
            self.assertEqual(rc_human, 0)
            human_out = buf_human.getvalue()
            self.assertIn("gemma4:override", human_out)
            self.assertIn("10.0 GB", human_out)
            self.assertIn("6.0 GB", human_out)

    def test_maca_config_precedence_and_local_gemma_num_ctx_option(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "local_model.env"
            write_local_model_config(select_gemma_model(total_memory_gb=28.0), path=cfg_path)

            # 1. Env var beats persisted config
            env_override = {
                "MACA_LOCAL_MODEL_CONFIG": str(cfg_path),
                "OLLAMA_MODEL": "gemma4:env-override",
                "OLLAMA_NUM_CTX": "24576",
            }
            with mock.patch.dict(os.environ, env_override, clear=False):
                model, num_ctx, _, _ = config._resolve_ollama_settings()
                self.assertEqual(model, "gemma4:env-override")
                self.assertEqual(num_ctx, 24576)

            # 2. Persisted config beats auto-detection when env vars are unset
            excluded_env = {
                "OLLAMA_MODEL",
                "OLLAMA_NUM_CTX",
                "OLLAMA_KV_CACHE_TYPE",
                "OLLAMA_FLASH_ATTENTION",
                "MACA_OS_HEADROOM_GB",
            }
            clean_env = {k: v for k, v in os.environ.items() if k not in excluded_env}
            clean_env["MACA_LOCAL_MODEL_CONFIG"] = str(cfg_path)
            with mock.patch.dict(os.environ, clean_env, clear=True):
                model, num_ctx, kv, flash = config._resolve_ollama_settings()
                self.assertEqual(model, MODEL_Q4_26B)
                self.assertEqual(num_ctx, 16384)
                self.assertEqual(kv, "q8_0")
                self.assertTrue(flash)

            # 3. Auto-selection when neither env nor persisted config exists
            clean_env["MACA_LOCAL_MODEL_CONFIG"] = str(Path(tmpdir) / "missing.env")
            with ExitStack() as stack:
                stack.enter_context(mock.patch.dict(os.environ, clean_env, clear=True))
                stack.enter_context(
                    mock.patch(
                        "maca.local_model_selector.detect_total_memory_gb",
                        return_value=12.0,
                    )
                )
                model, num_ctx, _, _ = config._resolve_ollama_settings()
                self.assertEqual(model, MODEL_E4B)
                self.assertEqual(num_ctx, 8192)

    def test_local_gemma_client_forwards_num_ctx_option(self):
        captured_payloads = []

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return None

            def read(self):
                return json.dumps({"response": "ok"}).encode("utf-8")

        def _fake_urlopen(req, timeout=10):
            captured_payloads.append(json.loads(req.data.decode("utf-8")))
            return _FakeResponse()

        old_mock = config.MOCK_GEMMA_FALLBACK
        old_ctx = config.OLLAMA_NUM_CTX
        config.MOCK_GEMMA_FALLBACK = False
        try:
            config.OLLAMA_NUM_CTX = 32768
            client = LocalGemmaClient()
            with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
                res = client.generate("hello")
            self.assertEqual(res, "ok")
            self.assertEqual(captured_payloads[-1]["options"], {"num_ctx": 32768})

            config.OLLAMA_NUM_CTX = 0
            with mock.patch("urllib.request.urlopen", side_effect=_fake_urlopen):
                client.generate("hello again")
            self.assertNotIn("options", captured_payloads[-1])
        finally:
            config.MOCK_GEMMA_FALLBACK = old_mock
            config.OLLAMA_NUM_CTX = old_ctx


if __name__ == "__main__":
    unittest.main()
