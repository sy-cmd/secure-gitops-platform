"""Secure GitOps Platform — demo REST API.

Deliberately small: the point of this project is the platform around the app
(Vault dynamic secrets, GitOps, supply-chain security), not the app itself.

Two health endpoints on purpose:
  - /healthz  (liveness)  -> no dependencies, just "is the process up?"
  - /readyz   (readiness) -> checks the DB, so K8s won't send traffic until
                             the Vault-injected DB credentials actually work.
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from . import db

app = FastAPI(title="secure-gitops-platform", version="0.1.0")


@app.get("/healthz")
def healthz():
    """Liveness probe — no external dependencies."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness probe — verifies the database is reachable."""
    if db.ping():
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "db-unavailable"})


@app.get("/items")
def list_items():
    """Return items from the database (the credential-using path)."""
    try:
        return {"items": db.list_items()}
    except Exception as exc:  # surfaced as 503 so probes/observability can see it
        raise HTTPException(status_code=503, detail=f"database error: {exc}") from exc
