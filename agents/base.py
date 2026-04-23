"""
Base ReAct Agent - Core Thinking Loop
"""
from __future__ import annotations
import json
import asyncio
from typing import Any, List, Optional, Dict
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
import structlog

from llm_client import call_with_messages as llm_call
from config import settings
from tools.registry import ToolRegistry

class AgentStatus:
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    SUCCESS = "success"
    FAILURE = "failure"

class AgentResult(BaseModel):
    status: str
    output: Optional[Any] = None
    thought_process: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    memory: Optional[Dict] = None

REACT_CORE_INSTRUCTIONS = """
## Response Format (STRICT)
You must output ONLY a JSON block. No pre-text, no post-text.

Example:
```json
{{
    "thought": "I need to initialize the database schema.",
    "is_complete": false,
    "tool_call": {{
        "tool_name": "write_file",
        "arguments": {{"path": "db.py", "content": "..."}}
    }}
}}
```

## Rules
1. NEVER output conversational text outside the JSON.
2. Complete the task step-by-step.
3. {tools_description}
"""

class ReActAgent(ABC):
    def __init__(
        self,
        tool_registry: ToolRegistry,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ):
        self.tool_registry = tool_registry
        self.model = model or settings.model_strong
        self.system_prompt = system_prompt or "You are an autonomous AI agent."
        self.status = AgentStatus.IDLE
        self.logger = structlog.get_logger(self.__class__.__name__)

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Subclasses must define their base prompt."""
        pass

    def get_tools_description(self) -> str:
        return self.tool_registry.get_tools_description()

    async def run(self, task: str, context: Optional[Dict] = None) -> AgentResult:
        self.logger.info("agent.start", task=task[:100])
        
        messages = [{"role": "user", "content": f"TASK: {task}\nCONTEXT: {json.dumps(context or {})}"}]
        thought_process = []
        
        combined_system = f"{self.get_system_prompt()}\n\n{REACT_CORE_INSTRUCTIONS}".format(
            tools_description=self.get_tools_description()
        )
        
        for step in range(15):  # Default 15 steps for v6
            self.status = AgentStatus.THINKING
            try:
                response_text = await llm_call(
                    system=combined_system,
                    messages=messages,
                    model=self.model
                )
                
                # Parse JSON
                import re
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if not json_match:
                    raise ValueError(f"No JSON found in response: {response_text[:100]}...")
                
                response = json.loads(json_match.group())
                thought = response.get("thought", "No thought provided")
                thought_process.append(thought)
                self.logger.info("agent.thought", thought=thought)
                
                if response.get("is_complete"):
                    self.status = AgentStatus.SUCCESS
                    return AgentResult(
                        status=AgentStatus.SUCCESS,
                        output=response.get("final_answer"),
                        thought_process=thought_process
                    )
                
                tool_call = response.get("tool_call")
                if tool_call:
                    tool_name = tool_call.get("tool_name")
                    args = tool_call.get("arguments", {})
                    
                    self.status = AgentStatus.ACTING
                    self.logger.info("agent.act", tool=tool_name, args=args)
                    
                    observation = self.tool_registry.execute(tool_name, **args)
                    
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "user", "content": f"OBSERVATION: {observation}"})
                
            except Exception as e:
                self.logger.error("agent.error", error=str(e))
                return AgentResult(status=AgentStatus.FAILURE, error=str(e), thought_process=thought_process)
        
        return AgentResult(status=AgentStatus.FAILURE, error="Max steps reached", thought_process=thought_process)
