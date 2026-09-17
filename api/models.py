"""
Schémas Pydantic pour l'API.
"""

from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Message de l'utilisateur")
    history: list[dict] = Field(default_factory=list, description="Historique de conversation [{role, content}]")


class ConfirmationResponse(BaseModel):
    confirmation_id: str
    accepted: bool


class MemoryIngestRequest(BaseModel):
    path: str = Field(..., min_length=1, description="Chemin absolu du fichier à ingérer (.txt/.md/.pdf)")


class ToolCallResult(BaseModel):
    tool: str
    args: dict
    status: str
    result: Optional[dict] = None
    message: Optional[str] = None
    confirmation_id: Optional[str] = None
    reason: Optional[str] = None
    level: Optional[str] = None
    suggestion: Optional[str] = None
    target: Optional[str] = None


class ChatResponse(BaseModel):
    type: str  # "text" | "tool_execution"
    message: Optional[str] = None
    tool_results: list[dict] = Field(default_factory=list)


class ContextResponse(BaseModel):
    timestamp: float
    foreground_window: dict
    running_processes: list[dict]
    audio_active_processes: list[str]
    cpu_usage: float
    ram_usage: float
    ram_available_gb: float
    gpu_usage: float
    disk_usage: dict
    network_active_processes: list[str]
