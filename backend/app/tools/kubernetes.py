"""Read-only Kubernetes tools, parameterised by a kubeconfig path.

Safety: only read verbs; argv invocation (no shell); validated identifiers;
capped output. Cluster RBAC on the provided kubeconfig is the hard guardrail.
"""

from __future__ import annotations

import asyncio
import re

from app.core.logging import get_logger
from app.tools.base import Tool, ToolRegistry

logger = get_logger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.\-]{0,251}[a-z0-9])?$", re.IGNORECASE)
_KIND_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9.]{0,63}$")
_SELECTOR_RE = re.compile(r"^[a-zA-Z0-9._/=,\-]{1,253}$")
_MAX_OUTPUT = 6000


def _ok(value: str | None, pattern: re.Pattern) -> bool:
    return bool(value) and bool(pattern.match(value))


async def _run_kubectl(kubeconfig: str, *args: str, timeout: float = 25.0) -> str:
    cmd = ["kubectl", "--kubeconfig", kubeconfig, *args]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return "Error: kubectl command timed out."
    except FileNotFoundError:
        return "Error: kubectl is not available."
    if proc.returncode != 0:
        return f"kubectl error: {err.decode('utf-8', 'replace').strip()[:1500]}"
    text = out.decode("utf-8", "replace").strip()
    if not text:
        return "(no resources / empty output)"
    return text[:_MAX_OUTPUT] + ("\n… (truncated)" if len(text) > _MAX_OUTPUT else "")


async def test_connection(kubeconfig: str) -> tuple[bool, str]:
    out = await _run_kubectl(kubeconfig, "get", "namespaces", "-o", "name", timeout=12.0)
    if out.startswith("kubectl error") or out.startswith("Error"):
        return False, out[:300]
    n = len([l for l in out.splitlines() if l.strip()])
    return True, f"Connected — {n} namespaces visible."


_NS = {
    "type": "object",
    "properties": {"namespace": {"type": "string", "description": "Kubernetes namespace"}},
    "required": ["namespace"],
}


def build_registry(kubeconfig: str) -> ToolRegistry:
    """Build the K8s tool registry bound to a specific kubeconfig file path."""

    async def k(*args, timeout=25.0):
        return await _run_kubectl(kubeconfig, *args, timeout=timeout)

    async def list_namespaces(_: dict) -> str:
        return await k("get", "namespaces", "-o", "wide")

    async def list_pods(a: dict) -> str:
        ns = a.get("namespace", "")
        if not _ok(ns, _NAME_RE):
            return "Error: invalid/missing 'namespace'."
        cmd = ["get", "pods", "-n", ns, "-o", "wide"]
        sel = a.get("label_selector")
        if sel:
            if not _ok(sel, _SELECTOR_RE):
                return "Error: invalid 'label_selector'."
            cmd += ["-l", sel]
        return await k(*cmd)

    async def pod_logs(a: dict) -> str:
        ns, pod = a.get("namespace", ""), a.get("pod", "")
        if not _ok(ns, _NAME_RE) or not _ok(pod, _NAME_RE):
            return "Error: invalid/missing 'namespace'/'pod'."
        try:
            tail = max(1, min(int(a.get("tail_lines", 200)), 1000))
        except (TypeError, ValueError):
            tail = 200
        cmd = ["logs", "-n", ns, pod, f"--tail={tail}"]
        c = a.get("container")
        if c:
            if not _ok(c, _NAME_RE):
                return "Error: invalid 'container'."
            cmd += ["-c", c]
        return await k(*cmd, timeout=30.0)

    async def describe(a: dict) -> str:
        ns, kind, name = a.get("namespace", ""), a.get("kind", ""), a.get("name", "")
        if not _ok(ns, _NAME_RE) or not _ok(kind, _KIND_RE) or not _ok(name, _NAME_RE):
            return "Error: invalid/missing 'namespace'/'kind'/'name'."
        return await k("describe", kind, name, "-n", ns)

    async def get_events(a: dict) -> str:
        ns = a.get("namespace", "")
        if not _ok(ns, _NAME_RE):
            return "Error: invalid/missing 'namespace'."
        return await k("get", "events", "-n", ns, "--sort-by=.lastTimestamp")

    async def get_resource(a: dict) -> str:
        ns, kind = a.get("namespace", ""), a.get("kind", "")
        if not _ok(ns, _NAME_RE) or not _ok(kind, _KIND_RE):
            return "Error: invalid/missing 'namespace'/'kind'."
        cmd = ["get", kind, "-n", ns, "-o", "wide"]
        name = a.get("name")
        if name:
            if not _ok(name, _NAME_RE):
                return "Error: invalid 'name'."
            cmd.insert(2, name)
        return await k(*cmd)

    async def top_pods(a: dict) -> str:
        ns = a.get("namespace", "")
        if not _ok(ns, _NAME_RE):
            return "Error: invalid/missing 'namespace'."
        return await k("top", "pods", "-n", ns)

    reg = ToolRegistry()
    reg.register(Tool("k8s_list_namespaces", "List all Kubernetes namespaces.",
                      {"type": "object", "properties": {}}, list_namespaces))
    reg.register(Tool("k8s_list_pods",
                      "List pods in a namespace (status, restarts, node, IP); optional label_selector.",
                      {"type": "object", "properties": {
                          "namespace": {"type": "string"},
                          "label_selector": {"type": "string", "description": "e.g. app=web"}},
                       "required": ["namespace"]}, list_pods))
    reg.register(Tool("k8s_pod_logs", "Recent logs for a pod (optional container).",
                      {"type": "object", "properties": {
                          "namespace": {"type": "string"}, "pod": {"type": "string"},
                          "container": {"type": "string"}, "tail_lines": {"type": "integer"}},
                       "required": ["namespace", "pod"]}, pod_logs))
    reg.register(Tool("k8s_describe", "Describe a resource (kind e.g. pod/deployment/ingress).",
                      {"type": "object", "properties": {
                          "namespace": {"type": "string"}, "kind": {"type": "string"},
                          "name": {"type": "string"}},
                       "required": ["namespace", "kind", "name"]}, describe))
    reg.register(Tool("k8s_get_events", "Recent events in a namespace (diagnose failures).",
                      _NS, get_events))
    reg.register(Tool("k8s_get_resource",
                      "Read a resource kind in a namespace (optional name).",
                      {"type": "object", "properties": {
                          "namespace": {"type": "string"}, "kind": {"type": "string"},
                          "name": {"type": "string"}}, "required": ["namespace", "kind"]},
                      get_resource))
    reg.register(Tool("k8s_top_pods", "CPU/memory usage of pods (needs metrics-server).",
                      _NS, top_pods))
    return reg
