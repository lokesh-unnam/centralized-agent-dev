from __future__ import annotations
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict
import uuid


# ── Pydantic models for structured data ──────────────────────────────────────

class AgentMeta(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_name: str = ""
    version: int = 1
    iteration: int = 0
    max_iterations: int = 5


class AgentSpec(BaseModel):
    name: str = ""
    description: str = ""
    inputs: list[Any] = Field(default_factory=list)
    outputs: list[Any] = Field(default_factory=list)
    constraints: list[Any] = Field(default_factory=list)
    edge_cases: list[Any] = Field(default_factory=list)
    success_criteria: list[Any] = Field(default_factory=list)
    documents: list[Any] = Field(default_factory=list)


class TaskStep(BaseModel):
    step_id: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    status: str = "pending"


class TaskPlan(BaseModel):
    steps: list[TaskStep] = Field(default_factory=list)


class InterpretedSpecModel(BaseModel):
    system_type: str = "agent"
    phases: list[dict[str, Any]] = Field(default_factory=list)
    tools_required: list[str] = Field(default_factory=list)
    framework: str = "custom"
    reasoning_style: str = "sequential"
    output_structure: Any = "json"
    constraints: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)


class CodeFile(BaseModel):
    filename: str
    content: str
    language: str = "python"


class TestCase(BaseModel):
    test_id: str
    input: dict[str, Any]
    expected_output: dict[str, Any]
    type: Literal["normal", "edge", "adversarial"]


class AgentArtifacts(BaseModel):
    workflow_json: dict[str, Any] = Field(default_factory=dict)
    code_files: list[CodeFile] = Field(default_factory=list)
    previous_version: list[CodeFile] = Field(default_factory=list)
    tests: list[TestCase] = Field(default_factory=list)


class TestError(BaseModel):
    test_id: str
    error_type: str
    error_message: str
    file: str = ""
    line: int = 0
    code_snippet: str = ""


class AgentExecution(BaseModel):
    logs: list[str] = Field(default_factory=list)
    errors: list[TestError] = Field(default_factory=list)
    failed_tests: list[str] = Field(default_factory=list)
    passed_tests: list[str] = Field(default_factory=list)


class AgentEvaluation(BaseModel):
    accuracy: float = 0.0
    previous_accuracy: float = 0.0
    normal_accuracy: float = 0.0
    edge_accuracy: float = 0.0
    adversarial_accuracy: float = 0.0
    status: Literal["pending", "success", "failed", "regressed"] = "pending"
    failure_patterns: list[str] = Field(default_factory=list)
    root_cause_summary: str = ""


class FilePatch(BaseModel):
    filename: str
    original: str
    patched: str
    diff: str


class AgentPatch(BaseModel):
    required: bool = False
    target_files: list[str] = Field(default_factory=list)
    patches: list[FilePatch] = Field(default_factory=list)
    patch_summary: str = ""


class MemoryPattern(BaseModel):
    pattern_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    failure_type: str
    error_message: str
    fix_pattern: str
    code_snippet: str
    frequency: int = 1


class AgentMemory(BaseModel):
    retrieved_patterns: list[MemoryPattern] = Field(default_factory=list)
    applied_patterns: list[str] = Field(default_factory=list)


class HumanEscalation(BaseModel):
    triggered: bool = False
    reason: str = ""
    stuck_failures: list[TestError] = Field(default_factory=list)
    human_patch: Optional[str] = None
    resolved: bool = False


# ── LangGraph TypedDict state (what flows through the graph) ─────────────────

class WorkflowState(TypedDict, total=False):
    meta: dict[str, Any]
    spec: dict[str, Any]
    artifacts: dict[str, Any]
    execution: dict[str, Any]
    evaluation: dict[str, Any]
    patch: dict[str, Any]
    memory: dict[str, Any]
    escalation: dict[str, Any]
    lint_passed: bool
    lint_retries: int          # circuit-breaker counter for critic↔lint loop
    user_input: Optional[str]  # set by API layer before graph entry
    interpreted_spec: dict[str, Any]
    plan: dict[str, Any]       # TaskPlan model dump
    error: Optional[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_initial_state(workflow_name: str, max_iterations: int = 5) -> WorkflowState:
    return WorkflowState(
        meta=AgentMeta(workflow_name=workflow_name, max_iterations=max_iterations).model_dump(),
        spec=AgentSpec().model_dump(),
        artifacts=AgentArtifacts().model_dump(),
        execution=AgentExecution().model_dump(),
        evaluation=AgentEvaluation().model_dump(),
        patch=AgentPatch().model_dump(),
        memory=AgentMemory().model_dump(),
        escalation=HumanEscalation().model_dump(),
        lint_passed=False,
        lint_retries=0,
        user_input=None,
        interpreted_spec=InterpretedSpecModel().model_dump(),
        plan=TaskPlan().model_dump(),
        error=None,
    )


def parse_state(state: WorkflowState) -> tuple[
    AgentMeta, AgentSpec, AgentArtifacts,
    AgentExecution, AgentEvaluation, AgentPatch, AgentMemory
]:
    return (
        AgentMeta(**state["meta"]),
        AgentSpec(**state["spec"]),
        AgentArtifacts(**state["artifacts"]),
        AgentExecution(**state["execution"]),
        AgentEvaluation(**state["evaluation"]),
        AgentPatch(**state["patch"]),
        AgentMemory(**state["memory"]),
    )
