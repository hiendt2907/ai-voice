#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { echo "[deploy] $*"; }

# Build images (context = repo root for api/portal; services/voice for voice)
log "Building api image..."
docker build -f apps/api/Dockerfile -t ai-voice/api:latest .

log "Building portal image..."
docker build -f apps/portal/Dockerfile -t ai-voice/portal:latest .

log "Building voice image..."
docker build -f services/voice/Dockerfile -t ai-voice/voice:latest services/voice/

# Apply K8s manifests
log "Applying K8s manifests..."
kubectl apply -k deploy/k8s/

# Restart deployments to pick up new images
log "Rolling restart..."
kubectl rollout restart deployment/api deployment/portal deployment/voice -n ai-voice

log "Waiting for rollout..."
kubectl rollout status deployment/api -n ai-voice --timeout=120s
kubectl rollout status deployment/portal -n ai-voice --timeout=120s
kubectl rollout status deployment/voice -n ai-voice --timeout=120s

log "Done. Portal: http://doctorcheck.ai-agent.local"
kubectl get pods -n ai-voice
