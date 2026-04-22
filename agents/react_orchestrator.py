"""
React Orchestrator v5 - The Master Pipeline for Agent Generation.
Implements the full 13-step autonomous generation loop.
"""
from __future__ import annotations
import asyncio
import json
import structlog
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from agents.react_planner import SpecBuilderAgent
from agents.architecture_planner import ArchitecturePlanner
from agents.task_planner import TaskPlanner
from agents.coder import CoderAgent, DebuggerAgent, ReviewerAgent
from agents.test_generator import TestGeneratorAgent
from agents.finalization import FinalizationAgent
from api.document_extractor import DocumentExtractor
from core.scoring import ScoringEngine
from core.patch_generator import PatchGenerator
from tools.registry import get_tool_registry
from checkpoints import CheckpointManager, CheckpointType

logger = structlog.get_logger(__name__)

class ReactOrchestrator:
    def __init__(self, config: Any = None):
        self.workflow_id = f"v5_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.workspace_path = Path("output") / self.workflow_id
        self.workspace_path.mkdir(parents=True, exist_ok=True)
        
        self.tool_registry = get_tool_registry(str(self.workspace_path))
        self.checkpoint_manager = CheckpointManager(interactive=True)
        
        # 13-Step Pipeline Agents
        self.extractor = DocumentExtractor()
        self.normalizer = SpecBuilderAgent(self.tool_registry)
        self.arch_planner = ArchitecturePlanner()
        self.task_planner = TaskPlanner()
        self.coder = CoderAgent(self.tool_registry)
        self.test_gen = TestGeneratorAgent()
        self.scorer = ScoringEngine()
        self.debugger = DebuggerAgent(self.tool_registry)
        self.patcher = PatchGenerator()
        self.finalizer = FinalizationAgent()
        
        self.logger = structlog.get_logger("OrchestratorV5")

    async def generate(self, raw_input: str) -> dict:
        self.logger.info("orchestrator.v5.start", workflow_id=self.workflow_id)
        
        # Initialize default scores to prevent NameError
        scores = {"aggregate_score": 0}
        
        # 1. Document Parser / 2. Semantic Extractor
        recipe = await self.extractor.extract_recipe(raw_input)
        
        # 3. Spec Normalizer
        spec = await self.normalizer.build_spec(recipe)
        
        # 4. Architecture Planner
        arch = await self.arch_planner.define_structure(spec)
        
        # 5. Task Planner / 6. Task Graph Builder
        dag = await self.task_planner.create_dag(spec, arch)
        
        # 7. Modular Code Generator (File-by-File Execution)
        for file_meta in arch.get("files", []):
            filename = file_meta["filename"]
            self.logger.info("orchestrator.generating_file", file=filename)
            
            # Pass FULL FILE CONTEXT (filename + existing contents)
            context = {
                "spec": spec,
                "arch": arch,
                "target_file": filename,
                "existing_files": self._collect_files() 
            }
            
            # Implementation request
            prompt = f"Implement the file '{filename}' based on the architecture responsibility: {file_meta['responsibility']}"
            code_output = await self.coder.run(prompt, context)
            
            # Hard Validation Step (AST Parse + Syntax Check)
            if not self._validate_code_syntax(code_output, filename):
                self.logger.warning("orchestrator.syntax_error", file=filename)
                # Trigger immediate retry with context
                code_output = await self.coder.run(f"FIX SYNTAX ERROR in {filename}. Previous output failed AST parse.", context)

            # Write file
            self.tool_registry.execute("write_file", path=filename, content=code_output)

        # 8. Static Analyzer
        lint_result = self.tool_registry.execute("lint_code", path=".")
        
        # 9. Test Generator
        current_files = self._collect_files()
        tests = await self.test_gen.generate_tests(spec, current_files)
        self.workspace_path.joinpath("tests").mkdir(parents=True, exist_ok=True)
        self.workspace_path.joinpath("tests/test_agent.py").write_text(tests)

        # 10. Execution + Scoring Engine (Iteration Loop)
        iteration = 0
        while iteration < 5:
            self.logger.info("orchestrator.iteration", num=iteration)
            
            # Execute tests - FIX BUG 5: tool name and param
            test_exec = self.tool_registry.execute("execute_command", command="pytest tests/test_agent.py")
            
            # Score codebase
            scores = await self.scorer.evaluate(spec, self._collect_files())
            self.logger.info("orchestrator.scores", score=scores.get("aggregate_score", 0))
            
            if scores.get("aggregate_score", 0) >= 80:
                break
                
            # 11. Debugger Agent / 12. Patch Generator
            report = f"Test Result: {test_exec.output}\nScores: {json.dumps(scores)}"
            for f in self._collect_files():
                patches = await self.patcher.generate_patches(f["content"], report, f["filename"])
                for p in patches:
                    self.tool_registry.execute("edit_file", path=p["path"], old_content=p["old_content"], new_content=p["new_content"])
            
            iteration += 1

        # 13. Finalizer + Report Generator
        # FIX BUG 8: Pass list instead of dict (updating finalizer to handle list)
        meta_files = await self.finalizer.finalize_project(spec, arch, self._collect_files())
        for mf in meta_files:
             dest = self.workspace_path / mf["filename"]
             dest.parent.mkdir(parents=True, exist_ok=True)
             dest.write_text(mf["content"])

        # Add README.md and .env.example
        self._generate_boilerplate(spec)

        return {
            "status": "success", 
            "workflow_id": self.workflow_id, 
            "path": str(self.workspace_path), 
            "final_score": scores.get("aggregate_score", 0),
            "files": [f["filename"] for f in self._collect_files()]
        }

    def _validate_code_syntax(self, code: str, filename: str) -> bool:
        """Perform hard validation using AST parsing."""
        import ast
        try:
            ast.parse(code)
            return True
        except Exception as e:
            self.logger.error("code.syntax_invalid", file=filename, error=str(e))
            return False

    def _collect_files(self):
        files = []
        for p in self.workspace_path.rglob("*.py"):
            if p.is_file():
                try:
                    files.append({"filename": str(p.relative_to(self.workspace_path)), "content": p.read_text(encoding="utf-8")})
                except Exception:
                    continue
        return files

    def _generate_boilerplate(self, spec):
        name = spec.get("agent_name", "agent")
        purpose = spec.get("purpose", "")
        readme = f"# {name}\n\n{purpose}\n\n## Usage\n```python\nfrom agent import execute\n```"
        self.workspace_path.joinpath("README.md").write_text(readme)
        self.workspace_path.joinpath(".env.example").write_text("OPENAI_API_KEY=your_key_here")
        self.workspace_path.joinpath("requirements.txt").write_text("openai\npydantic\nstructlog\npytest")
