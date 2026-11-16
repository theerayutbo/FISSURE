"""Local, read-only client for the opt-in HIPRFISR Unix socket bridge."""
import json
import os
from pathlib import Path
import socket
import tempfile
from uuid import uuid4

MAX_RESPONSE_BYTES = 131072
ALLOWED_OPERATIONS = frozenset(("status", "nodes", "targets", "sois", "artifacts"))


class BridgeError(RuntimeError):
    pass


def default_socket_path():
    return Path(tempfile.gettempdir()) / f"fissure-agent-{os.getuid()}" / "bridge.sock"


def query(operation: str, limit: int = 25, *, socket_path=None, timeout_ms=5000):
    """Query HIPRFISR through Unix IPC; never issue generic hub commands."""
    if operation not in ALLOWED_OPERATIONS:
        raise ValueError("unsupported operation")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    if not 100 <= timeout_ms <= 30000:
        raise ValueError("timeout-ms must be in [100, 30000]")
    if os.name != "posix":
        raise BridgeError("Unix-domain socket transport requires a POSIX platform")
    address = Path(socket_path or os.environ.get("FISSURE_AGENT_SOCKET") or default_socket_path())
    if not address.is_absolute():
        raise ValueError("socket path must be absolute")
    request_id = uuid4().hex
    request = json.dumps({"request_id": request_id, "operation": operation, "limit": limit}).encode() + b"\n"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_ms / 1000)
    try:
        sock.connect(str(address))
        sock.sendall(request)
        content = bytearray()
        while len(content) <= MAX_RESPONSE_BYTES:
            part = sock.recv(min(4096, MAX_RESPONSE_BYTES + 1 - len(content)))
            if not part:
                raise BridgeError("HIPRFISR closed the bridge without a complete reply")
            content.extend(part)
            if b"\n" in part:
                break
        if len(content) > MAX_RESPONSE_BYTES or b"\n" not in content:
            raise BridgeError("HIPRFISR returned an oversized or incomplete response")
        response = json.loads(content.split(b"\n", 1)[0])
        if response.get("request_id") != request_id:
            raise BridgeError("response request_id mismatch")
        if not response.get("ok"):
            raise BridgeError(str(response.get("error") or "query rejected"))
        return response.get("data")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        if isinstance(exc, BridgeError):
            raise
        raise BridgeError(f"cannot query local HIPRFISR agent socket: {exc}") from exc
    finally:
        sock.close()
