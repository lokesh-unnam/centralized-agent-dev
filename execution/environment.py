"""
Execution Environment - Hybrid sandbox/real execution management.
"""
from __future__ import annotations
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional
from enum import Enum
import structlog

from tools.base import BaseTool, ToolResult, ToolResultStatus

logger = structlog.get_logger(__name__)


class ExecutionMode(str, Enum):
    SANDBOX = "sandbox"
    REAL = "real"
    HYBRID = "hybrid"


class ExecutionEnvironment:
    """Manages hybrid sandbox/real execution for agent generation."""
    
    def __init__(
        self,
        workspace_path: Path,
        mode: ExecutionMode = ExecutionMode.HYBRID,
        sandbox_enabled: bool = True,
    ):
        self.workspace_path = Path(workspace_path)
        self.mode = mode
        self.sandbox_enabled = sandbox_enabled
        
        # Create workspace
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        # Sandbox directory (temporary)
        self.sandbox_path: Optional[Path] = None
        if sandbox_enabled:
            self.sandbox_path = Path(tempfile.mkdtemp(prefix="agent_sandbox_"))
        
        self._current_mode = ExecutionMode.SANDBOX if sandbox_enabled else ExecutionMode.REAL
        self.logger = structlog.get_logger("ExecutionEnvironment")
        
        self.logger.info(
            "environment.initialized",
            workspace=str(self.workspace_path),
            sandbox=str(self.sandbox_path) if self.sandbox_path else None,
            mode=self._current_mode.value,
        )
    
    @property
    def active_path(self) -> Path:
        """Get the currently active working path."""
        if self._current_mode == ExecutionMode.SANDBOX and self.sandbox_path:
            return self.sandbox_path
        return self.workspace_path
    
    def execute_tool(self, tool: BaseTool, **kwargs) -> ToolResult:
        """Execute a tool in the appropriate environment."""
        
        # Update tool's workspace path based on current mode
        original_workspace = tool.workspace_path
        tool.workspace_path = str(self.active_path)
        
        try:
            result = tool(**kwargs)
            
            self.logger.debug(
                "environment.tool_executed",
                tool=tool.name,
                mode=self._current_mode.value,
                success=result.success,
            )
            
            return result
        finally:
            tool.workspace_path = original_workspace
    
    def switch_to_sandbox(self) -> None:
        """Switch execution to sandbox mode."""
        if not self.sandbox_path:
            self.logger.warning("environment.sandbox_not_available")
            return
        
        self._current_mode = ExecutionMode.SANDBOX
        self.logger.info("environment.switched_to_sandbox")
    
    def switch_to_real(self) -> None:
        """Switch execution to real workspace mode."""
        self._current_mode = ExecutionMode.REAL
        self.logger.info("environment.switched_to_real")
    
    def promote_to_real(self) -> bool:
        """Copy all files from sandbox to real workspace."""
        if not self.sandbox_path or not self.sandbox_path.exists():
            self.logger.warning("environment.no_sandbox_to_promote")
            return False
        
        try:
            # Copy all files from sandbox to workspace
            for item in self.sandbox_path.iterdir():
                dest = self.workspace_path / item.name
                
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
            
            self.logger.info(
                "environment.promoted_to_real",
                files=len(list(self.workspace_path.rglob("*"))),
            )
            
            self._current_mode = ExecutionMode.REAL
            return True
            
        except Exception as e:
            self.logger.error("environment.promote_failed", error=str(e))
            return False
    
    def reset_sandbox(self) -> None:
        """Clear sandbox and start fresh."""
        if self.sandbox_path and self.sandbox_path.exists():
            shutil.rmtree(self.sandbox_path)
            self.sandbox_path.mkdir(parents=True, exist_ok=True)
            self.logger.info("environment.sandbox_reset")
    
    def list_files(self, path: str = ".") -> list[str]:
        """List files in the active environment."""
        base = self.active_path / path
        if not base.exists():
            return []
        
        return [
            str(p.relative_to(self.active_path))
            for p in base.rglob("*")
            if p.is_file()
        ]
    
    def read_file(self, path: str) -> Optional[str]:
        """Read a file from the active environment."""
        file_path = self.active_path / path
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return None
    
    def write_file(self, path: str, content: str) -> bool:
        """Write a file to the active environment."""
        file_path = self.active_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            file_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False
    
    def cleanup(self) -> None:
        """Clean up sandbox (call when done)."""
        if self.sandbox_path and self.sandbox_path.exists():
            try:
                shutil.rmtree(self.sandbox_path)
                self.logger.info("environment.sandbox_cleaned")
            except Exception as e:
                self.logger.warning("environment.cleanup_failed", error=str(e))
    
    def get_status(self) -> dict[str, Any]:
        """Get current environment status."""
        sandbox_files = []
        workspace_files = []
        
        if self.sandbox_path and self.sandbox_path.exists():
            sandbox_files = self.list_files() if self._current_mode == ExecutionMode.SANDBOX else []
        
        if self._current_mode == ExecutionMode.REAL:
            workspace_files = [
                str(p.relative_to(self.workspace_path))
                for p in self.workspace_path.rglob("*")
                if p.is_file()
            ]
        
        return {
            "mode": self._current_mode.value,
            "workspace_path": str(self.workspace_path),
            "sandbox_path": str(self.sandbox_path) if self.sandbox_path else None,
            "sandbox_enabled": self.sandbox_enabled,
            "active_path": str(self.active_path),
            "sandbox_files": len(sandbox_files),
            "workspace_files": len(workspace_files),
        }
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


class WorkspaceManager:
    """Manages multiple workspaces for different generation sessions."""
    
    def __init__(self, base_path: str = "./output"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._environments: dict[str, ExecutionEnvironment] = {}
    
    def create_workspace(
        self,
        name: str,
        sandbox: bool = True,
    ) -> ExecutionEnvironment:
        """Create a new workspace environment."""
        workspace_path = self.base_path / name
        
        env = ExecutionEnvironment(
            workspace_path=workspace_path,
            sandbox_enabled=sandbox,
        )
        
        self._environments[name] = env
        return env
    
    def get_workspace(self, name: str) -> Optional[ExecutionEnvironment]:
        """Get an existing workspace."""
        return self._environments.get(name)
    
    def list_workspaces(self) -> list[str]:
        """List all workspace directories."""
        return [
            d.name for d in self.base_path.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
    
    def cleanup_all(self) -> None:
        """Clean up all environments."""
        for env in self._environments.values():
            env.cleanup()
        self._environments.clear()
