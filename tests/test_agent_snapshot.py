"""Hardware-free tests for the pure snapshot projection."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agent_snapshot", ROOT / "fissure/Server/agent_snapshot.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StubTracker:
    def get_all_artifacts(self):
        return [SimpleNamespace(id="a1", name="capture", artifact_type="iq", source_id="n1",
                                operation_id="op1", created_at="2026-11-16", file_count=1,
                                total_size=500)]


class TestSnapshots(unittest.TestCase):
    def setUp(self):
        self.hub = SimpleNamespace(dashboard_connected=True,
                                   nodes={"n1": {"nickname": "A", "status": "Running", "private_key": "SECRET"}},
                                   targets={"t1": {"name": "T", "state": "tracking", "extra": "SECRET"}},
                                   sois={"s1": {"name": "S", "modulation": "FSK"}},
                                   artifact_tracker=StubTracker())

    def test_status(self):
        self.assertEqual(module.snapshot(self.hub, "status")["node_count"], 1)

    def test_node_no_secret(self):
        self.assertNotIn("SECRET", repr(module.snapshot(self.hub, "nodes")))

    def test_target_no_secret(self):
        self.assertNotIn("SECRET", repr(module.snapshot(self.hub, "targets")))

    def test_sois(self):
        self.assertEqual(module.snapshot(self.hub, "sois")["items"][0]["modulation"], "FSK")

    def test_artifacts(self):
        self.assertEqual(module.snapshot(self.hub, "artifacts")["items"][0]["file_count"], 1)

    def test_unknown_op_rejected(self):
        with self.assertRaises(ValueError):
            module.snapshot(self.hub, "start_transmit")

    def test_limit_rejected(self):
        for invalid in (0, 101, "x"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                module.snapshot(self.hub, "nodes", invalid)

    def test_caps_results(self):
        self.hub.nodes = {f"n{i}": {} for i in range(150)}
        self.assertEqual(len(module.snapshot(self.hub, "nodes", 100)["items"]), 100)


if __name__ == "__main__":
    unittest.main()
