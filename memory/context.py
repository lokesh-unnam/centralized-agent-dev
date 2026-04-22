"""
Context Management - Tracks conversation and action context for agents.
"""
from __future__ import annotations
from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import json
import structlog

logger = structlog.get_logger(__name__)


class Message(BaseModel):
    """A message in the conversation."""
    role: str  # "user", "assistant", "system", "tool"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FileState(BaseModel):
    """State of a file in the workspace."""
    path: str
    exists: bool = True
    content_hash: Optional[str] = None
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    language: str = "python"
    line_count: int = 0


class ActionRecord(BaseModel):
    """Record of an action taken."""
    tool_name: str
    arguments: dict[str, Any]
    result_success: bool
    result_output: Optional[str] = None
    result_error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: int = 0


class ConversationContext(BaseModel):
    """Full context of a generation session."""
    session_id: str
    task: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    messages: list[Message] = Field(default_factory=list)
    actions: list[ActionRecord] = Field(default_factory=list)
    files: dict[str, FileState] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    
    def add_message(self, role: str, content: str, **metadata) -> None:
        """Add a message to the conversation."""
        self.messages.append(Message(role=role, content=content, metadata=metadata))
    
    def add_action(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        success: bool,
        output: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: int = 0,
    ) -> None:
        """Record an action."""
        self.actions.append(ActionRecord(
            tool_name=tool_name,
            arguments=arguments,
            result_success=success,
            result_output=output[:500] if output else None,
            result_error=error,
            duration_ms=duration_ms,
        ))
        
        # Track file changes
        if tool_name in ("create_file", "write_file") and success:
            path = arguments.get("path", "")
            if path:
                self.files[path] = FileState(path=path, exists=True)
        elif tool_name == "delete_file" and success:
            path = arguments.get("path", "")
            if path and path in self.files:
                self.files[path].exists = False
    
    def add_error(self, error: str) -> None:
        """Record an error."""
        self.errors.append(error)
    
    def set_variable(self, name: str, value: Any) -> None:
        """Set a context variable."""
        self.variables[name] = value
    
    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a context variable."""
        return self.variables.get(name, default)
    
    def get_recent_actions(self, n: int = 10) -> list[ActionRecord]:
        """Get the n most recent actions."""
        return self.actions[-n:]
    
    def get_failed_actions(self) -> list[ActionRecord]:
        """Get all failed actions."""
        return [a for a in self.actions if not a.result_success]
    
    def get_files_created(self) -> list[str]:
        """Get list of files created."""
        return [path for path, state in self.files.items() if state.exists]
    
    def format_for_llm(self, max_tokens: int = 4000) -> str:
        """Format context for inclusion in LLM prompt."""
        lines = [
            f"Session: {self.session_id}",
            f"Task: {self.task}",
            f"Started: {self.started_at.isoformat()}",
            "",
        ]
        
        # Files
        if self.files:
            lines.append("Files in workspace:")
            for path, state in self.files.items():
                status = "exists" if state.exists else "deleted"
                lines.append(f"  - {path} ({status})")
            lines.append("")
        
        # Recent actions
        recent = self.get_recent_actions(5)
        if recent:
            lines.append("Recent actions:")
            for action in recent:
                status = "OK" if action.result_success else "FAILED"
                lines.append(f"  - {action.tool_name}: [{status}]")
            lines.append("")
        
        # Errors
        if self.errors:
            lines.append(f"Errors encountered: {len(self.errors)}")
            for error in self.errors[-3:]:
                lines.append(f"  - {error[:100]}")
        
        result = "\n".join(lines)
        
        # Truncate if needed
        if len(result) > max_tokens * 4:  # Rough char estimate
            result = result[:max_tokens * 4] + "\n... (truncated)"
        
        return result
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "task": self.task,
            "started_at": self.started_at.isoformat(),
            "messages": len(self.messages),
            "actions": len(self.actions),
            "files": list(self.files.keys()),
            "errors": len(self.errors),
        }


class ContextManager:
    """Manages conversation contexts across sessions."""
    
    def __init__(self):
        self._contexts: dict[str, ConversationContext] = {}
    
    def create_context(self, session_id: str, task: str) -> ConversationContext:
        """Create a new context."""
        context = ConversationContext(session_id=session_id, task=task)
        self._contexts[session_id] = context
        return context
    
    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """Get a context by session ID."""
        return self._contexts.get(session_id)
    
    def delete_context(self, session_id: str) -> bool:
        """Delete a context."""
        if session_id in self._contexts:
            del self._contexts[session_id]
            return True
        return False
    
    def list_sessions(self) -> list[str]:
        """List all session IDs."""
        return list(self._contexts.keys())


# Global context manager
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get the global context manager."""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
