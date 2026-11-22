import json
from typing import Any, Dict, Optional, Union

JSONRPC_VERSION = "2.0"

# Standard JSON-RPC 2.0 Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
SERVER_ERROR = -32000


class JsonRpcError(Exception):
    """Represents a JSON-RPC 2.0 error."""

    def __init__(
        self,
        code: int,
        message: str,
        data: Optional[Any] = None,
        request_id: Optional[Union[str, int]] = None,
    ):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data
        self.request_id = request_id

    def to_dict(self) -> Dict[str, Any]:
        err: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            err["data"] = self.data
        return err


def make_request(
    method: str,
    params: Optional[Dict[str, Any]] = None,
    request_id: Optional[Union[str, int]] = None,
) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 request or notification dictionary."""
    req: Dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "method": method,
        "params": params if params is not None else {},
    }
    if request_id is not None:
        req["id"] = request_id
    return req


def make_notification(
    method: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 notification dictionary (no request id)."""
    return make_request(method=method, params=params, request_id=None)


def make_response(
    result: Any,
    request_id: Optional[Union[str, int]],
) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 success response dictionary."""
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "result": result,
    }


def make_error(
    code: int,
    message: str,
    data: Optional[Any] = None,
    request_id: Optional[Union[str, int]] = None,
) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 error response dictionary."""
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": err,
    }


def encode_message(msg: Dict[str, Any]) -> str:
    """Serialize a message dictionary to a newline-terminated JSON string."""
    return json.dumps(msg, ensure_ascii=False) + "\n"


def parse_message(raw_json: str) -> Dict[str, Any]:
    """Parse a raw JSON string and validate basic JSON-RPC 2.0 envelope structure."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise JsonRpcError(PARSE_ERROR, f"Parse error: {e}") from e

    if not isinstance(data, dict):
        raise JsonRpcError(INVALID_REQUEST, "Invalid Request: root must be a JSON object")

    if data.get("jsonrpc") != JSONRPC_VERSION:
        raise JsonRpcError(
            INVALID_REQUEST,
            f"Invalid Request: 'jsonrpc' must be '{JSONRPC_VERSION}', got '{data.get('jsonrpc')}'",
        )

    return data
