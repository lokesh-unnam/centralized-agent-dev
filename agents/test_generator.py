"""
Test Generator Agent - Produces pytest suites for the generated agent.
"""
from __future__ import annotations
import json
import structlog
from llm_client import call as llm_call

logger = structlog.get_logger(__name__)

TEST_SYSTEM = """You are a Senior SDET. Your task is to generate a comprehensive 
pytest suite for the provided AI agent codebase.

## RULES
- Tests MUST be deterministic.
- Mock ALL external APIs and network calls.
- Ensure tests run without any external dependencies.

## COVERAGE
- Normal cases (Happy path).
- Edge cases (Empty/null inputs, boundary conditions).
- Invalid inputs (Type errors, schema violations).
- Constraint validation from the spec.

Output ONLY the raw code for 'tests/test_agent.py'.
"""

class TestGeneratorAgent:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model

    async def generate_tests(self, spec: dict, files: list[dict]) -> str:
        file_summary = "\n".join([f"--- {f['filename']} ---\n{f['content']}" for f in files])
        context = f"SPEC:\n{json.dumps(spec)}\n\nCODEBASE:\n{file_summary}"
        
        response = await llm_call(
            system=TEST_SYSTEM,
            user_message=context,
            model=self.model
        )
        return response
