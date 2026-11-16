"""Bounded, allowlisted, read-only snapshots for trusted local AI/CLI clients.

No FISSURE imports, I/O, hardware calls, or arbitrary attribute access. The
HIPRFISR process is the only owner of its state; this module just serializes it.
"""

MAX_ITEMS = 100


def _limit(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer") from None
    if number < 1 or number > MAX_ITEMS:
        raise ValueError(f"limit must be between 1 and {MAX_ITEMS}")
    return number


def _str(record, *keys):
    for key in keys:
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)) and value is not None:
            return str(value)[:256]
    return ""


def _items(mapping, limit, serializer):
    if not isinstance(mapping, dict):
        return {"total": 0, "items": []}
    return {
        "total": len(mapping),
        "items": [serializer(key, value) for key, value in list(mapping.items())[:limit]
                  if isinstance(value, dict)],
    }


def _nodes(hub, limit):
    def public(uid, node):
        state = node.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        return {
            "node_uid": str(uid)[:128],
            "name": _str(node, "nickname", "callsign", "name"),
            "network_type": _str(node, "network_type"),
            "status": _str(state, "status") or _str(node, "status"),
            "autorun_state": _str(state, "autorun_state"),
        }
    return _items(getattr(hub, "nodes", {}), limit, public)


def _targets(hub, limit):
    def public(uid, target):
        return {
            "target_id": str(uid)[:128],
            "label": _str(target, "display_label", "name", "type"),
            "state": _str(target, "state", "status"),
            "source_soi_id": _str(target, "source_soi_id"),
            "updated": _str(target, "updated", "updated_at", "last_update_time"),
        }
    return _items(getattr(hub, "targets", {}), limit, public)


def _sois(hub, limit):
    def public(uid, soi):
        return {
            "soi_id": str(uid)[:128],
            "label": _str(soi, "name", "label", "soi_name"),
            "frequency_mhz": _str(soi, "frequency_mhz", "center_frequency", "frequency"),
            "modulation": _str(soi, "modulation", "modulation_type"),
            "status": _str(soi, "status", "state"),
        }
    return _items(getattr(hub, "sois", {}), limit, public)


def _artifacts(hub, limit):
    tracker = getattr(hub, "artifact_tracker", None)
    if tracker is None:
        return {"total": 0, "items": []}
    all_artifacts = tracker.get_all_artifacts()
    output = []
    for artifact in all_artifacts[:limit]:
        output.append({
            "artifact_id": str(artifact.id)[:128],
            "name": str(artifact.name)[:256],
            "artifact_type": str(artifact.artifact_type)[:128],
            "source_id": str(artifact.source_id)[:128],
            "operation_id": str(artifact.operation_id)[:128],
            "created_at": str(artifact.created_at)[:64],
            "file_count": int(artifact.file_count),
            "total_size": int(artifact.total_size),
        })
    return {"total": len(all_artifacts), "items": output}


def snapshot(hub, operation, limit=25):
    """Return a bounded public projection, never execute a user-supplied method."""
    cap = _limit(limit)
    handlers = {
        "nodes": _nodes,
        "targets": _targets,
        "sois": _sois,
        "artifacts": _artifacts,
    }
    if operation == "status":
        return {
            "hub": "HiprFisr",
            "dashboard_connected": bool(getattr(hub, "dashboard_connected", False)),
            "node_count": len(getattr(hub, "nodes", {}) or {}),
            "target_count": len(getattr(hub, "targets", {}) or {}),
            "soi_count": len(getattr(hub, "sois", {}) or {}),
        }
    if operation not in handlers:
        raise ValueError("unsupported read-only operation")
    return handlers[operation](hub, cap)
