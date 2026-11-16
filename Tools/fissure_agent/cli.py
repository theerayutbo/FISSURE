"""Run: python3 -m Tools.fissure_agent.cli status"""
import argparse
import json
import sys

from .client import BridgeError, query


def main(argv=None):
    parser = argparse.ArgumentParser(description="FISSURE read-only local CLI")
    parser.add_argument("--socket", default=None, help="absolute Unix bridge socket path")
    parser.add_argument("--timeout-ms", type=int, default=5000)
    sub = parser.add_subparsers(dest="operation", required=True)
    for name in ("status", "nodes", "targets", "sois", "artifacts"):
        cmd = sub.add_parser(name)
        if name != "status":
            cmd.add_argument("--limit", type=int, default=25)
    args = parser.parse_args(argv)
    try:
        data = query(args.operation, getattr(args, "limit", 25),
                     socket_path=args.socket, timeout_ms=args.timeout_ms)
    except (BridgeError, ValueError) as exc:
        print(f"fissure-cli: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
