from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.auth import router as auth_router

app = FastAPI(title="Sovereign AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/auth", tags=["auth"])

@app.on_event("startup")
def on_startup():
    from app.db.init_db import init_db
    init_db()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

from app.api.chat import router as chat_router
app.include_router(chat_router, prefix="/api/chat", tags=["chat"])

from app.api.documents import router as documents_router
app.include_router(documents_router, prefix="/api/documents", tags=["documents"])

from app.api.agent import router as agent_router
app.include_router(agent_router, prefix="/api/agent", tags=["agent"])

from app.api.audit import router as audit_router
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])

from app.api.users import router as users_router
app.include_router(users_router, prefix="/api/users", tags=["users"])

from app.api.agents import router as agents_router
app.include_router(agents_router, prefix="/api/agents", tags=["agents"])

from app.api.deliverables import router as deliverables_router
app.include_router(deliverables_router, prefix="/api/deliverables", tags=["deliverables"])

from app.api.settings import router as settings_router
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])

from app.api.approvals import router as approvals_router
app.include_router(approvals_router, prefix="/api/approvals", tags=["approvals"])
