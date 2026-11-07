# Kubernetes

Manifests for the energy agent: the agent Deployment and Service, a Chroma vector store, a
one-shot Job that builds the synthetic database and indexes the knowledge base, an HPA,
NetworkPolicies, a ConfigMap, a Secret template with empty values, and an `ExternalName`
Service for the vLLM server on the GPU host. All data is synthetic (fictional plant).

Security posture: the namespace enforces the `restricted` Pod Security Standard; every pod runs
as a non-root user with `RuntimeDefault` seccomp, no Linux capabilities, no privilege escalation
and (for our image) a read-only root filesystem; the agent mounts the plant database read-only
and has no service-account token; NetworkPolicies limit the agent to DNS, Chroma and the model
server.

## Run it locally with kind

Requires Docker, [kind](https://kind.sigs.k8s.io/) and kubectl.

```bash
docker build -t factory-energy-agent:local .
kind create cluster --name factory-energy
kind load docker-image factory-energy-agent:local --name factory-energy
kubectl apply -k k8s/
kubectl -n factory-energy wait --for=condition=complete job/plant-data --timeout=600s
kubectl -n factory-energy rollout status deployment/agent --timeout=300s
kubectl -n factory-energy port-forward service/agent 8000:8000
```

Then, in another terminal:

```bash
curl -s localhost:8000/ready
curl -s -X POST localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "How long does a reflow oven preheat?"}'
curl -s localhost:8000/metrics | grep agent_runs_total
```

Clean up with `kind delete cluster --name factory-energy`.

## Using the vLLM server

Set `externalName` in `vllm-external.yaml` to the GPU host's DNS name, then set
`LLM_PROVIDER: openai_compatible` and `LLM_MODEL` (the served model name) in `configmap.yaml`.
An API key for the server, if any, goes into the `agent-secrets` Secret as `LLM_API_KEY`.

## Notes

- kind's default CNI does not enforce NetworkPolicies; use Calico or Cilium to enforce them.
- Every pod sets `enableServiceLinks: false`. Otherwise Kubernetes injects `CHROMA_PORT=tcp://...`
  for the `chroma` Service, which Chroma reads as its own port setting and refuses to start.
- `plant-data` is ReadWriteOnce, which suits a single-node cluster. On several nodes use
  ReadWriteMany storage or bake the database into a data image.
- Chroma keeps its index in an `emptyDir`: the index is derived from the documents and the
  `plant-data` Job rebuilds it, and an `emptyDir` lets Chroma run as a non-root user on storage
  that ignores `fsGroup` (such as kind's local-path volumes). If the Chroma pod restarts, rerun
  the Job (`kubectl -n factory-energy delete job plant-data && kubectl apply -k k8s/`).
- The HPA needs metrics-server, which kind does not install; without it the HPA only warns.
- The same manifests are applied to a kind cluster in CI on every push (`.github/workflows/ci.yml`).
