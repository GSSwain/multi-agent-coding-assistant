import atexit
import json
import os
import queue
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, Optional

from maca.jsonrpc.protocol import (
    JSONRPC_VERSION,
    JsonRpcError,
    encode_message,
    make_request,
)


class JsonRpcClient:
    """A JSON-RPC 2.0 client managing a persistent subprocess worker over stdio."""

    def __init__(
        self,
        python_executable: Optional[str] = None,
        default_timeout: Optional[float] = 120.0,
        on_notification: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ):
        self.python_executable = python_executable or sys.executable
        self.default_timeout = default_timeout
        self.on_notification = on_notification
        self._worker: Optional[subprocess.Popen] = None
        self._response_queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None
        self._request_counter = 0
        self._lock = threading.Lock()
        atexit.register(self.close)

    def _next_id(self) -> int:
        self._request_counter += 1
        return self._request_counter

    def _get_worker_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        src_dir = os.path.abspath(os.path.join(curr_dir, "..", ".."))
        existing = env.get("PYTHONPATH", "")
        if src_dir not in existing.split(os.pathsep):
            env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{existing}" if existing else src_dir
        return env

    def _reader_loop(self, stdout_stream: Any, resp_queue: "queue.Queue[Optional[str]]") -> None:
        """Continuously read NDJSON lines from the worker's stdout.

        Dispatches JSON-RPC 2.0 notifications immediately via on_notification
        and enqueues request responses for the waiting caller.
        """
        try:
            while True:
                line = stdout_stream.readline()
                if not line:
                    resp_queue.put(None)
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    msg = json.loads(stripped)
                    if isinstance(msg, dict) and "method" in msg and "id" not in msg:
                        if self.on_notification is not None:
                            self.on_notification(
                                str(msg.get("method", "")),
                                msg.get("params") or {},
                            )
                        continue
                except Exception:
                    pass
                resp_queue.put(line)
        except Exception:
            resp_queue.put(None)

    def _ensure_worker(self) -> subprocess.Popen:
        """Ensure the persistent JSON-RPC server worker process is alive and running."""
        if self._worker is not None and self._worker.poll() is None:
            return self._worker

        if self._worker is not None:
            self.close()

        env = self._get_worker_env()
        self._response_queue = queue.Queue()
        self._worker = subprocess.Popen(
            [self.python_executable, "-m", "maca.jsonrpc.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1,  # Line buffered
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            args=(self._worker.stdout, self._response_queue),
            daemon=True,
        )
        self._reader_thread.start()
        return self._worker

    def _read_response_line(self, method: str, timeout: Optional[float]) -> Optional[str]:
        """Wait for a response line from the reader queue with optional timeout."""
        try:
            return self._response_queue.get(timeout=timeout)
        except queue.Empty as e:
            self.close()
            raise TimeoutError(f"JSON-RPC call '{method}' timed out after {timeout}s") from e

    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        """Invoke a remote method via JSON-RPC 2.0 and return the result."""
        effective_timeout = timeout if timeout is not None else self.default_timeout
        with self._lock:
            effective_params = dict(params) if params is not None else {}
            effective_params["_env"] = {
                k: v
                for k, v in os.environ.items()
                if k.startswith(("MOCK_", "MACA_", "GEMINI_", "ANTHROPIC_"))
            }

            req_id = self._next_id()
            req = make_request(method, effective_params, req_id)
            encoded = encode_message(req)

            try:
                worker = self._ensure_worker()
                if not worker.stdin or not worker.stdout:
                    raise RuntimeError("Worker process stdin/stdout streams not available")

                worker.stdin.write(encoded)
                worker.stdin.flush()
                resp_line = self._read_response_line(method, effective_timeout)

                if not resp_line:
                    # Worker closed pipe or crashed; try one restart
                    self.close()
                    worker = self._ensure_worker()
                    if not worker.stdin or not worker.stdout:
                        raise RuntimeError("Worker restart failed")
                    worker.stdin.write(encoded)
                    worker.stdin.flush()
                    resp_line = self._read_response_line(method, effective_timeout)

                if not resp_line:
                    stderr_msg = worker.stderr.read() if worker.stderr else ""
                    raise RuntimeError(
                        f"JSON-RPC worker terminated unexpectedly. Stderr: {stderr_msg}"
                    )

                parsed = json.loads(resp_line)
                if not isinstance(parsed, dict) or parsed.get("jsonrpc") != JSONRPC_VERSION:
                    raise RuntimeError(f"Malformed JSON-RPC 2.0 response: {resp_line}")

                if "error" in parsed:
                    err = parsed["error"]
                    raise JsonRpcError(
                        code=err.get("code", -32603),
                        message=err.get("message", "Unknown error"),
                        data=err.get("data"),
                        request_id=parsed.get("id"),
                    )

                return parsed.get("result")

            except (JsonRpcError, TimeoutError):
                raise
            except Exception as e:
                raise RuntimeError(f"Failed to execute JSON-RPC call '{method}': {e}") from e

    def close(self) -> None:
        """Terminate the persistent worker process and close open pipes."""
        if self._worker is not None:
            try:
                if self._worker.stdin and not self._worker.stdin.closed:
                    self._worker.stdin.close()
                if self._worker.stdout and not self._worker.stdout.closed:
                    self._worker.stdout.close()
                if self._worker.stderr and not self._worker.stderr.closed:
                    self._worker.stderr.close()
                if self._worker.poll() is None:
                    self._worker.terminate()
                    self._worker.wait(timeout=2.0)
            except Exception:
                if self._worker.poll() is None:
                    self._worker.kill()
            finally:
                self._worker = None
                self._reader_thread = None

    def __enter__(self) -> "JsonRpcClient":
        self._ensure_worker()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
