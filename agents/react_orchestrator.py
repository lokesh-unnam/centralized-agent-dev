"""
v6 ReAct Orchestrator - With Persistent Intelligence (Memory)
"""
from __future__ import annotations
import os
import datetime
from typing import Dict, List
import structlog
from agents.coder import CoderAgent, ReviewerAgent
from tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)

class ReactOrchestrator:
    def __init__(self, tool_registry: ToolRegistry, output_dir: str):
        self.tool_registry = tool_registry
        self.output_dir = output_dir
        self.memory_path = os.path.join(output_dir, "memory.md")
        self.coder = CoderAgent(tool_registry)
        self.reviewer = ReviewerAgent()

    def log_memory(self, event: str, status: str, details: str):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        with open(self.memory_path, "a") as f:
            f.write(f"\n### [{timestamp}] {event}\n- **Status**: {status}\n- **Details**: {details}\n---\n")

    async def generate_project(self, spec: Dict, file_tree: List[str]):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        with open(self.memory_path, "w") as f:
            f.write(f"# Project Memory & Evolution Log\nStarted: {datetime.datetime.now().isoformat()}\n\n")

        for filename in file_tree:
            logger.info("orchestrator.processing", file=filename)
            self.log_memory(f"Start processing {filename}", "Success", "Initiating file generation.")
            
            # 1. Coder Generates
            result = await self.coder.run(f"Implement {filename} based on spec.", context={"spec": spec})
            
            # 2. Reviewer Audits
            review = await self.reviewer.review_code(filename, result.output or "", context={"spec": spec})
            
            if not review.get("approved"):
                self.log_memory(f"Reviewer Audit: {filename}", "Rejected", f"Issues: {review.get('issues')}")
                # Retry loop...
                result = await self.coder.run(f"REGENERATE {filename}. Issues: {review.get('issues')}", context={"spec": spec})
            
            self.log_memory(f"Coder: {filename}", "Success", "File implementation finalized.")
        
        return "Project generation complete."
