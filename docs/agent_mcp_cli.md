# Opt-in local FISSURE CLI and MCP (read-only)

This integration provides five **read-only** views of a running HIPRFISR Hub:
`status`, `nodes`, `targets`, `sois`, and `artifacts` (manifest summaries only).
The same local client powers a JSON CLI and a Model Context Protocol (MCP)
**stdio** server. It does not expose GNU Radio hardware, generic callbacks,
packet transmit/replay, fuzzing, attack flows, or arbitrary file reads.

## Security and compatibility

- **Disabled by default.** The Hub creates no socket unless
  `FISSURE_AGENT_ENABLED=1` is present in its process environment.
- **Linux local-only.** A dedicated Unix-domain socket uses a directory with
  permissions `0700` and a socket with permissions `0600`. The Hub independently
  checks the caller's kernel-supplied `SO_PEERCRED` UID against the Hub's UID.
  The MCP process therefore runs as the **same OS account** as HIPRFISR.
- **Not the existing ZMQ backend.** The bridge never enters the FISSURE
  callback router and does **not** reuse `client_0.key_secret` or other CURVE
  credentials. It accepts only a hard-coded projection of state.
- **Bounded.** Limit 1–100 entries per query, 2-KiB request and 128-KiB response
  limits, a 3-second read deadline, eight concurrent request handlers, and
  no binary Artifact or IQ retrieval. Only selected metadata fields are emitted.
- **Trust boundary.** Any process already running under the Hub account can
  query this socket. This is not multi-user authentication or an Internet API.
  Keep AI agents under a dedicated least-privilege OS user when appropriate.
- **Remote access.** Do not forward or expose this Unix socket publicly. Run
  the CLI/MCP on the Hub machine, optionally via an authenticated SSH session.

## Start the Hub with the bridge enabled

From the repository root in the same environment used to start FISSURE:

```bash
export FISSURE_AGENT_ENABLED=1
# Start HIPRFISR using your existing FISSURE launch procedure.
```

The default socket is `/tmp/fissure-agent-<UID>/bridge.sock`. To override:

```bash
mkdir -p "$HOME/.fissure-agent"
chmod 700 "$HOME/.fissure-agent"
export FISSURE_AGENT_SOCKET="$HOME/.fissure-agent/bridge.sock"
```

The socket path must be absolute and its parent directory owned by the Hub UID
and not accessible by group or other users. The bridge refuses to unlink a
regular file, a foreign socket, or an active socket owned by another instance.

## CLI

From the repository root, running as the same OS user as the Hub:

```bash
python3 -m Tools.fissure_agent.cli status
python3 -m Tools.fissure_agent.cli nodes --limit 20
python3 -m Tools.fissure_agent.cli targets
python3 -m Tools.fissure_agent.cli sois
python3 -m Tools.fissure_agent.cli artifacts
```

Use `--socket /absolute/path.sock` if you configured a different socket path.
CLI returns JSON on standard output and nonzero exit code for errors.
No additional dependencies are needed for the CLI beyond Python's stdlib.

## MCP stdio

Install the optional Python MCP SDK into the environment running the agent:

```bash
python3 -m pip install 'mcp>=1,<2'
FISSURE_AGENT_SOCKET=/tmp/fissure-agent-$(id -u)/bridge.sock \
  python3 -m Tools.fissure_agent.mcp_server
```

Example MCP client configuration (replace paths for your deployment):

```json
{
  "mcpServers": {
    "fissure": {
      "command": "python3",
      "args": ["-m", "Tools.fissure_agent.mcp_server"],
      "cwd": "/path/to/FISSURE",
      "env": {
        "FISSURE_AGENT_SOCKET": "/tmp/fissure-agent-1000/bridge.sock"
      }
    }
  }
}
```

Tool names are `fissure_status`, `fissure_nodes`, `fissure_targets`,
`fissure_sois`, and `fissure_artifacts`.

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_agent_*.py' -v
python3 -m compileall -q Tools/fissure_agent fissure/Server/agent_bridge.py fissure/Server/agent_snapshot.py
```

The tests use a stub Hub and exercise the **real Unix socket transport** with
peer credentials. They do **not** claim to establish compatibility with every
HIPRFISR startup mode, SDR, real Dashboard session, remote deployment, or
production OS configuration. Perform a real-Hub smoke test with bridge opt-in
before treating the feature as deployment-ready.

## Non-goals and follow-up

No remote TCP listener, TX/attack actions, general FISSURE Web API, plugin
execution, IQ data download, or AI autonomous RF action is present. Future RX
operations need an explicit capability allowlist, operator approval policy,
per-operation tracking, and independent security review.

Related upstream discussion: https://github.com/ainfosec/FISSURE/issues/55
