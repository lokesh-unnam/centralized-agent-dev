"""
Task Planner - Breaks implementation into atomic steps and generates a DAG.
"""
from __future__ import annotations
import json
import structlog
from typing import Any, Optional
from llm_client import call as llm_call

logger = structlog.get_logger(__name__)

TASK_SYSTEM = """You are a Technical Program Manager.

## OBJECTIVE
Break the architecture into ATOMIC, IMPLEMENTABLE tasks mapped to files or functions.

## RULES
- Each task MUST map to: exactly ONE file OR ONE function.
- Tasks must be executable independently.
- Tasks must define dependencies clearly.

## DAG RULES
- No circular dependencies.
- Leaf nodes first (models, utils).
- Root nodes last (agent, orchestration).

## VALIDATION CRITERIA
Each task MUST include:
- expected output (file or function).
- success condition (e.g., "file imports correctly", "Pydantic model validates").

## OUTPUT CONTRACT (STRICT JSON ONLY)
{
  "tasks": [
    {
      "id": "t1",
      "target": "models/state.py",
      "description": "Define Pydantic state model",
      "dependencies": [],
      "validation_criteria": [
        "File compiles",
        "Model validates input"
      ]
    }
  ],
  "implementation_order": ["t1", "t2", ...],
  "production_readiness_checklist": [...]
}
"""

class TaskPlanner:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model

    async def create_dag(self, spec: dict, arch: dict) -> dict:
        context = f"Spec: {json.dumps(spec)}\nArchitecture: {json.dumps(arch)}"
        response = await llm_call(
            system=TASK_SYSTEM,
            user_message=context,
            model=self.model
        )
        
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        return {"tasks": []}
