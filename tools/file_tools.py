"""
File Tools - Create, Read, Edit, Delete files.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
import difflib

from tools.base import BaseTool, ToolResult, ToolResultStatus, ToolParameter


class CreateFileTool(BaseTool):
    """Create a new file with content."""
    
    name = "create_file"
    description = "Create a new file with the specified content. Use this to generate code files, configs, etc."
    parameters = [
        ToolParameter(name="path", type="string", description="File path relative to workspace"),
        ToolParameter(name="content", type="string", description="Content to write to the file"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str, content: str) -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if file exists
            if full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"File already exists: {path}. Use edit_file to modify."
                )
            
            full_path.write_text(content, encoding="utf-8")
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"Created file: {path} ({len(content)} chars)",
                metadata={"path": str(full_path), "size": len(content)}
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class ReadFileTool(BaseTool):
    """Read content from a file."""
    
    name = "read_file"
    description = "Read the content of a file. Returns the full file content."
    parameters = [
        ToolParameter(name="path", type="string", description="File path relative to workspace"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str) -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            if not full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"File not found: {path}"
                )
            
            content = full_path.read_text(encoding="utf-8")
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=content,
                metadata={"path": str(full_path), "size": len(content), "lines": content.count('\n') + 1}
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class EditFileTool(BaseTool):
    """Edit an existing file using search/replace."""
    
    name = "edit_file"
    description = "Edit a file by replacing specific content. Provide the exact text to find and the replacement."
    parameters = [
        ToolParameter(name="path", type="string", description="File path relative to workspace"),
        ToolParameter(name="old_content", type="string", description="Exact content to find and replace"),
        ToolParameter(name="new_content", type="string", description="New content to replace with"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str, old_content: str, new_content: str) -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            if not full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"File not found: {path}"
                )
            
            content = full_path.read_text(encoding="utf-8")
            
            if old_content not in content:
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Content to replace not found in {path}"
                )
            
            new_file_content = content.replace(old_content, new_content, 1)
            full_path.write_text(new_file_content, encoding="utf-8")
            
            # Generate diff
            diff = list(difflib.unified_diff(
                content.splitlines(keepends=True),
                new_file_content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}"
            ))
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"Edited file: {path}",
                metadata={"path": str(full_path), "diff": "".join(diff)}
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class WriteFileTool(BaseTool):
    """Write/overwrite a file completely."""
    
    name = "write_file"
    description = "Write content to a file, creating or overwriting it. Use for complete file rewrites."
    parameters = [
        ToolParameter(name="path", type="string", description="File path relative to workspace"),
        ToolParameter(name="content", type="string", description="Full content to write"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str, content: str) -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            existed = full_path.exists()
            full_path.write_text(content, encoding="utf-8")
            
            action = "Overwrote" if existed else "Created"
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"{action} file: {path} ({len(content)} chars)",
                metadata={"path": str(full_path), "size": len(content), "overwritten": existed}
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class DeleteFileTool(BaseTool):
    """Delete a file."""
    
    name = "delete_file"
    description = "Delete a file from the workspace."
    parameters = [
        ToolParameter(name="path", type="string", description="File path relative to workspace"),
    ]
    requires_approval = True  # Destructive action
    sandbox_safe = True
    
    def execute(self, path: str) -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            if not full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"File not found: {path}"
                )
            
            full_path.unlink()
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=f"Deleted file: {path}",
                metadata={"path": str(full_path)}
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class ListFilesTool(BaseTool):
    """List files in a directory."""
    
    name = "list_files"
    description = "List all files in a directory, optionally recursive."
    parameters = [
        ToolParameter(name="path", type="string", description="Directory path relative to workspace", required=False, default="."),
        ToolParameter(name="recursive", type="boolean", description="Whether to list recursively", required=False, default=False),
        ToolParameter(name="pattern", type="string", description="Glob pattern to filter files", required=False, default="*"),
    ]
    requires_approval = False
    sandbox_safe = True
    
    def execute(self, path: str = ".", recursive: bool = False, pattern: str = "*") -> ToolResult:
        try:
            if self.workspace_path:
                full_path = Path(self.workspace_path) / path
            else:
                full_path = Path(path)
            
            if not full_path.exists():
                return ToolResult(
                    status=ToolResultStatus.ERROR,
                    error=f"Directory not found: {path}"
                )
            
            if recursive:
                files = list(full_path.rglob(pattern))
            else:
                files = list(full_path.glob(pattern))
            
            # Convert to relative paths and sort
            rel_files = sorted([
                str(f.relative_to(full_path)) for f in files if f.is_file()
            ])
            
            return ToolResult(
                status=ToolResultStatus.SUCCESS,
                output=rel_files,
                metadata={"count": len(rel_files), "path": str(full_path)}
            )
        except Exception as e:
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


def get_file_tools(workspace_path: Optional[str] = None) -> list[BaseTool]:
    """Get all file tools configured for a workspace."""
    return [
        CreateFileTool(workspace_path),
        ReadFileTool(workspace_path),
        EditFileTool(workspace_path),
        WriteFileTool(workspace_path),
        DeleteFileTool(workspace_path),
        ListFilesTool(workspace_path),
    ]
