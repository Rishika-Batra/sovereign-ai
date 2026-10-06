import os
import time
import asyncio
import socket
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import User
from app.api.deps import get_db, require_permission, get_current_user
from app.ai_gateway.registry import MODEL_REGISTRY

router = APIRouter()

_START_TIME = time.time()

# Known external AI endpoints to probe
BLOCKED_ENDPOINTS = [
    ("api.openai.com", "OpenAI"),
    ("api.anthropic.com", "Anthropic"),
    ("generativelanguage.googleapis.com", "Google Gemini"),
    ("huggingface.co", "Hugging Face"),
]


# ---------------------------------------------------------------------------
# GET /api/settings/models
# ---------------------------------------------------------------------------

@router.get("/models")
def get_models(
    current_user: User = Depends(require_permission("settings.manage")),
) -> List[Dict[str, Any]]:
    """Return the current model registry — read-only view."""
    return [
        {
            "key": key,
            "name": info["name"],
            "type": info["type"],
            "backend": info["backend"],
        }
        for key, info in MODEL_REGISTRY.items()
    ]


# ---------------------------------------------------------------------------
# GET /api/settings/system
# ---------------------------------------------------------------------------

@router.get("/system")
async def get_system_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("settings.manage")),
) -> Dict[str, Any]:
    """Return live system status indicators."""

    # --- Ollama liveness check ---
    ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
    ollama_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{ollama_url}/api/tags")
            if r.status_code == 200:
                ollama_status = "reachable"
    except Exception:
        pass

    # --- Database liveness check ---
    db_status = "unreachable"
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        db_status = "reachable"
    except Exception:
        pass

    uptime_seconds = int(time.time() - _START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return {
        "ollama_status": ollama_status,
        "database_status": db_status,
        "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uptime": f"{hours}h {minutes}m {seconds}s",
        "architecture": "air-gapped",
    }


# ---------------------------------------------------------------------------
# GET /api/settings/network-status   (admin-only)
# ---------------------------------------------------------------------------

async def _probe_host(host: str, timeout: float = 2.0) -> str:
    """
    Attempt a TCP connection to the given host on port 443.
    Returns "blocked" if the connection is refused, the address is null-routed,
    or the connection times out. Returns "reachable" if a TCP handshake succeeds.
    Returns "error" for unexpected exceptions.
    """
    loop = asyncio.get_event_loop()
    try:
        # Resolve first — if extra_hosts mapped it to 0.0.0.0 this will resolve
        # but the connection itself will fail immediately.
        sock = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: socket.create_connection((host, 443), timeout=timeout),
            ),
            timeout=timeout,
        )
        sock.close()
        return "reachable"
    except (OSError, asyncio.TimeoutError):
        # Connection refused / network unreachable / 0.0.0.0 null-route / timeout
        return "blocked"
    except Exception as e:
        logger.error(f"Unexpected error probing {host}: {e}")
        return "error"


@router.get("/network-status")
async def get_network_status(
    current_user: User = Depends(require_permission("settings.manage")),
) -> Dict[str, Any]:
    """
    Admin-only: probe each known external AI endpoint and report whether it
    is reachable or blocked at the network level.
    This is independent of application code — it tests the actual OS routing
    and /etc/hosts (extra_hosts) rules baked into the container.
    """
    results = {}
    for host, label in BLOCKED_ENDPOINTS:
        results[label] = {
            "host": host,
            "status": await _probe_host(host),
        }

    results["Direct internet (1.1.1.1:443)"] = {
        "host": "1.1.1.1",
        "status": await _probe_host("1.1.1.1"),
    }

    all_blocked = all(v["status"] == "blocked" for v in results.values())

    return {
        "isolation_verified": all_blocked,
        "endpoints": results,
        "note": (
            "Isolation is enforced by an internal-only Docker network "
            "(backend has no route out; Ollama is reached via ollama-proxy), "
            "with DNS blocks as a second layer. "
            "For production Linux hosts, supplement with iptables DOCKER-USER chain rules."
        ),
    }
