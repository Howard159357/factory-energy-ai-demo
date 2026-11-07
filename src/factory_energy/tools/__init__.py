"""Typed, permissioned tools over the plant database and the knowledge base.

The same registry backs the agent loop and the MCP server. Every tool validates its arguments
with a pydantic model, declares a read or write permission, and returns JSON-safe data.
"""

from factory_energy.tools.registry import Tool, ToolRegistry, ToolResult, build_registry

__all__ = ["Tool", "ToolRegistry", "ToolResult", "build_registry"]
