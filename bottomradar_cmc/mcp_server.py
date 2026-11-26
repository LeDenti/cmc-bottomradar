"""MCP server: lets an AI agent ask the screener questions with live CMC data.

Run with the official MCP Python SDK (Python >= 3.10):
    uv run --with mcp python -m bottomradar_cmc mcp
Tools: scan_now, explain(symbol), replay(days), market_context.
"""
import json



def build():
    try:  # MCP Python SDK 2.x
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:  # 1.x
        from mcp.server.fastmcp import FastMCP as Server

    from . import screener
    from .client import CMC

    app = Server("bottomradar-cmc")
    cmc = CMC()

    @app.tool()
    def scan_now(limit: int = 15) -> str:
        """Tokens closest to a BottomRadar ladder step right now, with open paper positions and the three filters."""
        out = screener.scan(cmc)
        out["tokens"] = out["tokens"][:limit]
        return json.dumps(out, default=str)

    @app.tool()
    def explain(symbol: str) -> str:
        """Why the rule would (or would not) buy this token now: RSI, ladder high or low and which filter decided."""
        out = screener.scan(cmc)
        row = next((r for r in out["tokens"] if r["symbol"].upper() == symbol.upper()), None)
        if not row:
            return json.dumps({"error": "%s is not in the 74-token universe" % symbol})
        return json.dumps({"token": row, "filters_now": out["filters_now"],
                           "rule": screener.public_rule()},
                          default=str)

    @app.tool()
    def replay(days: int = 30) -> str:
        """What the rule did on CMC data over the last N days (max ~30 on intraday plans): summary and open positions."""
        out = screener.replay(min(int(days), 30), cmc)
        out.pop("events", None)
        return json.dumps(out, default=str)

    @app.tool()
    def market_context() -> str:
        """CMC Fear & Greed and CMC100 index (context only, not part of the rule)."""
        return json.dumps(screener.context(cmc))

    return app


def main():
    build().run()
