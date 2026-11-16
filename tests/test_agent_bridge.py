"""Tests the actual Unix IPC transport with an in-process stub HIPRFISR."""
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import socket
import stat
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from unittest import TestCase, mock

ROOT = Path(__file__).resolve().parents[1]
# Avoid importing FISSURE's large package tree (GNU Radio, PyQt, etc.).
sys.path.insert(0, str(ROOT))
from Tools.fissure_agent.client import BridgeError, query


def load_bridge():
    with mock.patch.dict(sys.modules, {
        "fissure": ModuleType("fissure"),
        "fissure.Server": ModuleType("fissure.Server"),
    }):
        server_package = sys.modules["fissure.Server"]
        server_package.__path__ = [str(ROOT / "fissure" / "Server")]
        from importlib import import_module
        mod = import_module("fissure.Server.agent_bridge")
        return mod.AgentReadServer


AgentReadServer = load_bridge()


class TestAgentBridge(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private" / "bridge.sock"
        self.hub = SimpleNamespace(
            logger=logging.getLogger("test.agent"), dashboard_connected=True,
            nodes={"n1": {"nickname": "sensor", "private_key": "DO_NOT_LEAK"}},
            targets={}, sois={}, artifact_tracker=None,
        )

    def run_with_server(self, act):
        async def work():
            bridge = AgentReadServer(self.hub, socket_path=self.path)
            await bridge.start()
            try:
                self.assertTrue(stat.S_ISSOCK(self.path.stat().st_mode))
                self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)
                return await act()
            finally:
                await bridge.stop()
                self.assertFalse(self.path.exists())
        return asyncio.run(work())

    def test_cli_round_trip_and_projection(self):
        async def act():
            result = await asyncio.to_thread(query, "nodes", socket_path=self.path)
            self.assertEqual(result["total"], 1)
            self.assertNotIn("DO_NOT_LEAK", json.dumps(result))
        self.run_with_server(act)

    def test_status(self):
        async def act():
            result = await asyncio.to_thread(query, "status", socket_path=self.path)
            self.assertEqual(result["node_count"], 1)
        self.run_with_server(act)

    def test_reject_attack_operation(self):
        async def act():
            raw = await asyncio.open_unix_connection(str(self.path))
            reader, writer = raw
            writer.write(b'{"request_id":"t1","operation":"shutdown"}\n')
            await writer.drain()
            result = json.loads(await reader.readline())
            self.assertFalse(result["ok"])
            self.assertIn("unsupported", result["error"])
            writer.close()
            await writer.wait_closed()
        self.run_with_server(act)

    def test_reject_unexpected_fields(self):
        async def act():
            reader, writer = await asyncio.open_unix_connection(str(self.path))
            writer.write(b'{"request_id":"t1","operation":"status","callback":"shutdown"}\n')
            await writer.drain()
            self.assertFalse(json.loads(await reader.readline())["ok"])
            writer.close()
            await writer.wait_closed()
        self.run_with_server(act)

    def test_reject_oversized_request(self):
        async def act():
            reader, writer = await asyncio.open_unix_connection(str(self.path))
            writer.write(b"A" * 2100 + b"\n")
            await writer.drain()
            self.assertFalse(json.loads(await reader.readline())["ok"])
            writer.close()
            await writer.wait_closed()
        self.run_with_server(act)

    def test_reject_unsafe_socket_dir(self):
        self.path.parent.mkdir(mode=0o755)
        self.path.parent.chmod(0o755)
        with self.assertRaises(PermissionError):
            asyncio.run(AgentReadServer(self.hub, socket_path=self.path).start())

    def test_reject_duplicate_active_server(self):
        async def act():
            with self.assertRaises(RuntimeError):
                await AgentReadServer(self.hub, socket_path=self.path).start()
        self.run_with_server(act)

    def test_client_invalid_operations(self):
        with self.assertRaises(ValueError):
            query("start_transmit", socket_path=self.path)

    def test_missing_server(self):
        with self.assertRaises(BridgeError):
            query("status", socket_path=self.path, timeout_ms=200)
