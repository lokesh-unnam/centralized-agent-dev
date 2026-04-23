"""
Coder Agent - Implements functional logic.
Reviewer Agent - Performs pre-execution audits.
"""
from __future__ import annotations
import json
from agents.base import ReActAgent
from llm_client import call as llm_call

CODER_SYSTEM_PROMPT = """You are a Senior Software Engineer. Your goal is to write clean, functional, and production-ready Python code.

## MANDATE: ACTUAL FUNCTIONAL LOGIC
- **NO PLACEHOLDERS**: You are strictly forbidden from using `# logic goes here`, `# TODO`, `# placeholder`, or empty `pass` statements.
- **REAL IMPLEMENTATION**: You must write the actual, functional code.
- **MODULE SECLUSION**: ONLY implement logic that belongs in the assigned file path.
- **COMMIT**: You MUST call the 'write_file' tool with the COMPLETE code before declaring completion.
- **PRODUCTION GRADE**: Include retry logic, detailed error handling, and structured logging in every file.
"""

class CoderAgent(ReActAgent):
    def get_system_prompt(self) -> str:
        return CODER_SYSTEM_PROMPT

REVIEWER_SYSTEM = """You are a Senior Code Auditor. Your role is to prevent bugs BEFORE execution.

## REVIEW CRITERIA
1. SPEC ADHERENCE: Does this code implement exactly what is in the requirements?
2. LOGICAL SOUNDNESS: Is there any circular logic or unhandled edge case?
3. BOUNDARY AUDIT: Reject files that contain logic belonging to other layers.
   - 'models/' files MUST NOT contain database connections or API logic.
   - 'services/' files MUST NOT contain core business workflows.
4. ZERO PLACEHOLDER POLICY: REJECT any code that uses "TODO", "pass", or "# Simulate".
5. IMPORTS: Are all imports valid?

## OUTPUT CONTRACT
Output JSON: {"approved": true/false, "issues": [], "fix_recommendations": ""}
"""

class ReviewerAgent:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model

    async def review_code(self, filename: str, code: str, context: dict) -> dict:
        prompt = f"Review the following code for '{filename}':\n\nCODE:\n{code}\n\nCONTEXT:\nSpec: {json.dumps(context.get('spec', {}))}"
        response = await llm_call(system=REVIEWER_SYSTEM, user_message=prompt, model=self.model)
        
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        return {"approved": False, "issues": ["Failed to parse review output"]}
