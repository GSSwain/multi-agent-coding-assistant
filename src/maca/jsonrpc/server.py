import sys
from typing import Any, Dict, Optional, TextIO

from maca.jsonrpc.dispatcher import JsonRpcDispatcher
from maca.jsonrpc.protocol import (
    INTERNAL_ERROR,
    JsonRpcError,
    encode_message,
    make_error,
    make_notification,
    make_response,
    parse_message,
)


class JsonRpcServer:
    """A JSON-RPC 2.0 server operating over standard input/output streams."""

    def __init__(
        self,
        dispatcher: Optional[JsonRpcDispatcher] = None,
        in_stream: Optional[TextIO] = None,
        out_stream: Optional[TextIO] = None,
    ):
        self.stdin = in_stream or sys.stdin
        self.stdout = out_stream or sys.stdout
        self.dispatcher = dispatcher or JsonRpcDispatcher(notify_callback=self.send_notification)
        if self.dispatcher.notify_callback is None:
            self.dispatcher.notify_callback = self.send_notification
        self._running = True

    def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Write a JSON-RPC 2.0 notification line to the output stream."""
        notif = make_notification(method, params)
        self.stdout.write(encode_message(notif))
        self.stdout.flush()

    def handle_line(self, line: str) -> Optional[str]:
        """Process a single JSON-RPC line and return the encoded response line, or None."""
        stripped = line.strip()
        if not stripped:
            return None

        request_id = None
        try:
            req = parse_message(stripped)
            request_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if not method or not isinstance(method, str):
                raise JsonRpcError(
                    -32600,
                    "Invalid Request: 'method' must be a non-empty string",
                    request_id=request_id,
                )

            # Support clean shutdown
            if method in ("shutdown", "exit"):
                self._running = False
                if request_id is not None:
                    return encode_message(make_response({"status": "shutdown"}, request_id))
                return None

            result = self.dispatcher.dispatch(method, params)
            if request_id is not None:
                return encode_message(make_response(result, request_id))
            return None

        except JsonRpcError as e:
            req_id = e.request_id if e.request_id is not None else request_id
            return encode_message(make_error(e.code, e.message, e.data, request_id=req_id))
        except Exception as e:
            return encode_message(make_error(INTERNAL_ERROR, str(e), request_id=request_id))

    def serve_forever(self) -> None:
        """Read NDJSON lines from stdin and write NDJSON responses to stdout."""
        while self._running:
            line = self.stdin.readline()
            if not line:
                break  # Pipe closed / EOF

            resp = self.handle_line(line)
            if resp:
                self.stdout.write(resp)
                self.stdout.flush()


def run_server() -> None:
    server = JsonRpcServer()
    server.serve_forever()


if __name__ == "__main__":
    run_server()
