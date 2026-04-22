"""
Checkpoint Manager - Orchestrates checkpoints and user interactions.
"""
from __future__ import annotations
import asyncio
from typing import Any, Callable, Optional
from datetime import datetime
import structlog

from checkpoints.types import (
    Checkpoint, CheckpointType, CheckpointStatus, CheckpointAction,
    CheckpointEvent, GenerationProgress
)

logger = structlog.get_logger(__name__)


class CheckpointManager:
    """Manages checkpoints during agent generation."""
    
    def __init__(
        self,
        interactive: bool = True,
        auto_approve_delay: int = 0,  # 0 = wait forever
        on_checkpoint: Optional[Callable[[Checkpoint], None]] = None,
        on_progress: Optional[Callable[[GenerationProgress], None]] = None,
    ):
        self.interactive = interactive
        self.auto_approve_delay = auto_approve_delay
        self.on_checkpoint = on_checkpoint
        self.on_progress = on_progress
        
        self._checkpoints: list[Checkpoint] = []
        self._pending_approval: Optional[Checkpoint] = None
        self._approval_event: Optional[asyncio.Event] = None
        self._progress: Optional[GenerationProgress] = None
    
    def initialize(self, workflow_id: str, total_steps: int = 10) -> GenerationProgress:
        """Initialize progress tracking for a new generation."""
        self._progress = GenerationProgress(
            workflow_id=workflow_id,
            current_phase="initialization",
            current_step=0,
            total_steps=total_steps,
        )
        return self._progress
    
    def update_progress(self, phase: str, step: int, files: Optional[list[str]] = None) -> None:
        """Update the current progress."""
        if self._progress:
            self._progress.current_phase = phase
            self._progress.current_step = step
            if files:
                self._progress.files_generated.extend(files)
            
            if self.on_progress:
                self.on_progress(self._progress)
    
    async def checkpoint(
        self,
        checkpoint_type: CheckpointType,
        title: str,
        description: str,
        data: dict[str, Any],
        requires_approval: bool = True,
    ) -> Checkpoint:
        """Create a checkpoint and wait for approval if interactive."""
        
        checkpoint = Checkpoint(
            type=checkpoint_type,
            title=title,
            description=description,
            data=data,
            requires_approval=requires_approval and self.interactive,
            auto_continue_seconds=self.auto_approve_delay if self.auto_approve_delay > 0 else None,
        )
        
        self._checkpoints.append(checkpoint)
        if self._progress:
            self._progress.add_checkpoint(checkpoint)
        
        logger.info(
            "checkpoint.created",
            type=checkpoint_type.value,
            title=title,
            requires_approval=checkpoint.requires_approval,
        )
        
        # Notify listeners
        if self.on_checkpoint:
            self.on_checkpoint(checkpoint)
        
        # If interactive and requires approval, wait
        if checkpoint.requires_approval:
            await self._wait_for_approval(checkpoint)
        else:
            checkpoint.status = CheckpointStatus.AUTO_APPROVED
            checkpoint.resolved_at = datetime.utcnow()
        
        return checkpoint
    
    async def _wait_for_approval(self, checkpoint: Checkpoint) -> None:
        """Wait for user to approve/reject the checkpoint."""
        self._pending_approval = checkpoint
        self._approval_event = asyncio.Event()
        
        logger.info("checkpoint.waiting_for_approval", checkpoint_id=checkpoint.id)
        
        if checkpoint.auto_continue_seconds:
            try:
                await asyncio.wait_for(
                    self._approval_event.wait(),
                    timeout=checkpoint.auto_continue_seconds
                )
            except asyncio.TimeoutError:
                checkpoint.status = CheckpointStatus.AUTO_APPROVED
                checkpoint.resolved_at = datetime.utcnow()
                logger.info("checkpoint.auto_approved", checkpoint_id=checkpoint.id)
        else:
            await self._approval_event.wait()
        
        self._pending_approval = None
        self._approval_event = None
    
    def approve(self, checkpoint_id: str, feedback: Optional[str] = None) -> bool:
        """Approve a pending checkpoint."""
        checkpoint = self._find_checkpoint(checkpoint_id)
        if not checkpoint or checkpoint.status != CheckpointStatus.PENDING:
            return False
        
        checkpoint.approve(feedback)
        logger.info("checkpoint.approved", checkpoint_id=checkpoint_id)
        
        if self._approval_event and self._pending_approval and self._pending_approval.id == checkpoint_id:
            self._approval_event.set()
        
        return True
    
    def reject(self, checkpoint_id: str, feedback: str) -> bool:
        """Reject a pending checkpoint."""
        checkpoint = self._find_checkpoint(checkpoint_id)
        if not checkpoint or checkpoint.status != CheckpointStatus.PENDING:
            return False
        
        checkpoint.reject(feedback)
        logger.info("checkpoint.rejected", checkpoint_id=checkpoint_id, feedback=feedback)
        
        if self._approval_event and self._pending_approval and self._pending_approval.id == checkpoint_id:
            self._approval_event.set()
        
        return True
    
    def modify(
        self, 
        checkpoint_id: str, 
        modified_data: dict[str, Any],
        feedback: Optional[str] = None
    ) -> bool:
        """Modify data at a checkpoint and continue."""
        checkpoint = self._find_checkpoint(checkpoint_id)
        if not checkpoint or checkpoint.status != CheckpointStatus.PENDING:
            return False
        
        checkpoint.modify(modified_data, feedback)
        logger.info("checkpoint.modified", checkpoint_id=checkpoint_id)
        
        if self._approval_event and self._pending_approval and self._pending_approval.id == checkpoint_id:
            self._approval_event.set()
        
        return True
    
    def _find_checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        """Find a checkpoint by ID."""
        for cp in self._checkpoints:
            if cp.id == checkpoint_id:
                return cp
        return None
    
    def get_pending(self) -> Optional[Checkpoint]:
        """Get the currently pending checkpoint."""
        return self._pending_approval
    
    def get_all_checkpoints(self) -> list[Checkpoint]:
        """Get all checkpoints."""
        return self._checkpoints.copy()
    
    def get_progress(self) -> Optional[GenerationProgress]:
        """Get current progress."""
        return self._progress
    
    # Sync versions for non-async contexts
    def checkpoint_sync(
        self,
        checkpoint_type: CheckpointType,
        title: str,
        description: str,
        data: dict[str, Any],
        requires_approval: bool = True,
    ) -> Checkpoint:
        """Synchronous version - auto-approves immediately in non-interactive mode."""
        checkpoint = Checkpoint(
            type=checkpoint_type,
            title=title,
            description=description,
            data=data,
            requires_approval=False,  # Sync mode can't wait
        )
        
        checkpoint.status = CheckpointStatus.AUTO_APPROVED
        checkpoint.resolved_at = datetime.utcnow()
        
        self._checkpoints.append(checkpoint)
        if self._progress:
            self._progress.add_checkpoint(checkpoint)
        
        if self.on_checkpoint:
            self.on_checkpoint(checkpoint)
        
        return checkpoint


class CLICheckpointHandler:
    """Handle checkpoints via CLI prompts."""
    
    def __init__(self, manager: CheckpointManager):
        self.manager = manager
    
    def display_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Display checkpoint info in CLI."""
        print("\n" + "=" * 60)
        print(f"CHECKPOINT: {checkpoint.title}")
        print("=" * 60)
        print(f"Type: {checkpoint.type.value}")
        print(f"Description: {checkpoint.description}")
        print("-" * 60)
        
        # Display data summary
        if checkpoint.data:
            print("Data:")
            for key, value in checkpoint.data.items():
                if isinstance(value, str) and len(value) > 200:
                    print(f"  {key}: {value[:200]}...")
                elif isinstance(value, list):
                    print(f"  {key}: [{len(value)} items]")
                elif isinstance(value, dict):
                    print(f"  {key}: {{...}}")
                else:
                    print(f"  {key}: {value}")
        print("-" * 60)
    
    def prompt_for_action(self, checkpoint: Checkpoint) -> CheckpointAction:
        """Prompt user for action on checkpoint."""
        self.display_checkpoint(checkpoint)
        
        print("\nActions:")
        print("  [a] Approve and continue")
        print("  [r] Reject and abort")
        print("  [m] Modify (provide feedback)")
        print("  [s] Skip this checkpoint")
        
        while True:
            choice = input("\nYour choice (a/r/m/s): ").strip().lower()
            
            if choice == 'a':
                feedback = input("Feedback (optional, press Enter to skip): ").strip()
                self.manager.approve(checkpoint.id, feedback or None)
                return CheckpointAction.APPROVE
            
            elif choice == 'r':
                feedback = input("Reason for rejection: ").strip()
                self.manager.reject(checkpoint.id, feedback)
                return CheckpointAction.REJECT
            
            elif choice == 'm':
                feedback = input("Modification feedback: ").strip()
                # In a real implementation, this would open an editor
                self.manager.modify(checkpoint.id, {}, feedback)
                return CheckpointAction.MODIFY
            
            elif choice == 's':
                self.manager.approve(checkpoint.id, "Skipped by user")
                return CheckpointAction.SKIP
            
            else:
                print("Invalid choice. Please enter a, r, m, or s.")
