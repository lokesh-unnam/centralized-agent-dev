"""
Tool Registry - Central registry for all available tools.
"""
from __future__ import annotations
from typing import Optional
import structlog

from tools.base import BaseTool, ToolResult, ToolResultStatus
from tools.file_tools import get_file_tools
from tools.terminal_tools import get_terminal_tools
from tools.code_tools import get_code_tools
from tools.search_tools import get_search_tools

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """Central registry for all tools available to agents."""
    
    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path
        self._tools: dict[str, BaseTool] = {}
        self._load_default_tools()
    
    def _load_default_tools(self) -> None:
        """Load all default tools."""
        all_tools = [
            *get_file_tools(self.workspace_path),
            *get_terminal_tools(self.workspace_path),
            *get_code_tools(self.workspace_path),
            *get_search_tools(self.workspace_path),
        ]
        
        for tool in all_tools:
            self.register(tool)
        
        logger.info("tool_registry.loaded", count=len(self._tools))
    
    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        logger.debug("tool_registry.registered", tool=tool.name)
    
    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name."""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                status=ToolResultStatus.ERROR,
                error=f"Tool not found: {name}"
            )
        return tool(**kwargs)
    
    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())
    
    def get_schemas(self) -> list[dict]:
        """Get JSON schemas for all tools (for LLM function calling)."""
        return [tool.to_schema() for tool in self._tools.values()]
    
    def get_tools_by_category(self) -> dict[str, list[str]]:
        """Get tools organized by category."""
        categories = {
            "file": ["create_file", "read_file", "edit_file", "write_file", "delete_file", "list_files"],
            "terminal": ["execute_command", "run_python", "run_python_file", "install_package", "run_tests"],
            "code": ["lint_code", "type_check", "format_code", "analyze_code", "search_code"],
            "search": ["web_search", "python_docs", "package_info"],
        }
        return {cat: [t for t in tools if t in self._tools] for cat, tools in categories.items()}
    
    def get_sandbox_safe_tools(self) -> list[str]:
        """Get tools that are safe to run in sandbox."""
        return [name for name, tool in self._tools.items() if tool.sandbox_safe]
    
    def get_approval_required_tools(self) -> list[str]:
        """Get tools that require user approval."""
        return [name for name, tool in self._tools.items() if tool.requires_approval]
    
    def format_tools_for_prompt(self) -> str:
        """Format tools for inclusion in LLM prompt."""
        lines = ["Available tools:\n"]
        
        for category, tools in self.get_tools_by_category().items():
            lines.append(f"\n## {category.upper()} TOOLS")
            for tool_name in tools:
                tool = self._tools[tool_name]
                params = ", ".join(
                    f"{p.name}: {p.type}" + ("" if p.required else "?")
                    for p in tool.parameters
                )
                lines.append(f"- **{tool.name}**({params}): {tool.description}")
        
        return "\n".join(lines)


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_tool_registry(workspace_path: Optional[str] = None) -> ToolRegistry:
    """Get or create the global tool registry."""
    global _registry
    if _registry is None or (workspace_path and _registry.workspace_path != workspace_path):
        _registry = ToolRegistry(workspace_path)
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
