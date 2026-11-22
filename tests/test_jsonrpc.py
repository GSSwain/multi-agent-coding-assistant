import io
import unittest

from maca.jsonrpc.client import JsonRpcClient
from maca.jsonrpc.dispatcher import JsonRpcDispatcher
from maca.jsonrpc.protocol import (
    INVALID_REQUEST,
    JSONRPC_VERSION,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    JsonRpcError,
    make_error,
    make_request,
    make_response,
    parse_message,
)
from maca.jsonrpc.server import JsonRpcServer


class TestJsonRpcProtocol(unittest.TestCase):
    def test_make_request(self):
        req = make_request("planner.plan", {"task": "do something"}, request_id=42)
        self.assertEqual(req["jsonrpc"], JSONRPC_VERSION)
        self.assertEqual(req["method"], "planner.plan")
        self.assertEqual(req["params"], {"task": "do something"})
        self.assertEqual(req["id"], 42)

    def test_make_notification(self):
        notif = make_request("notify.progress", {"status": "running"})
        self.assertEqual(notif["jsonrpc"], JSONRPC_VERSION)
        self.assertEqual(notif["method"], "notify.progress")
        self.assertNotIn("id", notif)

    def test_make_response(self):
        res = make_response({"status": "ok"}, request_id=42)
        self.assertEqual(res["jsonrpc"], JSONRPC_VERSION)
        self.assertEqual(res["result"], {"status": "ok"})
        self.assertEqual(res["id"], 42)

    def test_make_error(self):
        err = make_error(METHOD_NOT_FOUND, "Method not found", data="extra", request_id=42)
        self.assertEqual(err["jsonrpc"], JSONRPC_VERSION)
        self.assertEqual(err["id"], 42)
        self.assertEqual(err["error"]["code"], METHOD_NOT_FOUND)
        self.assertEqual(err["error"]["message"], "Method not found")
        self.assertEqual(err["error"]["data"], "extra")

    def test_parse_message_valid(self):
        raw = '{"jsonrpc": "2.0", "method": "ping", "id": 1}'
        data = parse_message(raw)
        self.assertEqual(data["method"], "ping")

    def test_parse_message_invalid_json(self):
        with self.assertRaises(JsonRpcError) as ctx:
            parse_message("not valid json {")
        self.assertEqual(ctx.exception.code, PARSE_ERROR)

    def test_parse_message_invalid_version(self):
        with self.assertRaises(JsonRpcError) as ctx:
            parse_message('{"jsonrpc": "1.0", "method": "ping"}')
        self.assertEqual(ctx.exception.code, INVALID_REQUEST)


class TestJsonRpcDispatcher(unittest.TestCase):
    def setUp(self):
        self.dispatcher = JsonRpcDispatcher()

    def test_list_methods(self):
        methods = self.dispatcher.list_methods()
        self.assertIn("system.ping", methods)
        self.assertIn("planner.plan", methods)
        self.assertIn("coder.generate", methods)
        self.assertIn("reviewer.review", methods)

    def test_dispatch_system_ping(self):
        res = self.dispatcher.dispatch("system.ping")
        self.assertEqual(res, "pong")

    def test_dispatch_method_not_found(self):
        with self.assertRaises(JsonRpcError) as ctx:
            self.dispatcher.dispatch("nonexistent.method")
        self.assertEqual(ctx.exception.code, METHOD_NOT_FOUND)

    def test_dispatch_custom_handler(self):
        self.dispatcher.register("calc.add", lambda p: p["a"] + p["b"])
        res = self.dispatcher.dispatch("calc.add", {"a": 10, "b": 20})
        self.assertEqual(res, 30)


class TestJsonRpcServer(unittest.TestCase):
    def setUp(self):
        self.dispatcher = JsonRpcDispatcher()
        self.dispatcher.register("echo", lambda p: p.get("msg"))
        self.in_stream = io.StringIO()
        self.out_stream = io.StringIO()
        self.server = JsonRpcServer(
            dispatcher=self.dispatcher,
            in_stream=self.in_stream,
            out_stream=self.out_stream,
        )

    def test_handle_request(self):
        req_line = '{"jsonrpc": "2.0", "id": 10, "method": "echo", "params": {"msg": "hello"}}\n'
        resp_line = self.server.handle_line(req_line)
        self.assertIsNotNone(resp_line)
        self.assertIn('"result": "hello"', resp_line)
        self.assertIn('"id": 10', resp_line)

    def test_handle_notification(self):
        notif_line = '{"jsonrpc": "2.0", "method": "echo", "params": {"msg": "hello"}}\n'
        resp_line = self.server.handle_line(notif_line)
        self.assertIsNone(resp_line)

    def test_handle_shutdown(self):
        line = '{"jsonrpc": "2.0", "id": 99, "method": "shutdown"}\n'
        resp_line = self.server.handle_line(line)
        self.assertIsNotNone(resp_line)
        self.assertFalse(self.server._running)

    def test_server_send_notification(self):
        self.server.send_notification("progress.stream", {"chunk": "def hello():"})
        written = self.out_stream.getvalue()
        self.assertIn('"method": "progress.stream"', written)
        self.assertIn('"chunk": "def hello():"', written)
        self.assertNotIn('"id"', written)


class TestJsonRpcClient(unittest.TestCase):
    def test_client_roundtrip_and_recovery(self):
        with JsonRpcClient() as client:
            # 1. Ping test over persistent stdio
            pong = client.call("system.ping")
            self.assertEqual(pong, "pong")

            # 2. Sequential calls reuse the worker
            methods = client.call("system.methods")
            self.assertIn("system.ping", methods)

            # 3. Method not found raises JsonRpcError
            with self.assertRaises(JsonRpcError) as ctx:
                client.call("nonexistent.method")
            self.assertEqual(ctx.exception.code, METHOD_NOT_FOUND)

            # 4. Simulate worker death: terminate process and verify auto-recovery
            if client._worker is not None:
                client._worker.kill()
                client._worker.wait()

            recovered_pong = client.call("system.ping")
            self.assertEqual(recovered_pong, "pong")

    def test_client_streaming_notifications(self):
        import os

        old_mock = os.environ.get("MOCK_GEMMA_FALLBACK")
        os.environ["MOCK_GEMMA_FALLBACK"] = "true"
        received_notifications = []

        def on_notif(method, params):
            received_notifications.append((method, params))

        try:
            with JsonRpcClient(on_notification=on_notif) as client:
                res = client.call(
                    "coder.generate",
                    {
                        "coder_type": "SIMPLE",
                        "task_description": "Create greet.py",
                        "plan": "1. Create greet.py",
                    },
                )
                self.assertIn("files", res)
                self.assertGreaterEqual(len(received_notifications), 1)
                self.assertEqual(received_notifications[0][0], "progress.stream")
                self.assertEqual(received_notifications[0][1]["agent"], "coder")
        finally:
            if old_mock is not None:
                os.environ["MOCK_GEMMA_FALLBACK"] = old_mock
            else:
                os.environ.pop("MOCK_GEMMA_FALLBACK", None)


if __name__ == "__main__":
    unittest.main()
