"""
Unit tests — no LLM calls, no network.
Covers: state model, lint checker, memory engine, weighted accuracy,
        sandbox, lint circuit breaker, distribution enforcement, and all audit fixes.
"""
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
os.environ.setdefault("MODEL_STRONG", "gpt-4o")
os.environ.setdefault("MODEL_FAST", "gpt-4o-mini")


# ── State model ───────────────────────────────────────────────────────────────

class TestStateModel:
    def test_all_keys_present(self):
        from models.state import build_initial_state
        state = build_initial_state("test_agent")
        for key in ["meta", "spec", "artifacts", "execution", "evaluation",
                    "patch", "memory", "escalation", "lint_retries", "user_input"]:
            assert key in state, f"Missing key: {key}"

    def test_user_input_declared_in_typeddict(self):
        from models.state import WorkflowState
        assert "user_input" in WorkflowState.__annotations__

    def test_lint_retries_declared_in_typeddict(self):
        from models.state import WorkflowState
        assert "lint_retries" in WorkflowState.__annotations__

    def test_initial_lint_retries_is_zero(self):
        from models.state import build_initial_state
        assert build_initial_state("x")["lint_retries"] == 0

    def test_initial_user_input_is_none(self):
        from models.state import build_initial_state
        assert build_initial_state("x")["user_input"] is None

    def test_workflow_ids_are_unique(self):
        from models.state import build_initial_state
        assert build_initial_state("a")["meta"]["workflow_id"] != build_initial_state("b")["meta"]["workflow_id"]

    def test_test_case_type_validation(self):
        from models.state import TestCase
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            TestCase(test_id="T1", input={}, expected_output={}, type="bad_type")

    def test_agent_patch_accepts_file_patch_objects(self):
        """Audit fix #2 — AgentPatch.patches must accept FilePatch objects directly."""
        from models.state import AgentPatch, FilePatch
        fp = FilePatch(filename="workflow.py", original="a", patched="b", diff="")
        patch = AgentPatch(required=True, target_files=["workflow.py"], patches=[fp])
        assert patch.patches[0].filename == "workflow.py"


# ── Lint checker ──────────────────────────────────────────────────────────────

VALID_WORKFLOW = '''import logging, openai
logger = logging.getLogger(__name__)
def validate_inputs(inputs): logger.info("[w][v] ok")
def process(inputs): logger.info("[w][p] ok"); return {}
def format_output(raw): logger.info("[w][f] ok"); return raw
def execute(inputs):
    logger.info("[w][e] ok")
    validate_inputs(inputs)
    return format_output(process(inputs))
'''


class TestLintChecker:
    def _state(self, files):
        from models.state import build_initial_state
        s = build_initial_state("lint_test")
        s["artifacts"]["code_files"] = files
        return s

    def test_valid_workflow_passes(self):
        from execution.lint_check import run_lint_check
        assert run_lint_check(self._state([
            {"filename": "workflow.py", "content": VALID_WORKFLOW, "language": "python"}
        ]))["lint_passed"] is True

    def test_syntax_error_fails(self):
        from execution.lint_check import run_lint_check
        r = run_lint_check(self._state([
            {"filename": "workflow.py", "content": "def broken(\n  pass", "language": "python"}
        ]))
        assert r["lint_passed"] is False
        assert any(e["error_type"] == "SyntaxError" for e in r["execution"]["errors"])

    def test_missing_execute_fails(self):
        from execution.lint_check import run_lint_check
        code = "import logging,openai\nlogger=logging.getLogger(__name__)\n" \
               "def validate_inputs(x): pass\ndef process(x): pass\ndef format_output(x): pass\n"
        assert run_lint_check(self._state([
            {"filename": "workflow.py", "content": code, "language": "python"}
        ]))["lint_passed"] is False

    def test_helper_file_skips_required_pattern_check(self):
        """Audit fix #7 — utils.py must NOT fail for missing execute/validate_inputs."""
        from execution.lint_check import run_lint_check
        helper = "import logging\nlogger=logging.getLogger(__name__)\ndef helper(): pass\n"
        assert run_lint_check(self._state([
            {"filename": "workflow.py", "content": VALID_WORKFLOW, "language": "python"},
            {"filename": "utils.py", "content": helper, "language": "python"},
        ]))["lint_passed"] is True

    def test_valid_json_passes(self):
        from execution.lint_check import run_lint_check
        assert run_lint_check(self._state([
            {"filename": "config.json", "content": '{"name":"test"}', "language": "json"}
        ]))["lint_passed"] is True

    def test_invalid_json_fails(self):
        from execution.lint_check import run_lint_check
        assert run_lint_check(self._state([
            {"filename": "config.json", "content": '{broken}', "language": "json"}
        ]))["lint_passed"] is False

    def test_no_files_passes(self):
        from execution.lint_check import run_lint_check
        assert run_lint_check(self._state([]))["lint_passed"] is True

    def test_missing_logging_fails_on_workflow(self):
        from execution.lint_check import run_lint_check
        code = "import anthropic\ndef validate_inputs(x): pass\ndef process(x): pass\n" \
               "def format_output(x): pass\ndef execute(x): pass\n"
        assert run_lint_check(self._state([
            {"filename": "workflow.py", "content": code, "language": "python"}
        ]))["lint_passed"] is False

    def test_missing_openai_fails_on_workflow(self):
        from execution.lint_check import run_lint_check
        code = "import logging\nlogger=logging.getLogger(__name__)\n" \
               "def validate_inputs(x): pass\ndef process(x): pass\n" \
               "def format_output(x): pass\ndef execute(x): pass\n"
        assert run_lint_check(self._state([
            {"filename": "workflow.py", "content": code, "language": "python"}
        ]))["lint_passed"] is False


# ── Memory engine ─────────────────────────────────────────────────────────────

class TestMemoryEngine:
    def _engine(self):
        from memory.memory_engine import MemoryEngine
        f = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
        f.write("[]"); f.close()
        return MemoryEngine(store_path=f.name), f.name

    def test_store_and_retrieve(self):
        e, p = self._engine()
        e.store("TypeError", "int+str", "Cast to int")
        assert len(e.retrieve("TypeError")) == 1
        os.unlink(p)

    def test_frequency_increments(self):
        e, p = self._engine()
        e.store("KeyError", "missing x", "Use .get()")
        e.store("KeyError", "missing x", "Use .get()")
        assert e.retrieve("KeyError")[0].frequency == 2
        os.unlink(p)

    def test_human_fix_priority_boost(self):
        e, p = self._engine()
        e.store("ValueError", "bad", "Fix it")
        e.write_human_fix("ValueError", "bad", "Fix it")
        assert e.retrieve("ValueError")[0].frequency > 5
        os.unlink(p)

    def test_retrieve_sorted_by_frequency(self):
        e, p = self._engine()
        e.store("A", "a", "fix a")
        for _ in range(3): e.store("B", "b", "fix b")
        assert e.retrieve_all_for_context()[0].failure_type == "B"
        os.unlink(p)

    def test_format_for_prompt(self):
        e, p = self._engine()
        e.store("TypeError", "x", "Cast")
        out = e.format_for_prompt(e.retrieve("TypeError"))
        assert "TypeError" in out and "Cast" in out
        os.unlink(p)

    def test_empty_message(self):
        e, p = self._engine()
        assert "No relevant" in e.format_for_prompt(e.retrieve("Nope"))
        os.unlink(p)

    def test_persistence(self):
        e1, p = self._engine()
        e1.store("IOError", "nf", "Check path")
        from memory.memory_engine import MemoryEngine
        assert MemoryEngine(store_path=p).retrieve("IOError")[0].fix_pattern == "Check path"
        os.unlink(p)


# ── Weighted accuracy ─────────────────────────────────────────────────────────

class TestWeightedAccuracy:
    _tests = [
        {"test_id": f"T{i}", "type": t, "input": {}, "expected_output": {}}
        for i, t in enumerate(["normal","normal","normal","edge","edge","adversarial","adversarial"], 1)
    ]
    _W = {"normal": 0.5, "edge": 0.3, "adversarial": 0.2}

    def _c(self, passed):
        from agents.evaluation import _compute_weighted_accuracy
        return _compute_weighted_accuracy(self._tests, passed, self._W)

    def test_all_pass(self):
        w, *_ = self._c([f"T{i}" for i in range(1, 8)])
        assert abs(w - 1.0) < 0.001

    def test_none_pass(self):
        assert self._c([])[0] == 0.0

    def test_normal_only_below_threshold(self):
        w, *_ = self._c(["T1", "T2", "T3"])
        assert w < 0.75 and abs(w - 0.5) < 0.001

    def test_partial(self):
        w, *_ = self._c(["T1", "T2", "T4"])
        assert abs(w - ((2/3)*0.5 + (1/2)*0.3)) < 0.001


# ── Distribution enforcement ──────────────────────────────────────────────────

class TestDistributionEnforcement:
    """Audit fix #6 — _ensure_distribution must actually reclassify, not be a no-op."""

    def _t(self, types):
        return [{"test_id": f"T{i}", "type": t, "input": {}, "expected_output": {}}
                for i, t in enumerate(types, 1)]

    def test_all_normal_gets_reclassified(self):
        from agents.test_generation import _ensure_distribution
        result = _ensure_distribution(self._t(["normal"] * 10))
        assert len(result) == 10
        assert sum(1 for r in result if r["type"] == "edge") >= 1
        assert sum(1 for r in result if r["type"] == "adversarial") >= 1

    def test_no_tests_lost(self):
        from agents.test_generation import _ensure_distribution
        result = _ensure_distribution(self._t(["normal"] * 7 + ["adversarial"] * 3))
        assert len(result) == 10

    def test_empty_safe(self):
        from agents.test_generation import _ensure_distribution
        assert _ensure_distribution([]) == []

    def test_correct_dist_unchanged(self):
        from agents.test_generation import _ensure_distribution
        tests = self._t(["normal","normal","normal","edge","edge","adversarial","adversarial"])
        result = _ensure_distribution(tests)
        assert len(result) == 7


# ── Lint circuit breaker ──────────────────────────────────────────────────────

class TestLintCircuitBreaker:
    """Audit fix #3 — infinite critic↔lint loop must be broken after MAX_LINT_RETRIES."""

    def _s(self, lint_retries=0, lint_passed=False):
        from models.state import build_initial_state
        s = build_initial_state("test")
        s["lint_passed"] = lint_passed
        s["lint_retries"] = lint_retries
        return s

    def test_pass_routes_to_execution(self):
        from orchestrator.graph import route_after_lint
        assert route_after_lint(self._s(lint_passed=True)) == "execution_engine"

    def test_fail_below_max_routes_to_critic(self):
        from orchestrator.graph import route_after_lint
        assert route_after_lint(self._s(lint_retries=1)) == "critic_patch"

    def test_fail_at_max_routes_to_escalation(self):
        from orchestrator.graph import route_after_lint, MAX_LINT_RETRIES
        assert route_after_lint(self._s(lint_retries=MAX_LINT_RETRIES)) == "escalation"

    def test_increment_iteration_resets_lint_retries(self):
        from orchestrator.graph import increment_iteration
        from models.state import build_initial_state
        s = build_initial_state("test"); s["lint_retries"] = 2
        assert increment_iteration(s)["lint_retries"] == 0

    def test_increment_lint_retries_bumps(self):
        from orchestrator.graph import increment_lint_retries
        from models.state import build_initial_state
        s = build_initial_state("test"); s["lint_retries"] = 1
        assert increment_lint_retries(s)["lint_retries"] == 2


# ── Sandbox ───────────────────────────────────────────────────────────────────

class TestSandbox:
    _echo = [{"filename": "workflow.py", "language": "python", "content": '''
import logging, openai
logger = logging.getLogger(__name__)
def validate_inputs(i): logger.info("[w][v] ok")
def process(i): logger.info("[w][p] ok"); return {"echo": i.get("msg", "")}
def format_output(r): logger.info("[w][f] ok"); return r
def execute(i):
    logger.info("[w][e] ok"); validate_inputs(i); return format_output(process(i))
'''}]

    def test_successful(self):
        from execution.sandbox import PythonSandbox
        r = PythonSandbox(timeout=15).run(self._echo, {"msg": "hi"}, "workflow.execute")
        assert r.success and r.output["output"]["echo"] == "hi"

    def test_does_not_leak_real_api_key(self):
        """Audit fix #4 — sandbox must inject dummy key, not real one."""
        from execution.sandbox import PythonSandbox
        os.environ["OPENAI_API_KEY"] = "sk-REAL-KEY-MUST-NOT-LEAK"
        spy = [{"filename": "workflow.py", "language": "python", "content": '''
import os, logging, openai
logger = logging.getLogger(__name__)
def validate_inputs(i): pass
def process(i): return {"key": os.environ.get("OPENAI_API_KEY", "")}
def format_output(r): return r
def execute(i): logger.info("[w][e] ok"); validate_inputs(i); return format_output(process(i))
'''}]
        r = PythonSandbox(timeout=15).run(spy, {}, "workflow.execute")
        if r.success:
            key = r.output.get("output", {}).get("key", "")
            assert "REAL-KEY-MUST-NOT-LEAK" not in key

    def test_timeout(self):
        from execution.sandbox import PythonSandbox
        code = [{"filename": "workflow.py", "language": "python", "content": '''
import time, logging, openai
logger = logging.getLogger(__name__)
def validate_inputs(i): pass
def process(i): time.sleep(60)
def format_output(r): return r
def execute(i): logger.info("[w][e] ok"); validate_inputs(i); return format_output(process(i))
'''}]
        r = PythonSandbox(timeout=2).run(code, {}, "workflow.execute")
        assert r.timed_out and not r.success

    def test_runtime_error_captured(self):
        from execution.sandbox import PythonSandbox
        code = [{"filename": "workflow.py", "language": "python", "content": '''
import logging, openai
logger = logging.getLogger(__name__)
def validate_inputs(i): pass
def process(i): raise ValueError("deliberate")
def format_output(r): return r
def execute(i): logger.info("[w][e] ok"); validate_inputs(i); return format_output(process(i))
'''}]
        r = PythonSandbox(timeout=10).run(code, {}, "workflow.execute")
        assert not r.success and r.output.get("error_type") == "ValueError"


# ── Evaluation variable shadowing ─────────────────────────────────────────────

class TestEvaluationShadowing:
    """Audit fix #9 — 'e' shadowed in except clause must not crash."""

    def test_fallback_does_not_crash(self):
        from models.state import build_initial_state
        from unittest.mock import patch

        state = build_initial_state("test")
        state["spec"] = {"name": "t", "success_criteria": []}
        state["meta"]["iteration"] = 1
        state["artifacts"] = {
            "workflow_json": {}, "code_files": [], "previous_version": [],
            "tests": [{"test_id": "T1", "type": "normal", "input": {}, "expected_output": {}}],
        }
        state["execution"] = {
            "logs": [], "passed_tests": [], "failed_tests": ["T1"],
            "errors": [{"test_id": "T1", "error_type": "TypeError",
                        "error_message": "bad type", "file": "workflow.py",
                        "line": 5, "code_snippet": ""}],
        }

        with patch("agents.evaluation._client") as m:
            m.messages.create.side_effect = RuntimeError("LLM offline")
            from agents.evaluation import run_evaluation
            result = run_evaluation(state)  # must not raise TypeError

        assert "TypeError" in result["evaluation"]["failure_patterns"]


# ── Finalization reads all py files ──────────────────────────────────────────

class TestFinalizationMultiFile:
    """Audit fix #8 — finalization must include all .py files in context."""

    def test_all_py_files_in_context(self):
        from models.state import build_initial_state
        from unittest.mock import patch

        state = build_initial_state("multi_agent")
        state["spec"] = {"name": "multi_agent", "description": "t",
                         "inputs": [], "outputs": [], "constraints": [],
                         "edge_cases": [], "success_criteria": [], "documents": []}
        state["evaluation"] = {"accuracy": 0.8, "previous_accuracy": 0.7,
                               "status": "success", "failure_patterns": [],
                               "root_cause_summary": "", "normal_accuracy": 1.0,
                               "edge_accuracy": 0.8, "adversarial_accuracy": 0.5}
        state["patch"] = {"required": False, "target_files": [], "patches": [], "patch_summary": ""}
        state["execution"] = {"logs": [], "errors": [], "failed_tests": [], "passed_tests": []}
        state["artifacts"] = {
            "workflow_json": {}, "previous_version": [], "tests": [],
            "code_files": [
                {"filename": "workflow.py", "content": "def execute(i): pass  # MAIN_MARKER", "language": "python"},
                {"filename": "helpers.py", "content": "def helper(): pass  # HELPER_MARKER", "language": "python"},
            ],
        }

        captured = []
        with patch("agents.finalization._call_llm", side_effect=lambda s, u: (captured.append(u), "# doc")[1]):
            from agents.finalization import run_finalization
            run_finalization(state)

        combined = " ".join(captured)
        assert "MAIN_MARKER" in combined, "workflow.py missing from finalization context"
        assert "HELPER_MARKER" in combined, "helpers.py missing from finalization context"


# ── Graph routing ─────────────────────────────────────────────────────────────

class TestGraphRouting:
    def _s(self, accuracy, status, iteration=2, max_iter=5):
        from models.state import build_initial_state
        s = build_initial_state("test")
        s["evaluation"] = {"accuracy": accuracy, "previous_accuracy": 0.0,
                           "status": status, "failure_patterns": [], "root_cause_summary": "",
                           "normal_accuracy": 0.0, "edge_accuracy": 0.0, "adversarial_accuracy": 0.0}
        s["meta"]["iteration"] = iteration
        s["meta"]["max_iterations"] = max_iter
        return s

    def test_success_to_finalization(self):
        from orchestrator.graph import route_after_evaluation
        assert route_after_evaluation(self._s(0.8, "success")) == "finalization"

    def test_above_threshold_to_finalization(self):
        from orchestrator.graph import route_after_evaluation
        assert route_after_evaluation(self._s(0.76, "failed")) == "finalization"

    def test_max_iter_to_escalation(self):
        from orchestrator.graph import route_after_evaluation
        assert route_after_evaluation(self._s(0.5, "failed", iteration=5, max_iter=5)) == "escalation"

    def test_failure_to_critic(self):
        from orchestrator.graph import route_after_evaluation
        assert route_after_evaluation(self._s(0.55, "failed")) == "critic_patch"
