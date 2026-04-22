"""
Spec Normalizer Models - Defines the rigid schema for generated agents.
Ensures every agent has inputs, outputs, constraints, and error modes.
"""
from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field

class InputModel(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True

class OutputModel(BaseModel):
    name: str
    type: str
    description: str

class ToolModel(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

class ErrorMode(BaseModel):
    scenario: str
    handling_strategy: str

class NormalizedSpec(BaseModel):
    agent_name: str
    purpose: str
    inputs: list[InputModel]
    outputs: list[OutputModel]
    constraints: list[str] = Field(default_factory=list)
    tools: list[ToolModel] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    error_modes: list[ErrorMode] = Field(default_factory=list)
    execution_flow: list[str] = Field(default_factory=list)
    technical_requirements: dict[str, Any] = Field(default_factory=dict)
