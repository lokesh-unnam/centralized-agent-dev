"""
Integration tests — OpenAI strict version.
Tests the full pipeline wiring: state flows correctly through all nodes.
"""
import json
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("MODEL_STRONG", "gpt-4o")
os.environ.setdefault("MODEL_FAST", "gpt-4o-mini")

MOCK_SPEC = {
    "name": "echo_agent",
    "description": "Echoes the user's message back with a greeting.",
    "inputs": [{"name": "message", "type": "str", "required": True}],
    "outputs": [{"name": "reply", "type": "str"}],
    "constraints": [],
    "edge_cases": [],
    "success_criteria": [],
    "documents": [],
}

MOCK_WORKFLOW_CODE = '''import logging, json, openai
logger = logging.getLogger(__name__)
def execute(inputs): return {"reply": "ok"}
'''

@pytest.fixture
def state():
    from models.state import build_initial_state
    s = build_initial_state("echo_agent")
    s["user_input"] = "echo"
    return s

class TestSpecBuilder:
    def test_spec_builder_populates_state(self, state):
        from agents.spec_builder import run_spec_builder
        with patch("agents.spec_builder.llm_call") as mock_call:
            mock_call.side_effect = [json.dumps(MOCK_SPEC), json.dumps({"valid": True})]
            result = run_spec_builder(state)
        assert result["spec"]["name"] == "echo_agent"

class TestCodeGeneration:
    def test_code_generation_produces_code_files(self, state):
        from agents.code_generation import run_code_generation
        state["spec"] = MOCK_SPEC
        # Patch llm_call where it is used (core.system_compiler)
        with patch("core.system_compiler.llm_call") as mock_call:
            mock_call.return_value = json.dumps({
                "files": [{"filename": "workflow.py", "content": MOCK_WORKFLOW_CODE, "language": "python"}],
                "workflow_json": {"name": "echo_agent"}
            })
            result = run_code_generation(state)
        assert len(result["artifacts"]["code_files"]) >= 1
