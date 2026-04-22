"""
Finalization Agent - Generates professional documentation and metadata for the agent.
Produces: claude.md, skills.md, workflow_config.json
"""
from __future__ import annotations
import json
import structlog
from typing import Any, Optional

from agents.base import ReActAgent, AgentResult
from llm_client import call as llm_call
from config import settings

logger = structlog.get_logger(__name__)

SKILLS_MD_SYSTEM = """You are a technical writer for a high-end AI engineering firm.
Generate a 'skills.md' file that describes the technical capabilities of this agent.
Focus on:
- Input/Output schemas.
- The specific business logic implemented (e.g., Sequence Strategy, Signal Mapping).
- Technical constraints and performance characteristics.
"""

CLAUDE_MD_SYSTEM = """You are an AI Architect.
Generate a 'claude.md' file that explains to OTHER AIs (like Claude or Devin) how to use this agent.
Include:
- The core mission of the agent.
- How to trigger the workflow.
- Key file dependencies.
- How to extend or modify the logic.
"""

class FinalizationAgent:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.logger = structlog.get_logger("FinalizationAgent")

    async def finalize_project(self, spec: dict, plan: dict, artifacts: dict) -> list[dict[str, str]]:
        """Generate the meta-files for the project."""
        workflow_name = spec.get("name", "agent")
        
        self.logger.info("finalization.start", project=workflow_name)
        
        meta_files = []
        
        # 1. Generate workflow_config.json
        config_data = {
            "name": workflow_name,
            "version": "1.0.0",
            "spec": spec,
            "plan": plan,
            "generated_at": "2026-04-22"
        }
        meta_files.append({
            "filename": "workflow_config.json",
            "content": json.dumps(config_data, indent=2),
            "language": "json"
        })

        # 2. Generate skills.md
        skills_md = await llm_call(
            system=SKILLS_MD_SYSTEM,
            user_message=f"Project Spec: {json.dumps(spec)}\nImplementation Plan: {json.dumps(plan)}\nFiles Created: {[f['filename'] for f in artifacts]}",
            model=self.model
        )
        meta_files.append({
            "filename": "skills.md",
            "content": skills_md,
            "language": "markdown"
        })

        # 3. Generate claude.md
        claude_md = await llm_call(
            system=CLAUDE_MD_SYSTEM,
            user_message=f"Project Spec: {json.dumps(spec)}\nArchitecture Overview: {json.dumps(plan)}",
            model=self.model
        )
        meta_files.append({
            "filename": "claude.md",
            "content": claude_md,
            "language": "markdown"
        })

        self.logger.info("finalization.complete", files=len(meta_files))
        return meta_files
