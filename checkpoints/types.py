"""
Checkpoint Types - Events and state for interactive checkpoints.
"""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class CheckpointType(str, Enum):
    """Types of checkpoints in the generation flow."""
    SPEC_GENERATED = "spec_generated"
    SPEC_APPROVED = "spec_approved"
    PLAN_GENERATED = "plan_generated"
    PLAN_APPROVED = "plan_approved"
    FILE_CREATED = "file_created"
    FILE_VALIDATED = "file_validated"
    TESTS_GENERATED = "tests_generated"
    TESTS_PASSED = "tests_passed"
    TESTS_FAILED = "tests_failed"
    FIX_APPLIED = "fix_applied"
    REVIEW_COMPLETE = "review_complete"
    READY_TO_DEPLOY = "ready_to_deploy"
    ERROR = "error"
    CANCELLED = "cancelled"


class CheckpointStatus(str, Enum):
    """Status of a checkpoint."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    AUTO_APPROVED = "auto_approved"
    TIMED_OUT = "timed_out"


class CheckpointAction(str, Enum):
    """Actions that can be taken at a checkpoint."""
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    SKIP = "skip"
    RETRY = "retry"
    ABORT = "abort"


class Checkpoint(BaseModel):
    """A checkpoint in the generation flow."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: CheckpointType
    title: str
    description: str
    data: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = True
    auto_continue_seconds: Optional[int] = None  # Auto-approve after N seconds
    status: CheckpointStatus = CheckpointStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    action_taken: Optional[CheckpointAction] = None
    user_feedback: Optional[str] = None
    modified_data: Optional[dict[str, Any]] = None
    
    def approve(self, feedback: Optional[str] = None) -> None:
        self.status = CheckpointStatus.APPROVED
        self.action_taken = CheckpointAction.APPROVE
        self.resolved_at = datetime.utcnow()
        self.user_feedback = feedback
    
    def reject(self, feedback: str) -> None:
        self.status = CheckpointStatus.REJECTED
        self.action_taken = CheckpointAction.REJECT
        self.resolved_at = datetime.utcnow()
        self.user_feedback = feedback
    
    def modify(self, modified_data: dict[str, Any], feedback: Optional[str] = None) -> None:
        self.status = CheckpointStatus.MODIFIED
        self.action_taken = CheckpointAction.MODIFY
        self.resolved_at = datetime.utcnow()
        self.modified_data = modified_data
        self.user_feedback = feedback
    
    @property
    def is_resolved(self) -> bool:
        return self.status not in (CheckpointStatus.PENDING,)
    
    @property
    def is_approved(self) -> bool:
        return self.status in (CheckpointStatus.APPROVED, CheckpointStatus.AUTO_APPROVED, CheckpointStatus.MODIFIED)


class CheckpointEvent(BaseModel):
    """Event emitted when checkpoint status changes."""
    checkpoint_id: str
    type: CheckpointType
    status: CheckpointStatus
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: dict[str, Any] = Field(default_factory=dict)


class GenerationProgress(BaseModel):
    """Overall progress of the generation."""
    workflow_id: str
    current_phase: str
    current_step: int
    total_steps: int
    files_generated: list[str] = Field(default_factory=list)
    checkpoints: list[Checkpoint] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "in_progress"
    error: Optional[str] = None
    
    @property
    def progress_percent(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100
    
    def add_checkpoint(self, checkpoint: Checkpoint) -> None:
        self.checkpoints.append(checkpoint)
    
    def get_pending_checkpoints(self) -> list[Checkpoint]:
        return [c for c in self.checkpoints if c.status == CheckpointStatus.PENDING]
