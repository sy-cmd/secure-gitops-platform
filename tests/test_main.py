"""Unit tests that run without a database.

Liveness must never depend on external services, so /healthz is testable in CI
with no Postgres. The DB-backed paths are covered by integration tests later
(Phase 2+), once the app runs in-cluster.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_ok():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_reports_db_down(monkeypatch):
    # With no database reachable in CI, readiness should fail closed (503).
    monkeypatch.setattr("app.db.ping", lambda: False)
    resp = client.get("/readyz")
    assert resp.status_code == 503
