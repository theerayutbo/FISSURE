"""Read-only MCP stdio tools for a locally running FISSURE HIPRFISR."""
try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise SystemExit("Install the optional MCP SDK: python3 -m pip install 'mcp>=1,<2'") from exc

from .client import query

mcp = FastMCP("FISSURE Read-only")


@mcp.tool()
def fissure_status() -> dict:
    """Read the local FISSURE Hub state totals."""
    return query("status")


@mcp.tool()
def fissure_nodes(limit: int = 25) -> dict:
    """Read a bounded list of currently registered Sensor Nodes."""
    return query("nodes", limit)


@mcp.tool()
def fissure_targets(limit: int = 25) -> dict:
    """Read selected Target metadata; no execution or RF transmissions."""
    return query("targets", limit)


@mcp.tool()
def fissure_sois(limit: int = 25) -> dict:
    """Read selected Signal-of-Interest metadata."""
    return query("sois", limit)


@mcp.tool()
def fissure_artifacts(limit: int = 25) -> dict:
    """Read Artifact manifest summaries, not IQ payload files."""
    return query("artifacts", limit)


if __name__ == "__main__":
    mcp.run(transport="stdio")
