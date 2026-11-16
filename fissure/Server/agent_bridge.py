"""Opt-in, locally authenticated read-only Unix socket for FISSURE queries.

This socket does NOT share HIPRFISR's generic callback router or CURVE identity.
The Linux kernel supplies peer credentials; only the Hub's OS UID is accepted.
"""

import asyncio
import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile

from .agent_snapshot import snapshot

MAX_REQUEST_BYTES = 2048
MAX_RESPONSE_BYTES = 131072
READ_TIMEOUT_SECONDS = 3


def default_socket_path():
    return Path(tempfile.gettempdir()) / f"fissure-agent-{os.getuid()}" / "bridge.sock"


class AgentReadServer:
    """Tiny, non-generic API that never invokes HIPRFISR callbacks."""

    def __init__(self, hub, socket_path=None):
        self.hub = hub
        self.path = Path(socket_path or os.environ.get("FISSURE_AGENT_SOCKET") or default_socket_path())
        self.server = None
        self._inode = None
        self._semaphore = asyncio.Semaphore(8)

    def _prepare_path(self):
        directory = self.path.parent
        if len(os.fsencode(str(self.path))) >= 100:
            raise ValueError("FISSURE agent socket path is too long")
        if not self.path.is_absolute():
            raise ValueError("FISSURE agent socket path must be absolute")
        if not directory.exists():
            directory.mkdir(mode=0o700, parents=True)
        dstat = directory.lstat()
        if not stat.S_ISDIR(dstat.st_mode) or dstat.st_uid != os.getuid() or dstat.st_mode & 0o077:
            raise PermissionError("FISSURE agent socket directory must be owned by Hub UID and mode 0700")
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise PermissionError("Refusing to replace a non-socket or another user's socket")
        # Do not disconnect another active instance, even with the same UID.
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            if probe.connect_ex(str(self.path)) == 0:
                raise RuntimeError("FISSURE agent socket is already served by another process")
        finally:
            probe.close()
        self.path.unlink()  # Stale socket from a crashed same-UID process.

    async def start(self):
        if os.name != "posix" or not hasattr(socket, "SO_PEERCRED"):
            raise RuntimeError("FISSURE AgentReadServer currently requires Linux SO_PEERCRED")
        self._prepare_path()
        self.server = await asyncio.start_unix_server(
            self._handle_client, path=str(self.path), limit=MAX_REQUEST_BYTES + 1
        )
        os.chmod(self.path, 0o600)
        self._inode = self.path.stat().st_ino
        self.hub.logger.info("FISSURE read-only agent IPC enabled (UID restricted)")

    async def stop(self):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        try:
            state = self.path.lstat()
            if stat.S_ISSOCK(state.st_mode) and state.st_uid == os.getuid() and state.st_ino == self._inode:
                self.path.unlink()
        except FileNotFoundError:
            pass

    async def _handle_client(self, reader, writer):
        async with self._semaphore:
            request_id = ""
            try:
                peer = writer.get_extra_info("socket")
                if peer is None:
                    raise PermissionError("peer socket unavailable")
                credentials = peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                _, peer_uid, _ = struct.unpack("3i", credentials)
                if peer_uid != os.getuid():
                    raise PermissionError("only the local Hub OS user may query this socket")
                line = await asyncio.wait_for(reader.readline(), READ_TIMEOUT_SECONDS)
                if not line or len(line) > MAX_REQUEST_BYTES or not line.endswith(b"\n"):
                    raise ValueError("malformed or oversized request")
                request = json.loads(line)
                if not isinstance(request, dict) or set(request) - {"request_id", "operation", "limit"}:
                    raise ValueError("unexpected request fields")
                request_id = request.get("request_id", "")
                if not isinstance(request_id, str) or len(request_id) > 64:
                    raise ValueError("invalid request_id")
                operation = request.get("operation")
                if not isinstance(operation, str):
                    raise ValueError("invalid operation")
                data = snapshot(self.hub, operation, request.get("limit", 25))
                result = {"request_id": request_id, "ok": True, "data": data}
                self.hub.logger.info("FISSURE agent read query: %s", operation)
            except (PermissionError, ValueError, TypeError, json.JSONDecodeError) as exc:
                result = {"request_id": request_id, "ok": False, "error": str(exc)[:180]}
            except (asyncio.TimeoutError, asyncio.IncompleteReadError):
                result = {"request_id": request_id, "ok": False, "error": "request timeout or incomplete data"}
            except Exception:
                self.hub.logger.exception("FISSURE agent read query failed")
                result = {"request_id": request_id, "ok": False, "error": "internal read query error"}
            try:
                response = json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
                if len(response) > MAX_RESPONSE_BYTES:
                    response = b'{"ok":false,"error":"response too large"}'
                writer.write(response + b"\n")
                await asyncio.wait_for(writer.drain(), READ_TIMEOUT_SECONDS)
            except (OSError, asyncio.TimeoutError):
                pass
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass
