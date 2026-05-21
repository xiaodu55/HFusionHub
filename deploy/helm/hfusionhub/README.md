# hfusionhub Helm Chart

Deploys HFusionHub (Java backend + Python AI + Vue frontend + MySQL + Redis +
Milvus/etcd/Attu + optional isolated plugin runner) to Kubernetes.

## Template layout

`templates/` is split per component (Helm renders every `*.yaml` in this
directory; the split is organizational only):

| File                | Resources                                  | Gate (`values.yaml`)   |
| ------------------- | ------------------------------------------ | ---------------------- |
| `secret.yaml`       | Shared secrets (DB/API tokens, admin pwd)  | always                 |
| `mysql.yaml`        | MySQL Service + Deployment + PVC           | `mysql.enabled`        |
| `redis.yaml`        | Redis Service + Deployment                 | `redis.enabled`        |
| `java.yaml`         | Java backend Service + Deployment          | `javaBackend.enabled`  |
| `python.yaml`       | Python AI Service + Deployment             | `pythonAi.enabled`     |
| `plugin-runner.yaml`| Isolated plugin runner Service + Deploy + PVC | `pluginRunner.enabled`|
| `uploads-pvc.yaml`  | Shared Java/Python uploads RWX PVC         | always                 |
| `etcd.yaml`         | etcd StatefulSet (Milvus dependency)       | `etcd.enabled`         |
| `milvus.yaml`       | Milvus standalone StatefulSet              | `milvus.enabled`       |
| `attu.yaml`         | Attu (Milvus web console)                  | `attu.enabled`         |
| `hpa.yaml`          | Python AI HorizontalPodAutoscaler          | `pythonAi.minReplicas > 0` |
| `frontend.yaml`     | Vue frontend Service + Deployment          | `frontend.enabled`     |
| `ingress.yaml`      | Ingress (`/api` → java, `/` → frontend)    | `ingress.enabled`      |

## Enable/disable components

```bash
# Minimal: only Java + Python + infra (no plugin runner, no Attu)
helm install hfusionhub . \
  --set pluginRunner.enabled=false \
  --set attu.enabled=false

# Everything on
helm install hfusionhub . --set pluginRunner.enabled=true
```

Secrets are `required` when the corresponding component is enabled — see
`values.yaml` and the `required` calls in `secret.yaml` /
`plugin-runner.yaml`.

## Validate

```bash
helm lint .
helm template . --values values.yaml > /tmp/rendered.yaml
```
