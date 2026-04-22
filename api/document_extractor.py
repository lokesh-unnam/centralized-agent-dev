"""
Document Extractor - The "Context Compressor" for large technical recipes.

Problem: A 47,000-char, 800-line document cannot be dumped directly into a prompt.
Solution: LLM extracts only what matters for code generation — inputs, outputs, 
business logic steps, constraints, API calls, data schemas, edge cases.

Output is ~2000-4000 chars regardless of input size.
"""
from __future__ import annotations
import re
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from llm_client import call as llm_call
from config import settings

logger = structlog.get_logger(__name__)

MAX_RAW_CHARS = 40_000   # Hard ceiling before chunking kicks in
TARGET_OUTPUT = 4_000    # Target size of extracted recipe in chars

EXTRACTOR_SYSTEM = """You are a technical analyst extracting structured information from documents
to help an AI generate production-grade LLM workflow code.

Extract ONLY information that is directly useful for code generation:

1. FUNCTIONAL STEPS — the exact step-by-step business logic (preserve all steps, do not summarize)
2. INPUTS — every data field the workflow receives (name, type, source, required/optional)
3. OUTPUTS — every data field the workflow returns (name, type, format)
4. EXTERNAL APIs / SERVICES — API names, endpoints, auth methods, request/response formats
5. DATA SCHEMAS — any JSON structures, database schemas, or data formats described
6. CONSTRAINTS — rules that must never be violated (validation rules, rate limits, security)
7. EDGE CASES — boundary conditions, error states, exceptional inputs explicitly mentioned
8. TECHNICAL DEPENDENCIES — libraries, SDKs, models, tools referenced

RULES:
- Be extremely precise. 
- Preserve the "HOW" (the internal logic), not just the "WHAT".
- Use technical language. 
- Ignore marketing fluff, intros, and filler text.
- If the document describes a state machine or graph, describe the nodes and edges clearly.
"""

class DocumentExtractor:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.logger = structlog.get_logger("DocumentExtractor")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def extract_recipe(self, raw_text: str) -> str:
        """Extract a structured technical recipe from raw document text."""
        
        self.logger.info("extractor.start", raw_size=len(raw_text))
        
        # If the doc is too big, take the most important parts (usually beginning and end) 
        # or implement full map-reduce if needed. For v1, we take the top 40k chars.
        text_to_process = raw_text[:MAX_RAW_CHARS]
        
        prompt = f"### RAW TECHNICAL SPECIFICATION:\n{text_to_process}\n\n### INSTRUCTIONS:\nExtract the structured Code Generation Recipe following the system instructions."
        
        try:
            response = await llm_call(
                system=EXTRACTOR_SYSTEM,
                user_message=prompt,
                model=self.model,
                temperature=0.0 # Strict extraction
            )
            
            self.logger.info("extractor.complete", extracted_size=len(response))
            return response
            
        except Exception as e:
            self.logger.error("extractor.failed", error=str(e))
            raise
