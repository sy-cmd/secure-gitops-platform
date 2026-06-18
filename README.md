# secure-gitops-platform

> An end-to-end GitOps platform on Kubernetes where application secrets are never
> stored in Git or in a manifest. HashiCorp Vault issues **short-lived, dynamic
> database credentials** and **internal TLS certificates** at runtime, and every
> container image is **scanned and signed** before it can be deployed.

This is a portfolio project demonstrating a production-shaped DevOps platform:
CI/CD, GitOps, Kubernetes, Infrastructure as Code, observability, and a hardened
software supply chain — built around HashiCorp Vault.

## Status

| Phase | Scope | State |
|------|-------|-------|
| 1 | App + CI skeleton (build, test, image to GHCR) | ✅ in progress |
| 2 | Kubernetes + Helm | ⬜ |
| 3 | GitOps with ArgoCD | ⬜ |
| 4 | Vault — dynamic DB secrets + PKI ⭐ | ⬜ |
| 5 | Supply-chain security (Trivy, Checkov, cosign) | ⬜ |
| 6 | Observability (Prometheus + Grafana) | ⬜ |
| 7 | Terraform IaC + EKS (stretch) | ⬜ |

## The app

A deliberately minimal FastAPI service — the platform is the point, not the app.

| Endpoint | Purpose |
|----------|---------|
| `GET /healthz` | Liveness — no dependencies |
| `GET /readyz` | Readiness — verifies the database is reachable |
| `GET /items` | The credential-using path — reads from Postgres |

Database credentials are read from the environment **at call time**, never baked
into the image. In Phase 4 the Vault agent injector supplies short-lived
credentials with zero code changes.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# run tests (no database needed)
pytest -q

# run the API
uvicorn app.main:app --reload
curl localhost:8000/healthz
```

With Docker:

```bash
docker build -t secure-gitops-platform .
docker run -p 8000:8000 secure-gitops-platform
```

## Security notes (Phase 1)

- Multi-stage build — no build tooling in the final image.
- Runs as a non-root user.
- No secrets in the image or repo; credentials come from the environment.
- Liveness is dependency-free; readiness fails closed when the DB is unreachable.
# secure-gitops-platform
