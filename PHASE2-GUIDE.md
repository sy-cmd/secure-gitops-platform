# Phase 2 — Runbook: Kubernetes + Helm (do it yourself)

**Goal:** package the app as a Helm chart and run it in a real cluster, with
production-shaped hygiene — split probes, resource limits, a hardened
`securityContext`, a dedicated ServiceAccount, and NetworkPolicies — talking to a
Postgres running in-cluster.

**Milestone:** `helm install` brings the app up; `kubectl port-forward` + `curl`
returns `ready` and `/items` works against Postgres.

> Already in your repo (I scaffolded these — review them, rewrite for practice if
> you like): `charts/app/Chart.yaml`, `charts/app/values.yaml`,
> `charts/app/templates/_helpers.tpl`.
>
> You will author the rest yourself below.

---

## Step 0 — Tools

```bash
kubectl version --client
helm version
# a cluster: use your existing k3s, OR kind (kind create cluster)
```

**Use k3s if you can.** Two reasons: it's closer to real clusters, and its CNI
**enforces NetworkPolicies**. `kind`'s default CNI (kindnet) will *accept*
NetworkPolicy objects but silently **not enforce** them — so you won't see them
actually block traffic unless you install Calico. (Good interview detail: "a
NetworkPolicy does nothing unless your CNI implements it.")

---

## Step 1 — Namespace

```bash
kubectl create namespace sgp
kubectl config set-context --current --namespace=sgp
```

---

## Step 2 — Make the image pullable

Easiest: in Phase 1 Step 9 you set the GHCR package to **Public** — then the
cluster can pull `ghcr.io/sy-cmd/secure-gitops-platform:latest` with no auth.

If you'd rather keep it private, either create an image pull secret:

```bash
kubectl create secret docker-registry ghcr \
  --docker-server=ghcr.io \
  --docker-username=sy-cmd \
  --docker-password=<a GitHub PAT with read:packages> \
  -n sgp
```
(and reference it via `imagePullSecrets` in the Deployment), **or** side-load it:

```bash
# kind:
kind load docker-image ghcr.io/sy-cmd/secure-gitops-platform:latest
# k3s:
docker save ghcr.io/sy-cmd/secure-gitops-platform:latest | sudo k3s ctr images import -
```

---

## Step 3 — The chart files you'll create

Target layout:

```
charts/app/
├── Chart.yaml                 # ✅ scaffolded
├── values.yaml                # ✅ scaffolded
└── templates/
    ├── _helpers.tpl           # ✅ scaffolded
    ├── serviceaccount.yaml    # you write
    ├── configmap.yaml         # you write
    ├── secret.yaml            # you write (Phase 2 only; Vault replaces later)
    ├── deployment.yaml        # you write  ← the meaty one
    ├── service.yaml           # you write
    ├── networkpolicy.yaml     # you write
    └── NOTES.txt              # you write
```

Below is reference YAML for each. Type it (don't just paste) — you'll remember
the fields, and that's exactly what gets probed in interviews.

### `serviceaccount.yaml`
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "app.fullname" . }}
  labels:
    {{- include "app.labels" . | nindent 4 }}
# This app calls no Kubernetes API, so it should not get a mounted token.
automountServiceAccountToken: false
```
**Why:** every pod gets a token by default; if the app doesn't talk to the API
server, mounting one is needless attack surface. Least privilege.

### `configmap.yaml` — non-secret DB connection settings
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "app.fullname" . }}-db
  labels:
    {{- include "app.labels" . | nindent 4 }}
data:
  PGHOST: {{ .Values.database.host | quote }}
  PGPORT: {{ .Values.database.port | quote }}
  PGDATABASE: {{ .Values.database.name | quote }}
  PGUSER: {{ .Values.database.user | quote }}
```

### `secret.yaml` — the DB password (TEMPORARY)
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "app.fullname" . }}-db
  labels:
    {{- include "app.labels" . | nindent 4 }}
type: Opaque
stringData:
  PGPASSWORD: {{ .Values.database.password | quote }}
```
**Why it's temporary:** this is a long-lived static password in a Secret — the
exact anti-pattern Phase 4 fixes. Vault will mint short-lived credentials per
pod and this file gets deleted. Leave a `# TODO(phase4): replace with Vault`.

### `deployment.yaml` — the important one
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "app.fullname" . }}
  labels:
    {{- include "app.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "app.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "app.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ include "app.fullname" . }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: app
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: {{ .Values.service.targetPort }}
          envFrom:
            - configMapRef:
                name: {{ include "app.fullname" . }}-db
            - secretRef:
                name: {{ include "app.fullname" . }}-db
          livenessProbe:
            httpGet:
              path: /healthz
              port: {{ .Values.service.targetPort }}
            initialDelaySeconds: 5
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /readyz
              port: {{ .Values.service.targetPort }}
            initialDelaySeconds: 5
            periodSeconds: 10
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
```
**Why each piece:**
- **liveness `/healthz` vs readiness `/readyz`** — restart a hung pod, but stop
  traffic to a pod whose DB isn't ready. Different failures, different actions.
- **resources** — requests let the scheduler place the pod; limits stop a runaway
  pod starving neighbours.
- **securityContext** — non-root, no privilege escalation, read-only root FS,
  all Linux capabilities dropped. The `emptyDir` at `/tmp` is the one writable
  path the read-only FS needs.
- **envFrom configMap + secret** — config and secrets injected as env vars,
  exactly where `app/db.py` reads them.

### `service.yaml`
```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "app.fullname" . }}
  labels:
    {{- include "app.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  selector:
    {{- include "app.selectorLabels" . | nindent 4 }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: {{ .Values.service.targetPort }}
```

### `networkpolicy.yaml`
```yaml
{{- if .Values.networkPolicy.enabled }}
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ include "app.fullname" . }}
  labels:
    {{- include "app.labels" . | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "app.selectorLabels" . | nindent 6 }}
  policyTypes: [Ingress, Egress]
  ingress:
    # allow traffic to the app port from within the namespace
    - from:
        - podSelector: {}
      ports:
        - port: {{ .Values.service.targetPort }}
  egress:
    # to Postgres
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - port: 5432
    # to cluster DNS
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
{{- end }}
```
**Why:** default Kubernetes networking is wide open. This says the app may only
talk to Postgres and DNS, and only accept traffic from its namespace —
least-privilege networking. (Remember: only enforced if your CNI supports it.)

### `NOTES.txt`
```
App deployed. Reach it with:

  kubectl port-forward svc/{{ include "app.fullname" . }} 8000:{{ .Values.service.port }} -n {{ .Release.Namespace }}
  curl localhost:8000/healthz
  curl localhost:8000/readyz
  curl localhost:8000/items
```

---

## Step 4 — Deploy Postgres (the dependency)

Create `manifests/postgres.yaml` (raw manifests on purpose — practice both Helm
and plain YAML):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres
type: Opaque
stringData:
  POSTGRES_PASSWORD: postgres
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: postgres
  labels: { app: postgres }
spec:
  replicas: 1
  selector:
    matchLabels: { app: postgres }
  template:
    metadata:
      labels: { app: postgres }
    spec:
      containers:
        - name: postgres
          image: postgres:16
          env:
            - name: POSTGRES_DB
              value: appdb
            - name: POSTGRES_PASSWORD
              valueFrom:
                secretKeyRef: { name: postgres, key: POSTGRES_PASSWORD }
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          ports:
            - containerPort: 5432
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
      volumes:
        - name: data
          emptyDir: {}     # dev only — ephemeral. Prod = StatefulSet + PVC.
---
apiVersion: v1
kind: Service
metadata:
  name: postgres
spec:
  selector: { app: postgres }
  ports:
    - port: 5432
      targetPort: 5432
```

```bash
kubectl apply -f manifests/postgres.yaml -n sgp
kubectl rollout status deploy/postgres -n sgp
```

**Why `emptyDir`:** keeps Phase 2 simple; data is lost if the pod dies. Real
databases use a **StatefulSet + PersistentVolumeClaim** for stable storage and
identity — say that out loud in an interview and you've shown you know the
difference.

---

## Step 5 — Lint, render, install

```bash
helm lint charts/app
helm template sgp charts/app -n sgp      # render to YAML without applying — read it!
helm install sgp charts/app -n sgp
```

`helm template` first is a good habit: you see exactly what will hit the cluster
before it does.

---

## Step 6 — Verify

```bash
kubectl get pods -n sgp                 # app x2 + postgres, all Running/Ready
kubectl describe pod -l app.kubernetes.io/name=app -n sgp   # check probes, no restarts

kubectl port-forward svc/sgp-app 8000:80 -n sgp
# in another terminal:
curl localhost:8000/healthz     # {"status":"ok"}
curl localhost:8000/readyz      # {"status":"ready"}  -> DB reachable in-cluster
curl localhost:8000/items       # {"items":[]}
```

Test that readiness actually gates traffic:

```bash
kubectl scale deploy/postgres --replicas=0 -n sgp
# wait ~15s, then:
curl -i localhost:8000/readyz   # 503 — pod is correctly marked NotReady
kubectl scale deploy/postgres --replicas=1 -n sgp   # recovers
```

---

## Step 7 — Commit the milestone

```bash
# update README status table: Phase 2 -> ✅
git add charts/ manifests/ README.md PHASE2-GUIDE.md
git commit -m "Phase 2: Helm chart, hardened Deployment, NetworkPolicies, Postgres"
git push
```

---

## What to be ready to explain (interview gold)

- Liveness vs readiness — *which failure triggers a restart vs a traffic cutoff?*
- Why the container is non-root with a read-only root filesystem (and why `/tmp`
  is the exception).
- What a NetworkPolicy does — and why it's a no-op without a supporting CNI.
- Why the password-in-a-Secret here is a placeholder, and what Vault changes.
- `emptyDir` vs a StatefulSet+PVC for the database.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Pod `ImagePullBackOff` | Image private — make GHCR package public, add pull secret, or side-load (Step 2). |
| Pod `CreateContainerConfigError` | ConfigMap/Secret name mismatch — names must match `envFrom`. |
| App `CrashLoopBackOff`, "permission denied" | Something tried to write to the read-only FS; ensure only `/tmp` is written. |
| Readiness never true | Postgres not up, or `PG*` values wrong; `kubectl logs` the app pod. |
| NetworkPolicy doesn't block anything | CNI doesn't enforce it (kindnet). Use k3s or install Calico. |
| `helm install` "namespace not found" | `kubectl create namespace sgp` first, or add `--create-namespace`. |

Paste me the exact error + `kubectl describe`/`kubectl logs` output for whatever
breaks and I'll help you debug that specific thing.
