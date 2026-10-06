from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime

class SourceInfo(BaseModel):
    filename: str
    page: Optional[int] = None

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None

class ChatResponse(BaseModel):
    session_id: int
    reply: str
    sources: List[SourceInfo] = []
    model_used: str = "general"

class SessionResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    action: str
    resource: Optional[str] = None
    details: Optional[Any] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DocumentInfoResponse(BaseModel):
    document_id: str
    filename: str
    file_type: str
    status: str
    workspace: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_restricted: bool = False  # True when document has any ACL rows

    class Config:
        from_attributes = True

class WorkspaceResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True

class KnowledgeBaseSummary(BaseModel):
    workspace_name: str
    document_count: int
    last_updated: Optional[datetime] = None

class AgentCreate(BaseModel):
    name: str
    description: str
    prompt_template: str

class AgentResponse(BaseModel):
    id: int
    name: str
    description: str
    prompt_template: str
    created_by: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True

class AgentRunRequest(BaseModel):
    variables: dict[str, str] = {}
