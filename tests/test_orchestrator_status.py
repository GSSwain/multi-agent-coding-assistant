import unittest
from unittest import mock

from maca.orchestrator import Orchestrator


class OrchestratorStatusTests(unittest.TestCase):
    def test_fast_status_uses_ollama_http_when_available(self):
        orch = Orchestrator(".")

        fake_response = mock.MagicMock()
        fake_response.__enter__.return_value.status = 200
        fake_response.__enter__.return_value.read.return_value = b'{}'

        with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen_mock, \
             mock.patch("subprocess.run", side_effect=FileNotFoundError("no cli")):
            status = orch.check_backends_status(run_handshakes=False)

        self.assertEqual(status["Gemma"], "ONLINE (Ollama HTTP - gemma2:2b)")
        urlopen_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
