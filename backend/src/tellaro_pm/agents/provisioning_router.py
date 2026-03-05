"""API routes for agent provisioning tokens and binary downloads."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from tellaro_pm.agents.provisioning import (
    exchange_provisioning_token,
    generate_provisioning_token,
    list_provisioning_tokens,
    revoke_provisioning_token,
)
from tellaro_pm.agents.provisioning_schemas import (
    AgentBinaryInfo,
    ProvisioningTokenCreate,
    ProvisioningTokenCreated,
    ProvisioningTokenExchange,
    ProvisioningTokenExchangeResponse,
    ProvisioningTokenResponse,
)
from tellaro_pm.agents.service import agent_service
from tellaro_pm.core.auth import create_access_token
from tellaro_pm.core.dependencies import get_current_user
from tellaro_pm.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents/provisioning", tags=["agent-provisioning"])

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]

# Directory where agent binaries are stored
BINARIES_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "agent" / "releases"


# ------------------------------------------------------------------
# Provisioning token management
# ------------------------------------------------------------------


@router.post("/tokens", response_model=ProvisioningTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(body: ProvisioningTokenCreate, user: CurrentUser) -> dict[str, object]:
    """Generate a new provisioning token for agent registration."""
    user_id = str(user["id"])
    doc, raw_token = generate_provisioning_token(
        user_id=user_id,
        label=body.label,
        expires_hours=body.expires_hours,
    )
    return {
        "id": doc["id"],
        "token": raw_token,
        "label": doc["label"],
        "expires_hours": doc["expires_hours"],
        "created_at": doc["created_at"],
    }


@router.get("/tokens", response_model=list[ProvisioningTokenResponse])
async def list_tokens(user: CurrentUser) -> list[dict[str, object]]:
    """List all provisioning tokens for the current user."""
    return list_provisioning_tokens(str(user["id"]))


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: str, user: CurrentUser) -> None:
    """Revoke a provisioning token."""
    if not revoke_provisioning_token(token_id, str(user["id"])):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")


# ------------------------------------------------------------------
# Token exchange (no auth required — the token IS the auth)
# ------------------------------------------------------------------


@router.post("/exchange", response_model=ProvisioningTokenExchangeResponse)
async def exchange_token(body: ProvisioningTokenExchange) -> dict[str, object]:
    """Exchange a provisioning token for an agent JWT and register the agent."""
    token_doc = exchange_provisioning_token(body.token)
    if token_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or already used provisioning token",
        )

    user_id = str(token_doc["user_id"])

    # Register the agent
    agent = agent_service.register(
        user_id,
        {
            "name": body.name,
            "machine_info": body.machine_info,
            "capabilities": body.capabilities,
        },
    )

    agent_id = str(agent["id"])

    # Create an agent JWT (longer-lived than user tokens)
    access_token = create_access_token(
        subject=user_id,
        extra={
            "agent_id": agent_id,
            "type": "agent",
        },
    )

    return {
        "access_token": access_token,
        "agent_id": agent_id,
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# ------------------------------------------------------------------
# Agent binary downloads
# ------------------------------------------------------------------

_PLATFORM_MAP = {
    "windows-x86_64": "tellaro-pm-agent-x86_64-pc-windows-msvc.exe",
    "windows-aarch64": "tellaro-pm-agent-aarch64-pc-windows-msvc.exe",
    "linux-x86_64": "tellaro-pm-agent-x86_64-unknown-linux-musl",
    "linux-aarch64": "tellaro-pm-agent-aarch64-unknown-linux-musl",
    "macos-x86_64": "tellaro-pm-agent-x86_64-apple-darwin",
    "macos-aarch64": "tellaro-pm-agent-aarch64-apple-darwin",
}


@router.get("/binaries", response_model=list[AgentBinaryInfo])
async def list_binaries(_user: CurrentUser) -> list[dict[str, object]]:
    """List available agent binary downloads."""
    result: list[dict[str, object]] = []

    if not BINARIES_DIR.is_dir():
        return result

    for version_dir in sorted(BINARIES_DIR.iterdir(), reverse=True):
        if not version_dir.is_dir():
            continue
        version = version_dir.name
        for platform_key, filename in _PLATFORM_MAP.items():
            parts = platform_key.split("-")
            platform, arch = parts[0], parts[1]
            filepath = version_dir / filename
            if filepath.is_file():
                info: dict[str, object] = {
                    "platform": platform,
                    "arch": arch,
                    "version": version,
                    "filename": filename,
                    "size_bytes": filepath.stat().st_size,
                }
                # Include SHA256 if a checksum file exists
                sha_file = filepath.with_suffix(filepath.suffix + ".sha256")
                if sha_file.is_file():
                    info["sha256"] = sha_file.read_text().strip().split()[0]
                result.append(info)

    return result


def _resolve_binary(version: str, filename: str) -> Path:
    """Resolve a binary file path, supporting 'latest' as version alias."""
    if filename not in _PLATFORM_MAP.values():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown binary")

    if version == "latest":
        # Find the newest version directory that contains this binary
        if not BINARIES_DIR.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No binaries available")
        for version_dir in sorted(BINARIES_DIR.iterdir(), reverse=True):
            if version_dir.is_dir() and (version_dir / filename).is_file():
                return version_dir / filename
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binary not found")

    filepath = BINARIES_DIR / version / filename
    if not filepath.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binary not found")
    return filepath


@router.get("/binaries/{version}/{filename}")
async def download_binary(version: str, filename: str, _user: CurrentUser) -> FileResponse:
    """Download an agent binary by version (or 'latest') and filename."""
    filepath = _resolve_binary(version, filename)

    return FileResponse(
        path=filepath,
        filename=filename,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
