"""Live local-mode Tau/CRM MCP check, also run by the Git pre-push hook.

Uses the normal CLI login and configured real provider. CRM calls are read-only;
local Tau state and sanitized evidence stay in ignored .local/agent-pre-push/.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from contextlib import ExitStack
from importlib.metadata import version
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def check_push():
    require(not git("status", "--porcelain"), "Commit pending changes before pushing.")
    head = git("rev-parse", "HEAD")
    for line in sys.stdin:
        _local_ref, oid, _remote_ref, _remote_oid = line.split()
        if set(oid) == {"0"}:
            continue
        require(git("rev-parse", f"{oid}^{{commit}}") == head,
                "Check out the revision being pushed so its actual local agent can be tested.")


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def start(module, listen_port, environment, log, stack):
    stream = stack.enter_context(log.open("ab"))
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1",
         "--port", str(listen_port)],
        cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
    )
    stack.callback(stop, process)
    return process


def wait_for_http(client, process, url):
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        require(process.poll() is None, f"Local process exited; inspect its log for {url}.")
        try:
            response = client.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
        except httpx.RequestError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Local process did not become ready: {url}")


def get_json(client, url, **kwargs):
    response = client.get(url, **kwargs)
    require(response.status_code == 200, f"GET {url} returned HTTP {response.status_code}.")
    return response.json()


def history_tools(history):
    return [part for message in history["messages"]
            for part in message.get("content", []) if part.get("type") == "tool-call"]


def business_result(part):
    require(not part.get("isError"), "Agent tool returned an error.")
    details = part.get("result", {}).get("details", {})
    require("code" not in details, f"Local CRM MCP bridge returned {details.get('code')}.")
    result = details.get("structuredContent")
    if result is None:
        texts = [p["text"] for p in details.get("content", []) if p.get("type") == "text"]
        require(len(texts) == 1, "CRM MCP did not return one structured result.")
        result = json.loads(texts[0])
    require(not details.get("isError") and result.get("code") == "ok",
            f"CRM MCP returned {result.get('code', 'no result code')}.")
    return result["data"]


def verify(contact_uid=None):
    if contact_uid:
        contact_uid = str(uuid.UUID(contact_uid))
    workflow = yaml.safe_load((ROOT / ".mainsequence/workflows/crm-api.yaml").read_text())
    spec = next(r["spec"] for r in workflow["resources"] if r["kind"] == "harness_agent")
    profile = {"provider": spec["llm_provider"], "model": spec["llm_model"],
               "thinking": spec["llm_thinking"]}
    run = ROOT / ".local/agent-pre-push" / str(uuid.uuid4())
    run.mkdir(parents=True, mode=0o700)
    report = {"status": "running", "commit": git("rev-parse", "HEAD"),
              "working_tree_dirty": bool(git("status", "--porcelain")),
              "tau_version": version("ms-tau-sdk"), **profile, "crm_calls": "read-only"}

    def save():
        (run / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    save()
    api_port, tau_port = port(), port()
    while tau_port == api_port:
        tau_port = port()
    api, tau = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{tau_port}"
    environment = {**os.environ, "MAINSEQUENCE_AUTH_MODE": "jwt", "TAU_LOCAL_MODE": "true",
                   "TAU_LOCAL_PROVIDER": profile["provider"], "TAU_LOCAL_MODEL": profile["model"],
                   "TAU_LOCAL_THINKING": profile["thinking"], "TAU_EXCLUDE_BASE_TOOLS": "true",
                   "TAU_EXCLUDE_MAINSEQUENCE_MCP": "true", "TAU_LOCAL_STATE_ROOT": str(run / "tau"),
                   "MAINSEQUENCE_CLI": str(ROOT / ".venv/bin/mainsequence"),
                   "CRM_LOCAL_API_ORIGIN": api, "CRM_LOCAL_TAU_ORIGIN": tau}
    session_uid = str(uuid.uuid4())
    report["session_uid"] = session_uid
    marker = f"Local agent read verification {uuid.uuid4()}"
    query = f"contacts/{contact_uid}/" if contact_uid else "contacts/"
    params = {} if contact_uid else {"search": marker}
    requested_tool = "crm_contacts_get" if contact_uid else "crm_contacts_list"
    arguments = {"uid": contact_uid} if contact_uid else {"search": marker}
    report.update(business_tool=requested_tool, arguments=arguments)
    instruction = (f"Read Contact UID {contact_uid}." if contact_uid else
                   f'Search contacts for the exact text "{marker}"; expect no matches.')
    prompt = ("Perform a read-only CRM verification. Discover the CRM MCP schemas with "
              f"crm__list_tools, then use crm__call_tool to run {requested_tool}. "
              f"{instruction} Use exactly these arguments: {json.dumps(arguments)}. "
              "Do not create, edit, archive, or call any other business tool. "
              "Never retry an uncertain tool call. Report the actual returned result briefly.")
    try:
        with ExitStack() as stack, httpx.Client(trust_env=False, timeout=90) as client:
            crm = start("api.crm.local:app", api_port, environment, run / "crm.log", stack)
            agent = start("api.tau.main:app", tau_port, environment, run / "agent.log", stack)
            wait_for_http(client, crm, api + "/healthz")
            health = wait_for_http(client, agent, tau + "/health")
            require(health.get("mode") == "local", "Tau must report mode=local.")
            require(health.get("exclude_base_tools") and health.get("exclude_mainsequence_mcp"),
                    "The live agent must use the CRM tool exclusions.")
            require(health.get("base_tool_count") == health.get("mcp_tool_count") == 0,
                    "Broad coding/platform tools must be absent.")
            ready = get_json(client, tau + "/ready")
            require(all(ready.get(k) is True for k in
                        ("mainsequence_auth_ready", "provider_control_ready", "local_store_ready")),
                    "Local authentication, real provider, and storage must be ready.")
            require(get_json(client, tau + "/version")["version"] == report["tau_version"],
                    "The local process must run the installed Tau release.")
            report["local_runtime_ready"] = True
            save()
            print(f"Local Tau {report['tau_version']} ready with {profile['provider']}/{profile['model']}.",
                  flush=True)
            # Match the local frontend startup gate; process health alone is insufficient.
            bootstrap = client.get(api + "/api/crm/v1/bootstrap/", timeout=100)
            document = bootstrap.json()
            report["crm_bootstrap"] = {
                "http_status": bootstrap.status_code,
                "readiness": document.get("readiness", {}),
                "error": document.get("error"),
            }
            save()
            require(bootstrap.status_code == 200 and
                    document.get("readiness", {}).get("status") == "ready",
                    f"Protected CRM bootstrap failed (HTTP {bootstrap.status_code}); inspect report.json.")
            # One send only. Recover this same persisted local turn if its stream disconnects.
            deadline = time.monotonic() + 420
            try:
                with client.stream("POST", tau + "/api/chat",
                                   json={"sessionUid": session_uid, "message": prompt},
                                   timeout=httpx.Timeout(90, read=5)) as response:
                    require(response.status_code == 200, f"Local chat returned HTTP {response.status_code}.")
                    session_uid = response.headers["X-Agent-Session-Uid"]
                    report["session_uid"] = session_uid
                    save()
                    for _line in response.iter_lines():
                        # Never print or save reasoning from the stream.
                        if time.monotonic() >= deadline:
                            break
            except httpx.RequestError as error:
                report["stream_error_type"] = type(error).__name__
                save()
            history_url = tau + f"/api/local/v1/chat-sessions/{session_uid}/history"
            while True:
                history = get_json(client, history_url)
                if history["session"]["status"] != "running":
                    break
                require(time.monotonic() < deadline, "The existing local turn did not settle.")
                time.sleep(2)
            require(history["session"]["status"] == "completed", "The real local agent turn failed.")
            calls = history_tools(history)
            discovery = [p for p in calls if p["toolName"] == "crm__list_tools"]
            require(bool(discovery),
                    "The agent must actually discover CRM MCP tools.")
            require(any(not p.get("isError") and
                        any(t.get("name") == requested_tool for t in
                            p.get("result", {}).get("details", {}).get("tools", []))
                        for p in discovery), "CRM MCP discovery did not return the requested tool.")
            require(all(p["toolName"] in {"crm__list_tools", "crm__call_tool"} for p in calls),
                    "The agent used a tool outside the requested CRM read workflow.")
            business = [p for p in calls if p["toolName"] == "crm__call_tool"]
            require(len(business) == 1 and business[0]["args"]["tool"] == requested_tool,
                    "Require exactly one requested CRM MCP read; no retries or writes.")
            require(business[0]["args"]["arguments"] == arguments,
                    "The agent must use the exact scoped read arguments.")
            details = business[0].get("result", {}).get("details", {})
            report["bridge_code"] = details.get("code")
            save()
            result = business_result(business[0])
            if contact_uid:
                require(result["uid"] == contact_uid, "MCP read returned a different contact.")
            else:
                require(result["items"] == [] and result["pageInfo"]["totalItems"] == 0,
                        "The unique read-only search must have no matches.")
            report["mcp_read_verified"] = True
            report["read_evidence"] = (
                {k: result.get(k) for k in ("uid", "version", "created_by_uid", "updated_by_uid")}
                if contact_uid else {"total_items": result["pageInfo"]["totalItems"]}
            )
            save()
            # Restart both processes: confirm local conversation durability and fresh API binding.
            stop(agent)
            stop(crm)
            crm = start("api.crm.local:app", api_port, environment, run / "crm.log", stack)
            agent = start("api.tau.main:app", tau_port, environment, run / "agent.log", stack)
            wait_for_http(client, crm, api + "/healthz")
            wait_for_http(client, agent, tau + "/health")
            recovered = get_json(client, history_url)
            require(recovered["session"]["status"] == "completed" and
                    history_tools(recovered) == calls, "Local history did not survive restart.")
            independent = get_json(client, api + "/api/crm/v1/" + query, params=params)
            require(independent == result, "Fresh API read differs from the actual MCP result.")
            report.update(status="passed", restart_history_verified=True,
                          fresh_api_read_verified=True, tool_calls=len(calls))
            save()
            print(f"PASS: real local agent, CRM MCP read, restart persistence, fresh API read.\n"
                  f"Evidence: {run / 'report.json'}", flush=True)
    except Exception as error:
        report.update(status="failed", error_type=type(error).__name__, error=str(error))
        save()
        print(f"FAIL: {error}\nEvidence and local logs: {run}", file=sys.stderr, flush=True)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pre-push", action="store_true")
    parser.add_argument("--contact-uid", help="Read this exact controlled contact instead of an empty search.")
    args = parser.parse_args()
    if args.pre_push:
        check_push()
    return verify(args.contact_uid)


if __name__ == "__main__":
    raise SystemExit(main())
