# Kubernetes Platform with Monitoring

A hands-on Kubernetes project: a Python **Task API** running on a 3-node Minikube cluster with production-style settings, including zero-downtime rolling updates, health probes, high availability and autoscaling. A PostgreSQL StatefulSet and a Prometheus/Grafana monitoring stack are in progress.

## What's implemented

| Area | Details | File |
|---|---|---|
| Namespaces | Separate `task-app` and `monitoring` namespaces | `k8s/00-namespace.yaml` |
| Configuration | ConfigMap as env vars and as a mounted file; DB password in a Secret | `k8s/01-configmap.yaml` |
| Resource governance | LimitRange defaults and ResourceQuota for the namespace | `k8s/02-resource-limits.yaml` |
| Deployment | 3 replicas, rolling updates (`maxSurge: 1`, `maxUnavailable: 0`), rollback history | `k8s/03-deployment.yaml` |
| Health checks | Startup, liveness and readiness probes; preStop hook for graceful shutdown | `k8s/03-deployment.yaml` |
| High availability | Topology spread across nodes; PodDisruptionBudget (`minAvailable: 2`) | `k8s/03-deployment.yaml`, `k8s/06-pdb.yaml` |
| Networking | ClusterIP Service (internal) and NodePort Service (external, port 30080) | `k8s/04-service.yaml`, `k8s/05-service-nodeport.yaml` |
| Autoscaling | HPA on CPU (3 to 8 pods) with tuned scale-up/scale-down behavior | `k8s/07-hpa.yaml` |
| Container | Slim Python image, non-root user, Prometheus `/metrics` endpoint | `app/Dockerfile` |

## Repository structure
```
.
├── app/            # Flask Task API + Dockerfile
└── k8s/            # Kubernetes manifests, numbered in apply order
```

## The app
| Endpoint | Purpose |
|---|---|
| `GET /` | App version and the pod that served the request |
| `GET/POST /tasks` | List and create tasks |
| `GET /healthz` | Liveness check |
| `GET /readyz` | Readiness check (also checks the database when one is configured) |
| `GET /work?ms=N` | Burns CPU for N ms (used for autoscaling tests) |
| `GET /metrics` | Prometheus metrics (request count, latency) |

## Run it yourself

Prerequisites: Docker, kubectl, Minikube

```bash
# 1. Start a 3-node cluster
minikube start --driver=docker --nodes=3 --cpus=2 --memory=2500 --cni=calico
minikube addons enable metrics-server

# 2. Create the namespace and the Secret (the Secret is not stored in git)
kubectl apply -f k8s/00-namespace.yaml
kubectl create secret generic task-api-secret --from-literal=DB_PASSWORD='<your-password>' -n task-app

# 3. Deploy everything
kubectl apply -f k8s/

# 4. Test
curl http://$(minikube ip):30080/
```

To build your own image:
```bash
docker build --build-arg APP_VERSION=v2 -t <your-dockerhub-user>/task-api:v2 app/
docker push <your-dockerhub-user>/task-api:v2
```

## Roadmap
- [x] Deployments, Services, ConfigMaps, Secrets
- [x] Rolling updates and rollback
- [x] Probes, resource limits, graceful shutdown
- [x] High availability (topology spread, PDB)
- [x] Horizontal Pod Autoscaler
- [ ] PostgreSQL StatefulSet with persistent storage
- [ ] Ingress and NetworkPolicies
- [ ] RBAC and pod security
- [ ] Jobs, CronJobs, DaemonSets
- [ ] Helm chart
- [ ] Prometheus, Grafana and Alertmanager
- [ ] CI with GitHub Actions
