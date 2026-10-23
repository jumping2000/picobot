"""Server MCP minimo per i test (stdio): un solo tool `add`."""
from fastmcp import FastMCP

mcp = FastMCP("probe")


@mcp.tool
def add(a: int, b: int) -> int:
    """Somma due interi."""
    return a + b


if __name__ == "__main__":
    mcp.run()
