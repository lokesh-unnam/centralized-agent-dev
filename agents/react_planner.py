"""
Planner Agent - Creates execution plans for code generation.
"""
from __future__ import annotations
from typing import Any, Optional
import json
import structlog

from agents.base import ReActAgent, AgentResult
from tools.registry import ToolRegistry
from config import settings

logger = structlog.get_logger(__name__)


PLANNER_SYSTEM_PROMPT = """You are an elite Software Architect. Your task is to design a production-grade directory structure and implementation plan for an AI system.

## Architectural Mandate
1. MODULARITY: Do not create a flat file list. Organize the system into logical packages:
   - `core/`: Main orchestration and engine logic.
   - `services/` or `tools/`: External integrations and API clients.
   - `models/`: Pydantic data schemas and state definitions.
   - `utils/`: Reusable helpers (logging, config, prompts).
2. WIRING: Define how modules import each other. Use absolute package imports.
3. DEPENDENCY GRAPH: Ensure files are planned in an order where "leaf" nodes (utils, models) are built before "root" nodes (orchestrators).

## Output Format
Create a JSON plan with this structure:
{{
    "project_name": "name_in_snake_case",
    "system_type": "agent|pipeline|api",
    "framework": "custom|langgraph|fastapi",
    "directory_structure": ["core/", "models/", "utils/", "tools/"],
    "files": [
        {{
            "filename": "models/state.py",
            "description": "Pydantic state models",
            "responsibility": "Define the global state schema",
            "priority": 1
        }}
    ],
    "execution_order": ["models/state.py", "core/engine.py", "workflow.py"],
    "total_estimated_files": 10
}}

## Engineering Rules
- workflow.py remains the top-level entry point.
- Every directory must have a proper `__init__.py` if needed.
- Follow SOLID principles. Keep files focused on a single responsibility.

{tools_description}
"""


class PlannerAgent(ReActAgent):
    """Agent specialized in creating implementation plans."""
    
    name = "planner"
    description = "Creates detailed implementation plans"
    max_steps = 20
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        model: Optional[str] = None,
    ):
        super().__init__(tool_registry, model or settings.model_strong)
        self.system_prompt = PLANNER_SYSTEM_PROMPT
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    async def create_plan(
        self,
        spec: dict[str, Any],
        user_input: str,
    ) -> AgentResult:
        """Create an implementation plan from spec."""
        
        context = {
            "spec": spec,
            "user_input": user_input,
        }
        
        task = f"""Create an implementation plan for this project:

User Request:
{user_input}

Parsed Spec:
- Name: {spec.get('name', 'agent')}
- Description: {spec.get('description', '')}
- Inputs: {json.dumps(spec.get('inputs', []))}
- Outputs: {json.dumps(spec.get('outputs', []))}
- Constraints: {spec.get('constraints', [])}

Create a detailed plan with:
1. List of all files to create
2. What each file should contain
3. Dependencies between files
4. Order of implementation

Output the plan as JSON."""
        
        result = await self.run(task, context)
        
        # Try to extract plan from result
        if result.success and result.output:
            try:
                if isinstance(result.output, str):
                    # Try to parse JSON from output
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', result.output)
                    if json_match:
                        plan = json.loads(json_match.group())
                        result.output = plan
            except json.JSONDecodeError:
                pass
        
        return result


SPEC_BUILDER_SYSTEM_PROMPT = """You are an expert requirements analyst.
Your task is to convert user descriptions into a STRICT NORMALIZED SPECIFICATION for an AI agent.

## Normalized Spec Format
Create a JSON specification following this schema:
{{
    "agent_name": "project_name_snake_case",
    "purpose": "A one-sentence high-level goal",
    "inputs": [
        {{"name": "input_name", "type": "str|int|dict|list", "required": true, "description": "..."}}
    ],
    "outputs": [
        {{"name": "output_name", "type": "str|dict|list", "description": "..."}}
    ],
    "constraints": ["Mandatory rule 1", "Mandatory rule 2"],
    "tools": [
        {{"name": "tool_name", "description": "What it does", "parameters": {{}}}}
    ],
    "non_goals": ["What the agent will NOT do"],
    "error_modes": [
        {{"scenario": "API Timeout", "handling_strategy": "Retry with exponential backoff"}}
    ],
    "execution_flow": ["Step 1: Intake", "Step 2: Processing", "Step 3: Output"],
    "technical_requirements": {{
        "libraries": ["openai", "pydantic"],
        "python_version": "3.10+"
    }}
}}

## Extraction Rules
1. Be EXHAUSTIVE. Extract every constraint and edge case.
2. Define non-goals to prevent scope creep.
3. Map every potential failure to an Error Mode.
4. The purpose must be concise but powerful.

{tools_description}
"""


class SpecBuilderAgent(ReActAgent):
    """Agent specialized in building specifications from user input."""
    
    name = "spec_builder"
    description = "Converts user descriptions to structured specs"
    max_steps = 15
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        model: Optional[str] = None,
    ):
        super().__init__(tool_registry, model or settings.model_strong)
        self.system_prompt = SPEC_BUILDER_SYSTEM_PROMPT
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    async def build_spec(self, user_input: str) -> AgentResult:
        """Build a specification from user input."""
        
        task = f"""Convert this user request into a structured specification:

User Request:
{user_input}

Create a complete JSON specification with:
1. A clear snake_case name
2. Detailed description preserving all user requirements
3. All inputs with types
4. All outputs with types
5. Constraints and rules
6. Edge cases to handle
7. Measurable success criteria

Output only the JSON specification."""
        
        result = await self.run(task, {"user_input": user_input})
        
        # Try to extract spec from result
        if result.success and result.output:
            try:
                if isinstance(result.output, str):
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', result.output)
                    if json_match:
                        spec = json.loads(json_match.group())
                        result.output = spec
            except json.JSONDecodeError:
                pass
        
        return result
