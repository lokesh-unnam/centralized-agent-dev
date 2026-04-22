"""
Scoring Engine - Evaluates generated agents against production standards.
Provides scores for: Functional, Robustness, Security, Readability.
"""
from __future__ import annotations
import json
import structlog
from typing import Any
from llm_client import call as llm_call

logger = structlog.get_logger(__name__)

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

## REWARDS
- +10 for comprehensive Pydantic validation.
- +10 for structured logging in every module.

Output JSON:
{
    "functional": {"score": 0, "justification": "..."},
    "robustness": {"score": 0, "justification": "..."},
    "security": {"score": 0, "justification": "..."},
    "readability": {"score": 0, "justification": "..."},
    "aggregate_score": 0
}
"""

class ScoringEngine:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model

    async def evaluate(self, spec: dict, files: list[dict]) -> dict:
        file_summary = "\n".join([f"--- {f['filename']} ---\n{f['content'][:1000]}" for f in files])
        context = f"SPEC:\n{json.dumps(spec)}\n\nCODEBASE:\n{file_summary}"
        
        response = await llm_call(
            system=SCORING_SYSTEM,
            user_message=context,
            model=self.model
        )
        
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            return json.loads(json_match.group())
        return {"aggregate_score": 0}
