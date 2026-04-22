"""
ReAct Agent Base - Foundation for all agents using Think-Act-Observe loop.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
import json
import re
import structlog

from tools.base import BaseTool, ToolResult, ToolCall, Observation
from tools.registry import ToolRegistry
from llm_client import call_with_messages
from config import settings

logger = structlog.get_logger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVING = "observing"
    COMPLETE = "complete"
    ERROR = "error"


class Thought(BaseModel):
    """Agent's reasoning about current state."""
    reasoning: str
    is_complete: bool = False
    final_answer: Optional[Any] = None
    next_action: Optional[ToolCall] = None
    confidence: float = 0.8


class AgentMemory(BaseModel):
    """Memory for tracking agent state during execution."""
    task: str = ""
    thoughts: list[Thought] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    
    def add_thought(self, thought: Thought) -> None:
        self.thoughts.append(thought)
    
    def add_observation(self, tool_call: ToolCall, result: ToolResult) -> None:
        self.observations.append(Observation(tool_call=tool_call, result=result))
        
        # Track file operations
        if tool_call.tool_name in ("create_file", "write_file"):
            path = tool_call.arguments.get("path", "")
            if result.success and path:
                self.files_created.append(path)
        elif tool_call.tool_name == "edit_file":
            path = tool_call.arguments.get("path", "")
            if result.success and path:
                self.files_modified.append(path)
        
        # Track errors
        if not result.success:
            self.errors.append(f"{tool_call.tool_name}: {result.error}")
    
    def get_context_for_llm(self, max_observations: int = 10) -> str:
        """Get formatted context for LLM."""
        lines = [f"Task: {self.task}\n"]
        
        if self.files_created:
            lines.append(f"Files created: {', '.join(self.files_created)}")
        if self.files_modified:
            lines.append(f"Files modified: {', '.join(self.files_modified)}")
        if self.errors:
            lines.append(f"Errors encountered: {len(self.errors)}")
        
        # Recent observations
        recent = self.observations[-max_observations:]
        if recent:
            lines.append("\nRecent actions:")
            for obs in recent:
                status = "SUCCESS" if obs.result.success else "FAILED"
                output = str(obs.result.output)[:200] if obs.result.output else ""
                error = obs.result.error[:100] if obs.result.error else ""
                lines.append(f"  - {obs.tool_call.tool_name}: [{status}] {output or error}")
        
        return "\n".join(lines)


class AgentResult(BaseModel):
    """Result from agent execution."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    steps_taken: int = 0
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    memory: Optional[AgentMemory] = None


REACT_SYSTEM_PROMPT = """You are an autonomous AI agent that accomplishes tasks using available tools.

You operate in a THINK-ACT-OBSERVE loop:
1. THINK: Analyze the current state and decide what to do next
2. ACT: Call a tool to make progress
3. OBSERVE: Review the result and update your understanding

## Response Format
Always respond in this exact JSON format:
```json
{
    "thought": "Your reasoning about the current state and what to do next",
    "is_complete": false,
    "tool_call": {
        "tool_name": "name_of_tool",
        "arguments": {"arg1": "value1"}
    }
}
```

When the task is complete:
```json
{
    "thought": "Task completed because...",
    "is_complete": true,
    "final_answer": "Summary of what was accomplished"
}
```

## Rules
1. Always use tools to make progress - don't just think
2. After each tool call, wait for the observation before continuing
3. If a tool fails, analyze why and try a different approach
4. Complete the task step by step, don't try to do everything at once
5. When creating code, ensure it's complete and working
6. Test your work before declaring completion

{tools_description}
"""


class ReActAgent(ABC):
    """Base class for ReAct-style agents."""
    
    name: str = "react_agent"
    description: str = "A ReAct agent"
    max_steps: int = 50
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ):
        self.tool_registry = tool_registry
        self.model = model or settings.model_strong
        self.system_prompt = system_prompt or REACT_SYSTEM_PROMPT
        self.memory = AgentMemory()
        self.status = AgentStatus.IDLE
        self.logger = structlog.get_logger(self.__class__.__name__)
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get the system prompt for this agent."""
        pass
    
    def get_tools_description(self) -> str:
        """Get formatted tools for the system prompt."""
        return self.tool_registry.format_tools_for_prompt()
    
    async def run(self, task: str, context: Optional[dict[str, Any]] = None) -> AgentResult:
        """Execute the ReAct loop until task is complete or max steps reached."""
        self.memory = AgentMemory(task=task, context=context or {})
        self.status = AgentStatus.IDLE
        
        self.logger.info("agent.start", task=task[:100], max_steps=self.max_steps)
        
        messages = []
        system = self.get_system_prompt().format(
            tools_description=self.get_tools_description()
        )
        
        for step in range(self.max_steps):
            self.logger.info("agent.step", step=step + 1)
            
            # THINK
            self.status = AgentStatus.THINKING
            try:
                thought = await self._think(system, messages)
            except Exception as e:
                self.logger.error("agent.think_error", error=str(e))
                return AgentResult(
                    success=False,
                    error=f"Thinking error: {str(e)}",
                    steps_taken=step + 1,
                    memory=self.memory
                )
            
            self.memory.add_thought(thought)
            
            # Check completion
            if thought.is_complete:
                self.status = AgentStatus.COMPLETE
                self.logger.info("agent.complete", steps=step + 1)
                return AgentResult(
                    success=True,
                    output=thought.final_answer,
                    steps_taken=step + 1,
                    files_created=self.memory.files_created,
                    files_modified=self.memory.files_modified,
                    memory=self.memory
                )
            
            if not thought.next_action:
                self.logger.warning("agent.no_action")
                messages.append({
                    "role": "assistant",
                    "content": json.dumps({"thought": thought.reasoning, "is_complete": False})
                })
                messages.append({
                    "role": "user",
                    "content": "You must call a tool to make progress. What tool will you use?"
                })
                continue
            
            # ACT
            self.status = AgentStatus.ACTING
            tool_result = await self._act(thought.next_action)
            
            # OBSERVE
            self.status = AgentStatus.OBSERVING
            self.memory.add_observation(thought.next_action, tool_result)
            
            # Update messages for next iteration
            messages.append({
                "role": "assistant",
                "content": json.dumps({
                    "thought": thought.reasoning,
                    "is_complete": False,
                    "tool_call": thought.next_action.model_dump()
                })
            })
            messages.append({
                "role": "user",
                "content": f"Tool result:\n{tool_result}"
            })
        
        # Max steps reached
        self.status = AgentStatus.ERROR
        return AgentResult(
            success=False,
            error=f"Max steps ({self.max_steps}) reached without completing task",
            steps_taken=self.max_steps,
            files_created=self.memory.files_created,
            files_modified=self.memory.files_modified,
            memory=self.memory
        )
    
    async def _think(self, system: str, messages: list[dict]) -> Thought:
        """Generate next thought using LLM."""
        # Add context to first message
        if not messages:
            messages = [{
                "role": "user",
                "content": f"Task: {self.memory.task}\n\nContext:\n{self.memory.get_context_for_llm()}"
            }]
        
        response = call_with_messages(
            system=system,
            messages=messages,
            model=self.model,
            max_tokens=2000,
        )
        
        return self._parse_thought(response)
    
    def _parse_thought(self, response: str) -> Thought:
        """Parse LLM response into a Thought."""
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(response)
            
            thought = Thought(
                reasoning=data.get("thought", response),
                is_complete=data.get("is_complete", False),
                final_answer=data.get("final_answer"),
            )
            
            if data.get("tool_call"):
                tc = data["tool_call"]
                thought.next_action = ToolCall(
                    tool_name=tc.get("tool_name", ""),
                    arguments=tc.get("arguments", {}),
                    thought=thought.reasoning
                )
            
            return thought
            
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning("agent.parse_error", error=str(e), response=response[:200])
            return Thought(
                reasoning=response,
                is_complete=False,
            )
    
    async def _act(self, tool_call: ToolCall) -> ToolResult:
        """Execute a tool call."""
        self.logger.info("agent.act", tool=tool_call.tool_name, args=list(tool_call.arguments.keys()))
        
        tool = self.tool_registry.get(tool_call.tool_name)
        if not tool:
            return ToolResult(
                status="error",
                error=f"Tool not found: {tool_call.tool_name}"
            )
        
        return tool(**tool_call.arguments)
    
    # Sync version for compatibility
    def run_sync(self, task: str, context: Optional[dict[str, Any]] = None) -> AgentResult:
        """Synchronous version of run."""
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.run(task, context))
