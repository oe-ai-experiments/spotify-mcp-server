#!/bin/bash
# ABOUTME: Wrapper script to run Spotify MCP Server for Cursor integration
# ABOUTME: Ensures proper environment and path resolution for MCP protocol

# Use full path to uvx since Cursor may not have Homebrew paths in PATH
cd /Users/oeftimie/work/ai/spotify-mcp-server

# Pass through all arguments, but ensure config path is absolute
args=()
for arg in "$@"; do
    if [[ "$arg" == "config.json" ]]; then
        args+=("/Users/oeftimie/work/ai/spotify-mcp-server/config.json")
    else
        args+=("$arg")
    fi
done

FASTMCP_LOG_LEVEL=CRITICAL exec /opt/homebrew/bin/uvx --from /Users/oeftimie/work/ai/spotify-mcp-server spotify-mcp-server "${args[@]}"


