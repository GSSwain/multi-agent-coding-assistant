import threading
from typing import Any, Dict, Optional

from maca.jsonrpc.client import JsonRpcClient
from maca.jsonrpc.protocol import JsonRpcError

_rpc_client: Optional[JsonRpcClient] = None
_client_lock = threading.Lock()


def get_rpc_client() -> JsonRpcClient:
    """Return the active persistent JSON-RPC client, initializing if needed."""
    global _rpc_client
    with _client_lock:
        if _rpc_client is None:
            _rpc_client = JsonRpcClient()
        return _rpc_client


def close_rpc_client() -> None:
    """Cleanly close and terminate the persistent JSON-RPC client and worker."""
    global _rpc_client
    with _client_lock:
        if _rpc_client is not None:
            _rpc_client.close()
            _rpc_client = None


def call_agent(agent_module: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an agent method using JSON-RPC 2.0 over persistent stdio.

    Parameters
    ----------
    agent_module: str
        Dotted module path (e.g. "maca.agents.planner") or RPC method name (e.g. "planner.plan").
    args: dict
        Arguments to pass to the agent method.

    Returns
    -------
    dict
        Parsed JSON-RPC result from the agent.
    """
    client = get_rpc_client()
    try:
        res = client.call(agent_module, args)
        if isinstance(res, dict):
            return res
        return {"result": res}
    except JsonRpcError as e:
        raise RuntimeError(f"Agent {agent_module} JSON-RPC error [{e.code}]: {e.message}") from e
