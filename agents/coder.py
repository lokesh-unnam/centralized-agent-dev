"""
Coder Agent - Generates code files incrementally using ReAct loop.
"""
from __future__ import annotations
from typing import Any, Optional
import structlog

from agents.base import ReActAgent, AgentResult, REACT_SYSTEM_PROMPT
from tools.registry import ToolRegistry
from config import settings

logger = structlog.get_logger(__name__)


CODER_SYSTEM_PROMPT = """You are an elite Senior Python Engineer.

## OBJECTIVE
Generate ONE production-grade file with complete, correct, and executable code.

## CONTEXT RULES
You are given:
- Spec (The requirements)
- Target filename (What you are building)
- Dependencies (Existing files and their contents)

You MUST ONLY use provided context.

## STRICT CONSTRAINTS
- Output ONLY valid Python code (NO explanations).
- DO NOT import non-existent modules.
- DO NOT assume hidden files.
- If dependency missing → create safe fallback or error.
- NO placeholders (no pass, no TODO, no "implement here").

## ENGINEERING RULES
- Use Pydantic for all inputs/outputs.
- Use structured logging (structlog).
- Add try/except for all business logic.
- Use type hints everywhere.
- Add Google-style docstrings.

## DEPENDENCY RULES
- Only import from provided files or standard library.
- Use absolute imports (e.g., `from core.logic import Logic`).
- Ensure all imports are valid and exist in the provided context.

## OUTPUT FORMAT (STRICT)
- ONLY raw Python code.
- No markdown code blocks (```python).
- Must compile and pass lint.

## SELF-CHECK (MANDATORY BEFORE OUTPUT)
1. Are all imports valid?
2. Does code compile?
3. Are all functions fully implemented?
4. Is error handling present?

Only output after all checks pass.
"""

SCORING_SYSTEM = """You are a Senior QA Auditor. Evaluate the generated AI agent codebase.
You must provide 4 scores (0-100) and a detailed justification.

## EVALUATION CRITERIA
1. FUNCTIONAL_SCORE: Does it implement all requirements?
2. ROBUSTNESS_SCORE: Does it handle edge cases and errors?
3. SECURITY_SCORE: Is data handling and validation secure?
4. READABILITY_SCORE: Clean code, type hints, logging?

## PENALTIES
- -50 for missing mandatory files (config.py, agent.py).
- -30 for invalid imports or syntax errors.
- -20 for placeholders (pass, TODO).

Output JSON:
{
    "functional": {"score": 0, "justification": "..."},
    "robustness": {"score": 0, "justification": "..."},
    "security": {"score": 0, "justification": "..."},
    "readability": {"score": 0, "justification": "..."},
    "aggregate_score": 0
}
"""

PATCH_SYSTEM = """You are a Senior Software Engineer. Your task is to generate a PATCH 
to fix a specific bug in a file. 

Rules:
1. Ensure patch compiles after applying.
2. DO NOT change unrelated code.
3. Verify old_content exists EXACTLY once.
4. Patch must fix the root cause only.
5. NO explanations.

Output JSON:
{
    "patches": [
        {"path": "core/engine.py", "old_content": "...", "new_content": "..."}
    ]
}
"""

DEBUG_SYSTEM = """You are a Senior Debugging Engineer.

## OBJECTIVE
Identify ROOT CAUSE and apply MINIMAL FIX.

## RULES
- Fix ONLY the broken part.
- DO NOT rewrite entire file.
- Preserve working logic.

## PROCESS
1. Identify error location.
2. Identify root cause.
3. Apply minimal fix.
4. Verify fix logically.

## OUTPUT CONTRACT (STRICT JSON ONLY)
{
  "root_cause": "...",
  "fix_strategy": "...",
  "affected_files": ["..."]
}
"""

TEST_SYSTEM = """You are a Senior SDET. Your task is to generate a comprehensive 
pytest suite for the provided AI agent codebase.

## RULES
- Tests MUST be deterministic.
- Mock ALL external APIs.
- Ensure tests run without network dependency.

## COVERAGE
- Normal cases (Happy path).
- Edge cases (Empty/null inputs).
- Invalid inputs (Type errors).
- Constraint validation.

Output ONLY the raw code for 'tests/test_agent.py'.
"""


class CoderAgent(ReActAgent):
    """Agent specialized in code generation."""
    
    name = "coder"
    description = "Generates production-quality code files"
    max_steps = 100  # More steps for complex code generation
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        model: Optional[str] = None,
    ):
        super().__init__(tool_registry, model or settings.model_strong)
        self.system_prompt = CODER_SYSTEM_PROMPT
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    async def generate_file(
        self,
        filename: str,
        description: str,
        spec: dict[str, Any],
        existing_files: Optional[list[str]] = None,
    ) -> AgentResult:
        """Generate a single file based on spec."""
        
        context = {
            "filename": filename,
            "spec": spec,
            "existing_files": existing_files or [],
        }
        
        task = f"""Generate the file '{filename}' with the following requirements:

{description}

Spec Context:
- Name: {spec.get('name', 'agent')}
- Description: {spec.get('description', '')}
- Inputs: {spec.get('inputs', [])}
- Outputs: {spec.get('outputs', [])}
- Constraints: {spec.get('constraints', [])}

Existing files in project: {existing_files or 'None yet'}

Steps:
1. Create the file with complete, working code
2. Lint the file to check for errors
3. Fix any lint errors
4. Confirm the file is complete

When done, summarize what the file does."""
        
        return await self.run(task, context)
    
    async def generate_project(
        self,
        spec: dict[str, Any],
        plan: list[dict[str, Any]],
    ) -> AgentResult:
        """Generate a complete project based on spec and plan."""
        
        files_desc = "\n".join(
            f"- {step.get('filename', step.get('description', 'file'))}: {step.get('description', '')}"
            for step in plan
        )
        
        context = {
            "spec": spec,
            "plan": plan,
        }
        
        task = f"""Generate a complete Python project based on this spec:

Name: {spec.get('name', 'agent')}
Description: {spec.get('description', '')}

Files to create:
{files_desc}

Requirements:
1. Create each file with complete, working code
2. Ensure all imports are valid (reference files you've created)
3. Lint each file after creation
4. The main entry point should be in workflow.py with an execute() function
5. Include workflow_config.json with project metadata

After creating all files, run a final lint check on the entire project.

When complete, list all files created and confirm the project is ready."""
        
        return await self.run(task, context)


class DebuggerAgent(ReActAgent):
    """Agent specialized in debugging and fixing code."""
    
    name = "debugger"
    description = "Debugs and fixes code issues"
    max_steps = 30
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        model: Optional[str] = None,
    ):
        super().__init__(tool_registry, model or settings.model_strong)
        self.system_prompt = DEBUG_SYSTEM
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    async def fix_errors(
        self,
        errors: list[dict[str, Any]],
        files: list[str],
    ) -> AgentResult:
        """Fix errors in the specified files."""
        
        error_desc = "\n".join(
            f"- {e.get('file', 'unknown')}:{e.get('line', '?')}: {e.get('message', e.get('error', 'error'))}"
            for e in errors
        )
        
        context = {
            "errors": errors,
            "files": files,
        }
        
        task = f"""Fix the following errors:

{error_desc}

Steps:
1. For each error, read the relevant file
2. Identify the issue
3. Apply the minimal fix
4. Lint the file to verify the fix
5. Continue until all errors are resolved

When done, confirm all errors are fixed."""
        
        return await self.run(task, context)


REVIEWER_SYSTEM_PROMPT = """You are an expert code reviewer.
Your task is to review generated code for quality, correctness, and completeness.

## Review Checklist
1. All required files are present
2. Code is syntactically correct (no lint errors)
3. All imports are valid
4. Functions have proper signatures and types
5. Error handling is present
6. Logging is implemented
7. The main entry point works

## Review Process
1. List all files in the project
2. Read each file and analyze
3. Run lint on all files
4. Run tests if present
5. Note any issues found
6. Fix critical issues

{tools_description}
"""


class ReviewerAgent(ReActAgent):
    """Agent specialized in code review."""
    
    name = "reviewer"
    description = "Reviews code for quality and correctness"
    max_steps = 30
    
    def __init__(
        self,
        tool_registry: ToolRegistry,
        model: Optional[str] = None,
    ):
        super().__init__(tool_registry, model or settings.model_fast)
        self.system_prompt = REVIEWER_SYSTEM_PROMPT
    
    def get_system_prompt(self) -> str:
        return self.system_prompt
    
    async def review_project(self, project_path: str = ".") -> AgentResult:
        """Review all code in a project."""
        
        task = f"""Review the code in '{project_path}':

1. List all Python files
2. Run lint on the entire project
3. Read the main workflow.py file
4. Check that all required functions exist
5. Verify imports are correct
6. Fix any critical issues found

Provide a summary with:
- Files reviewed
- Issues found (if any)
- Overall quality assessment"""
        
        return await self.run(task, {"project_path": project_path})
