"""Static checks of the deployment files: Kubernetes manifests, compose file and Dockerfile.

These run without Docker or a cluster; CI additionally builds the image and deploys to kind.
"""

from typing import Any

import pytest
import yaml

from factory_energy.paths import ROOT

K8S = ROOT / "k8s"


def manifests() -> list[dict[str, Any]]:
    docs = []
    for path in sorted(K8S.glob("*.yaml")):
        if path.name == "kustomization.yaml":
            continue
        docs += [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
    return docs


def pods() -> list[tuple[str, dict[str, Any]]]:
    out = []
    for doc in manifests():
        if doc["kind"] in ("Deployment", "Job"):
            out.append((doc["metadata"]["name"], doc["spec"]["template"]["spec"]))
    return out


def test_kustomization_lists_every_manifest() -> None:
    listed = yaml.safe_load((K8S / "kustomization.yaml").read_text(encoding="utf-8"))["resources"]
    present = {p.name for p in K8S.glob("*.yaml")} - {"kustomization.yaml"}
    assert set(listed) == present


@pytest.mark.parametrize("name", ["agent", "chroma", "plant-data"])
def test_every_pod_meets_the_restricted_profile(name: str) -> None:
    spec = dict(pods())[name]
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert spec["automountServiceAccountToken"] is False
    # Service links would inject CHROMA_PORT=tcp://... and crash Chroma (seen in the kind run).
    assert spec["enableServiceLinks"] is False
    for container in spec["containers"]:
        security = container["securityContext"]
        assert security["allowPrivilegeEscalation"] is False
        assert security["capabilities"]["drop"] == ["ALL"]
        assert "limits" in container["resources"] and "requests" in container["resources"]


def test_our_image_runs_read_only_and_the_agent_has_probes() -> None:
    spec = dict(pods())
    for name in ("agent", "plant-data"):
        assert spec[name]["containers"][0]["securityContext"]["readOnlyRootFilesystem"] is True
    agent = spec["agent"]["containers"][0]
    assert agent["readinessProbe"]["httpGet"]["path"] == "/ready"
    assert agent["livenessProbe"]["httpGet"]["path"] == "/health"
    data_mount = next(m for m in agent["volumeMounts"] if m["mountPath"] == "/app/data")
    assert data_mount["readOnly"] is True


def test_secret_template_holds_no_values_and_namespace_is_restricted() -> None:
    docs = manifests()
    secret = next(d for d in docs if d["kind"] == "Secret")
    assert all(value == "" for value in secret["stringData"].values())
    namespace = next(d for d in docs if d["kind"] == "Namespace")
    assert namespace["metadata"]["labels"]["pod-security.kubernetes.io/enforce"] == "restricted"
    policies = {d["metadata"]["name"] for d in docs if d["kind"] == "NetworkPolicy"}
    assert policies == {"agent", "chroma"}


def test_compose_and_dockerfile_are_sandboxed() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    app = compose["services"]["app"]
    assert app["read_only"] is True and app["cap_drop"] == ["ALL"]
    assert app["ports"] == ["127.0.0.1:8000:8000"]  # not exposed beyond this machine
    assert set(compose["services"]["vllm"]["profiles"]) == {"gpu"}
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001" in dockerfile and "HEALTHCHECK" in dockerfile
    assert "latest" not in dockerfile  # pinned base image
