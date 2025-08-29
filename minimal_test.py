#!/usr/bin/env python3
"""Minimal FastMCP server for testing deployment."""

from fastmcp import FastMCP

app = FastMCP("Minimal Test Server")

@app.tool()
def test_tool() -> str:
    """A simple test tool."""
    return "Hello from minimal test server!"

def main():
    """Main entry point."""
    app.run()

if __name__ == "__main__":
    main()
