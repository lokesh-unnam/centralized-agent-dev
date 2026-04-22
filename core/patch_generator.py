"""
Patch Generator - Produces atomic edits for existing files using the edit_file tool.
Prevents full file regeneration.
"""
from __future__ import annotations
import json
import structlog
from llm_client import call as llm_call

logger = structlog.get_logger(__name__)

PATCH_SYSTEM = """You are a Senior Software Engineer. Your task is to generate a PATCH 
to fix a specific bug in a file. 

## RULES
1. Ensure patch compiles after applying.
2. DO NOT change unrelated code.
3. Verify old_content exists EXACTLY once in the provided file.
4. Patch must fix the root cause only.
5. NO explanations. Output ONLY the JSON.

Output JSON:
{
    "patches": [
        {"path": "core/engine.py", "old_content": "...", "new_content": "..."}
    ]
}
"""

class PatchGenerator:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model

    async def generate_patches(self, file_content: str, error_report: str, path: str) -> list[dict]:
        context = f"FILE PATH: {path}\nFILE CONTENT:\n{file_content}\n\nERROR REPORT:\n{error_report}"
        response = await llm_call(
            system=PATCH_SYSTEM,
            user_message=context,
            model=self.model
        )
        
        import re
        json_match = re.search(r'\{[\s\S]*\}', response)
        if json_match:
            data = json.loads(json_match.group())
            return data.get("patches", [])
        return []
