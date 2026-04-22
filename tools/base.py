"""
Base Tool System - Foundation for all tools in the ReAct agent loop.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)


class ToolResultStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PENDING_APPROVAL = "pending_approval"


class ToolResult(BaseModel):
    """Result from tool execution."""
    status: ToolResultStatus = ToolResultStatus.SUCCESS
    output: Any = None
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    @property
    def success(self) -> bool:
        return self.status == ToolResultStatus.SUCCESS
    
    def __str__(self) -> str:
        if self.success:
            return f"[SUCCESS] {self.output}"
        return f"[ERROR] {self.error}"


class ToolParameter(BaseModel):
    """Schema for a tool parameter."""
    name: str
    type: str  # "string", "integer", "boolean", "array", "object"
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[list[Any]] = None


class BaseTool(ABC):
    """Abstract base class for all tools."""
    
    name: str = "base_tool"
    description: str = "Base tool description"
    parameters: list[ToolParameter] = []
    requires_approval: bool = False
    sandbox_safe: bool = True  # Can run in sandbox
    
    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters."""
        pass
    
    def validate_params(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate parameters against schema."""
        for param in self.parameters:
            if param.required and param.name not in kwargs:
                return False, f"Missing required parameter: {param.name}"
            if param.name in kwargs:
                value = kwargs[param.name]
                if param.enum and value not in param.enum:
                    return False, f"Invalid value for {param.name}: {value}. Must be one of {param.enum}"
        return True, None
    
    def to_schema(self) -> dict[str, Any]:
        """Convert to JSON schema for LLM function calling."""
        properties = {}
        required = []
        
        for param in self.parameters:
            prop = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            if param.default is not None:
                prop["default"] = param.default
            properties[param.name] = prop
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        }
    
    def __call__(self, **kwargs) -> ToolResult:
        """Allow tool to be called directly."""
        valid, error = self.validate_params(**kwargs)
        if not valid:
            return ToolResult(status=ToolResultStatus.ERROR, error=error)
        
        self.logger.info(f"tool.execute", tool=self.name, params=list(kwargs.keys()))
        try:
            result = self.execute(**kwargs)
            self.logger.info(f"tool.complete", tool=self.name, success=result.success)
            return result
        except Exception as e:
            self.logger.error(f"tool.failed", tool=self.name, error=str(e))
            return ToolResult(status=ToolResultStatus.ERROR, error=str(e))


class ToolCall(BaseModel):
    """Represents a tool call from the LLM."""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    thought: Optional[str] = None  # Why the agent chose this tool


class Observation(BaseModel):
    """Observation after tool execution."""
    tool_call: ToolCall
    result: ToolResult
    timestamp: float = Field(default_factory=lambda: __import__('time').time())
