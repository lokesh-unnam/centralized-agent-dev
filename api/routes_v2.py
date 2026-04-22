"""
API Routes v2 - REST and WebSocket endpoints for ReAct-based generation.
"""
from __future__ import annotations
import asyncio
import json
from typing import Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
import structlog

from agents.react_orchestrator import ReactOrchestrator, GenerationConfig, GenerationResult
from checkpoints import CheckpointManager, Checkpoint, CheckpointType, CheckpointStatus
from tools.registry import get_tool_registry

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/v2", tags=["v2"])


# ── Request/Response Models ───────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    user_input: str = Field(..., min_length=10, description="Natural language description")
    output_path: Optional[str] = Field(None, description="Output directory")
    interactive: bool = Field(True, description="Enable interactive checkpoints")
    sandbox: bool = Field(True, description="Use sandbox for testing")


class GenerateResponse(BaseModel):
    success: bool
    workflow_id: str
    output_path: str
    files: list[dict[str, Any]]
    error: Optional[str] = None
    checkpoints: int = 0


class CheckpointResponse(BaseModel):
    id: str
    type: str
    title: str
    description: str
    status: str
    data: dict[str, Any]
    requires_approval: bool


class ApproveRequest(BaseModel):
    checkpoint_id: str
    action: str = Field(..., description="approve, reject, or modify")
    feedback: Optional[str] = None
    modified_data: Optional[dict[str, Any]] = None


class ToolListResponse(BaseModel):
    tools: list[dict[str, Any]]
    categories: dict[str, list[str]]


# ── Active Sessions ───────────────────────────────────────────────────────────


_active_sessions: dict[str, ReactOrchestrator] = {}
_session_results: dict[str, GenerationResult] = {}


# ── REST Endpoints ────────────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateResponse)
async def generate_agent(request: GenerateRequest) -> GenerateResponse:
    """
    Generate an agent from natural language description.
    In non-interactive mode, auto-approves all checkpoints.
    """
    logger.info("api.v2.generate", input_length=len(request.user_input))
    
    config = GenerationConfig(
        output_path=request.output_path,
        interactive=False,  # REST endpoint is non-interactive
        sandbox=request.sandbox,
    )
    
    orchestrator = ReactOrchestrator(config)
    result = await orchestrator.generate(request.user_input)
    
    _session_results[result.workflow_id] = result
    
    return GenerateResponse(
        success=result.success,
        workflow_id=result.workflow_id,
        output_path=result.output_path,
        files=result.files,
        error=result.error,
        checkpoints=len(result.checkpoints),
    )


@router.get("/sessions/{workflow_id}")
async def get_session(workflow_id: str) -> dict[str, Any]:
    """Get details of a generation session."""
    if workflow_id in _session_results:
        result = _session_results[workflow_id]
        return {
            "workflow_id": workflow_id,
            "success": result.success,
            "files": len(result.files),
            "error": result.error,
        }
    
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{workflow_id}/files")
async def get_session_files(workflow_id: str) -> list[dict[str, Any]]:
    """Get files from a generation session."""
    if workflow_id in _session_results:
        return _session_results[workflow_id].files
    
    raise HTTPException(status_code=404, detail="Session not found")


@router.get("/tools", response_model=ToolListResponse)
async def list_tools() -> ToolListResponse:
    """List all available tools."""
    registry = get_tool_registry()
    
    tools = []
    for name in registry.list_tools():
        tool = registry.get(name)
        if tool:
            tools.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": [p.model_dump() for p in tool.parameters],
                "requires_approval": tool.requires_approval,
                "sandbox_safe": tool.sandbox_safe,
            })
    
    return ToolListResponse(
        tools=tools,
        categories=registry.get_tools_by_category(),
    )


# ── WebSocket for Interactive Generation ──────────────────────────────────────


@router.websocket("/ws/generate")
async def ws_generate(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for interactive generation with real-time checkpoints.
    
    Client sends:
        {"type": "start", "user_input": "...", "output_path": "..."}
        {"type": "approve", "checkpoint_id": "...", "action": "approve|reject"}
    
    Server sends:
        {"type": "progress", "phase": "...", "step": N, "total": M}
        {"type": "checkpoint", "checkpoint": {...}}
        {"type": "file_created", "filename": "..."}
        {"type": "complete", "result": {...}}
        {"type": "error", "error": "..."}
    """
    await websocket.accept()
    logger.info("api.v2.ws_connected")
    
    orchestrator: Optional[ReactOrchestrator] = None
    generation_task: Optional[asyncio.Task] = None
    
    try:
        while True:
            raw = await websocket.receive_text()
            message = json.loads(raw)
            msg_type = message.get("type")
            
            if msg_type == "start":
                # Start generation
                user_input = message.get("user_input", "")
                if not user_input:
                    await websocket.send_json({"type": "error", "error": "No user_input provided"})
                    continue
                
                config = GenerationConfig(
                    output_path=message.get("output_path"),
                    interactive=True,
                    sandbox=True,
                )
                
                orchestrator = ReactOrchestrator(config)
                _active_sessions[orchestrator.workflow_id] = orchestrator
                
                # Set up callbacks
                async def on_checkpoint(checkpoint: Checkpoint):
                    await websocket.send_json({
                        "type": "checkpoint",
                        "checkpoint": {
                            "id": checkpoint.id,
                            "type": checkpoint.type.value,
                            "title": checkpoint.title,
                            "description": checkpoint.description,
                            "data": checkpoint.data,
                            "requires_approval": checkpoint.requires_approval,
                        }
                    })
                
                def on_progress(progress):
                    asyncio.create_task(websocket.send_json({
                        "type": "progress",
                        "phase": progress.current_phase,
                        "step": progress.current_step,
                        "total": progress.total_steps,
                        "files": progress.files_generated,
                    }))
                
                orchestrator.checkpoint_manager.on_checkpoint = lambda cp: asyncio.create_task(on_checkpoint(cp))
                orchestrator.checkpoint_manager.on_progress = on_progress
                
                # Start generation in background
                async def run_gen():
                    result = await orchestrator.generate(user_input)
                    _session_results[result.workflow_id] = result
                    await websocket.send_json({
                        "type": "complete",
                        "result": result.to_dict(),
                    })
                
                generation_task = asyncio.create_task(run_gen())
                
                await websocket.send_json({
                    "type": "started",
                    "workflow_id": orchestrator.workflow_id,
                })
            
            elif msg_type == "approve":
                # Handle checkpoint approval
                if not orchestrator:
                    await websocket.send_json({"type": "error", "error": "No active generation"})
                    continue
                
                checkpoint_id = message.get("checkpoint_id")
                action = message.get("action", "approve")
                feedback = message.get("feedback")
                
                if action == "approve":
                    orchestrator.checkpoint_manager.approve(checkpoint_id, feedback)
                elif action == "reject":
                    orchestrator.checkpoint_manager.reject(checkpoint_id, feedback or "Rejected")
                elif action == "modify":
                    modified_data = message.get("modified_data", {})
                    orchestrator.checkpoint_manager.modify(checkpoint_id, modified_data, feedback)
                
                await websocket.send_json({
                    "type": "checkpoint_resolved",
                    "checkpoint_id": checkpoint_id,
                    "action": action,
                })
            
            elif msg_type == "cancel":
                # Cancel generation
                if generation_task:
                    generation_task.cancel()
                await websocket.send_json({"type": "cancelled"})
                break
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        logger.info("api.v2.ws_disconnected")
    except Exception as e:
        logger.error("api.v2.ws_error", error=str(e))
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except:
            pass
    finally:
        if orchestrator and orchestrator.workflow_id in _active_sessions:
            del _active_sessions[orchestrator.workflow_id]
        if generation_task and not generation_task.done():
            generation_task.cancel()


# ── Health Check ──────────────────────────────────────────────────────────────


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check for v2 API."""
    from tools.registry import get_tool_registry
    
    registry = get_tool_registry()
    
    return {
        "status": "ok",
        "version": "v2",
        "engine": "react",
        "tools_available": len(registry.list_tools()),
        "active_sessions": len(_active_sessions),
    }
