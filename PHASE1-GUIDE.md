# Phase 1 — Runbook (do it yourself)

Goal: a green CI pipeline that builds, tests, and publishes a container image to
GitHub Container Registry (GHCR). Work top to bottom. Each step says **what you're
doing** and **why it matters** (the "why" is what interviewers actually probe).

> All commands run from the project root: `secure-gitops-platform/`

---

## Step 0 — Prerequisites

Check you have these:

```bash
python3 --version     # need 3.11+ (3.12 ideal)
docker --version      # any recent Docker
git --version
gh --version          # GitHub CLI (optional but easy); else use the web UI
```

If `gh` is missing and you want it: https://cli.github.com/ — or just use the
GitHub website for repo creation in Step 6.

---

## Step 1 — Create a virtualenv and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-dev.txt
```

**Why:** a virtualenv isolates this project's dependencies from your system
Python. `requirements-dev.txt` pulls in the app deps plus the tools (pytest,
ruff) you only need while developing — the production image never installs them.

Expected: a wall of "Successfully installed ..." ending without errors.

---

## Step 2 — Lint

```bash
ruff check .
```

Expected: `All checks passed!`

**Why:** linting catches dead imports, undefined names, and style drift before
they reach CI. Same command runs in the pipeline, so if it's clean here it's
clean there.

If ruff reports something, read the message — it usually tells you the fix. You
can auto-fix the safe ones with `ruff check --fix .`.

---

## Step 3 — Run the tests

```bash
pytest -q
```

Expected: `2 passed`.

**Why:** the tests prove the liveness endpoint works with **no database** and
that readiness **fails closed** (returns 503) when the DB is down. That
separation — liveness never depends on external services, readiness does — is a
real Kubernetes best practice and a great thing to be able to explain.

---

## Step 4 — Run the app locally (no database yet)

```bash
uvicorn app.main:app --reload
```

In another terminal:

```bash
curl localhost:8000/healthz      # {"status":"ok"}
curl -i localhost:8000/readyz    # 503 — no DB running yet, that's correct
```

Open http://localhost:8000/docs in a browser — FastAPI auto-generates an
interactive API page. Stop the server with Ctrl+C.

**Why:** confirms the app boots and that readiness correctly reports "not ready"
because there's no database. This is the behaviour Kubernetes relies on to avoid
routing traffic to a pod that can't serve.

---

## Step 5 — (Optional but recommended) Run a real database and hit /items

Spin up Postgres in a container so you can see the credential-using path work:

```bash
docker run -d --name pg \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=appdb \
  -p 5432:5432 postgres:16

# point the app at it and run again
export PGHOST=localhost PGUSER=postgres PGPASSWORD=postgres PGDATABASE=appdb
uvicorn app.main:app --reload
```

Then:

```bash
curl localhost:8000/readyz      # {"status":"ready"}  -- DB reachable now
curl localhost:8000/items       # {"items":[]}        -- table auto-created
```

Clean up when done:

```bash
docker rm -f pg
unset PGHOST PGUSER PGPASSWORD PGDATABASE
```

**Why:** this is the exact path Vault will secure in Phase 4. Right now the
credentials come from environment variables you set by hand; later Vault injects
short-lived ones automatically — and the app code doesn't change at all. Seeing
it work with static creds now makes the Vault swap obvious later.

---

## Step 6 — Build and run the container

```bash
docker build -t secure-gitops-platform .
docker run --rm -p 8000:8000 secure-gitops-platform
curl localhost:8000/healthz      # {"status":"ok"}
```

Confirm it isn't running as root:

```bash
docker run --rm secure-gitops-platform whoami    # should print: app
```

**Why:** the multi-stage build keeps pip and build tooling out of the final
image (smaller attack surface), and the container runs as an unprivileged user.
"Why non-root?" and "why multi-stage?" are common interview questions — you'll
have built the answer.

---

## Step 7 — Create the GitHub repo and push

Initialise git locally:

```bash
git init
git add .
git commit -m "Phase 1: app, tests, Dockerfile, CI pipeline"
git branch -M main
```

Create the remote repo and push:

**With gh CLI:**
```bash
gh repo create secure-gitops-platform --public --source=. --remote=origin --push
```

**Or via the website:** create an empty repo named `secure-gitops-platform`
(no README), then:
```bash
git remote add origin https://github.com/sy-cmd/secure-gitops-platform.git
git push -u origin main
```

**Why:** the push triggers the CI workflow. From here on, GitHub history is part
of your portfolio — steady, meaningful commits per phase tell the story of how
you build.

---

## Step 8 — Watch CI go green

- Open the repo on GitHub → **Actions** tab → you'll see the "CI" run.
- The `test` job runs ruff + pytest. The `build-and-push` job builds the image
  and pushes it to GHCR (only on `main`).

```bash
gh run watch          # if you have gh — live status in the terminal
```

Expected: both jobs succeed (green check).

**Why:** this is the milestone — `git push` now means tested code and a
published image with zero manual steps. That's CI in one sentence.

---

## Step 9 — Find your published image

- On the repo page, look at the right sidebar → **Packages** →
  `secure-gitops-platform`.
- New packages are **private** by default. To pull it without auth (and to show
  it off), open the package → **Package settings** → change visibility to
  **Public**, and link it to the repo if prompted.

Pull it to prove it works:

```bash
docker pull ghcr.io/sy-cmd/secure-gitops-platform:latest
```

---

## Done — Phase 1 complete ✅

You now have: a tested app, a hardened container, and a pipeline that publishes
it automatically. Update the status table in `README.md` (Phase 1 → ✅ done) and
commit that.

**What to be ready to explain (interview gold):**
- Why liveness and readiness are separate probes.
- Why the build is multi-stage and the container runs non-root.
- How `git push` becomes a published image (the CI flow).
- Why no secrets live in the image — and how Vault will fill that gap next.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `pip install` times out | Network issue; retry. Behind a proxy? set `HTTPS_PROXY`. |
| `ruff: command not found` | venv not activated, or deps not installed (Steps 1). |
| `pytest` import errors | Run from project root; `pyproject.toml` sets `pythonpath`. |
| `/readyz` returns 503 with DB up | Check `PG*` env vars match the container; is port 5432 free? |
| CI `build-and-push` fails on permissions | Repo → Settings → Actions → Workflow permissions → "Read and write". |
| Can't `docker pull` the image | Package is private — set visibility to Public (Step 9). |
| `docker build` fails on `psycopg` | Usually network; the `[binary]` wheel avoids needing compilers. |

When you hit something the table doesn't cover, paste me the exact error and
I'll help you debug that specific piece.
