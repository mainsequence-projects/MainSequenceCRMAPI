"""Live local-mode Tau/CRM MCP check, also run by the Git pre-push hook.

Uses the normal CLI login and configured real provider. By default, migrations
and read-only CRM settings checks use an owned, private local MetaTables runtime.
Local state and sanitized evidence stay in ignored .local/agent-pre-push/.
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
    return start_command(
        [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1",
         "--port", str(listen_port)], environment, log, stack,
    )


def start_command(command, environment, log, stack):
    stream = stack.enter_context(log.open("ab"))
    process = subprocess.Popen(
        command,
        cwd=ROOT, env=environment, stdout=stream, stderr=subprocess.STDOUT,
    )
    stack.callback(stop, process)
    return process


def isolated_catalog(environment, run, stack):
    """Use the installed local launcher and real SDK identity, never a shared DB."""
    from metatables.local_connection import read_development_client

    storage = run / "metatables"
    storage.mkdir(mode=0o700)
    configuration = storage / "configuration.yaml"
    configuration.write_text(yaml.safe_dump({
        "local_mode_available": True,
        "local_credentials": {"provider": "file", "key_directory": str(storage / "keys")},
    }))
    selected = {**environment, "METATABLES_LOCAL_STORAGE_DIR": str(storage)}
    # A stale URL/token from another shell must not select a different runtime.
    selected.pop("METATABLES_API_URL", None)
    selected.pop("METATABLES_LOCAL_TOKEN", None)
    process = start_command(
        [str(ROOT / ".venv/bin/metatables"), "serve", "--local", "--port", str(port()),
         "--configuration", str(configuration), "--no-open-browser"],
        selected, run / "metatables.log", stack,
    )
    deadline = time.monotonic() + 100
    connection = None
    while time.monotonic() < deadline:
        require(process.poll() is None, "Private MetaTables launcher exited; inspect metatables.log.")
        try:
            connection = read_development_client(storage / "server.json")
            with httpx.Client(trust_env=False, timeout=2) as client:
                if client.get(connection["api_url"] + "/openapi.json", headers={
                    "X-MetaTables-Local-Token": connection["token"],
                }).status_code == 200:
                    break
        except (RuntimeError, httpx.RequestError):
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError("Private MetaTables API did not become ready; inspect metatables.log.")
    require(connection is not None, "Private MetaTables connection is unavailable.")
    selected.update(METATABLES_API_URL=connection["api_url"],
                    METATABLES_LOCAL_TOKEN=connection["token"])
    # Execute the public migration client in a fresh process. No SDK identity,
    # provider, MCP, storage or catalog port is replaced by a fixture.
    setup = """
import json, sys
from pathlib import Path
from metatables import configure_local_client, get_runtime_status, initialize_runtime, upgrade_application
configure_local_client()
before = get_runtime_status()
expected = Path(sys.argv[1]).resolve()
assert before['local_mode'] is True
assert Path(before['bootstrap']['candidate']['configuration']['path']).resolve() == expected
initialize_runtime()
state = get_runtime_status()
assert state['local_mode'] is True and state['dialect'] == 'sqlite'
assert state['data_source']['class_type'] == 'sqlite'
assert state['bootstrap']['active'] is True and not state.get('data_source_error')
result = upgrade_application('src.crm.migrations:migration')
assert result['data_source_uid'] == state['data_source']['uid']
from src.crm.platform.catalog import CatalogRegistry
registry = CatalogRegistry()
registry.validate()
registry.validate_settings()
Path(sys.argv[2]).write_text(json.dumps({
    'local_mode': True, 'dialect': 'sqlite', 'database_path': str(expected),
    'data_source_uid': state['data_source']['uid'], 'revision': result['revision'],
    'bindings': len(registry.bindings), 'identity': 'real-sdk-session',
}))
"""
    with (run / "metatables-setup.log").open("ab") as log:
        result = subprocess.run(
            [sys.executable, "-c", setup, str(storage / "metatables.sqlite"),
             str(run / "catalog.json")], cwd=ROOT, env=selected,
            stdout=log, stderr=subprocess.STDOUT, timeout=300,
        )
    require(result.returncode == 0, "Private local migration failed; inspect metatables-setup.log.")
    metadata = json.loads((run / "catalog.json").read_text())
    print(f"Private local MetaTables ready at CRM revision {metadata['revision']} "
          f"with {metadata['bindings']} bindings.", flush=True)
    return selected, metadata


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


def solution_selling_reads(fixture_path):
    """Explicit existing fixture references; this gate never provisions records."""
    fixture = json.loads(Path(fixture_path).read_text())
    required = {"deal_uid", "company_uid", "interaction_uid", "contact_uid", "profile_uid", "prompter_uid"}
    require(required <= fixture.keys() and not fixture.keys() - required - {"solution_selling_uid", "inputs"},
            "Solution Selling fixture must contain only the documented explicit references and inputs.")
    for key in required | ({"solution_selling_uid"} if fixture.get("solution_selling_uid") else set()):
        fixture[key] = str(uuid.UUID(fixture[key]))
    assessment = ({"solution_selling_uid": fixture["solution_selling_uid"]}
                  if fixture.get("solution_selling_uid") else {})
    render = {"contact_uid": fixture["contact_uid"], "company_uid": fixture["company_uid"],
              "profile_uid": fixture["profile_uid"], "deal_uid": fixture["deal_uid"],
              "inputs": fixture.get("inputs", {}), **assessment}
    context = {"deal_uid": fixture["deal_uid"], "interaction_page_size": 2}
    prepare = {"interaction_uid": fixture["interaction_uid"], "contact_uid": fixture["contact_uid"],
               "profile_uid": fixture["profile_uid"], **assessment}
    return [
        {"tool": "crm_prompters_render", "arguments": {"uid": fixture["prompter_uid"], "payload": render},
         "path": f"/extensions/solution-selling/prompters/{fixture['prompter_uid']}/render/", "payload": render},
        {"tool": "crm_solution_selling_context_get", "arguments": context,
         "path": "/extensions/solution-selling/context/", "payload": context},
        {"tool": "crm_diagnoses_prepare", "arguments": prepare,
         "path": "/extensions/solution-selling/diagnoses/prepare/", "payload": prepare},
    ]


def verify(contact_uid=None, solution_selling_fixture=None, *, hosted_data=False):
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
    requests = (solution_selling_reads(solution_selling_fixture) if solution_selling_fixture else
                [{"tool": requested_tool, "arguments": arguments,
                  "path": "/api/crm/v1/" + query, "params": params}])
    if not hosted_data:
        require(not contact_uid and not solution_selling_fixture,
                "Existing hosted fixtures require explicit --hosted-data.")
        requests = [{"tool": "crm_settings_get", "arguments": {},
                     "path": "/api/crm/v1/settings/", "params": {}}]
    expected = [{"tool": r["tool"], "arguments": r["arguments"]} for r in requests]
    report.update(business_reads=expected)
    prompt = ("Perform a read-only CRM verification. Discover the CRM MCP schemas with "
              "crm__list_tools, then use crm__call_tool to run exactly these reads in order: "
              f"{json.dumps(expected)}. "
              "Do not create, edit, archive, or call any other business tool. "
              "Never retry an uncertain tool call. Report the actual returned results briefly.")
    if solution_selling_fixture:
        prompt += " Load the solution-selling project skill before using its workflow."
    try:
        with ExitStack() as stack, httpx.Client(trust_env=False, timeout=90) as client:
            if not hosted_data:
                environment, report["isolated_catalog"] = isolated_catalog(environment, run, stack)
                save()
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
            for request in requests:
                require(any(not p.get("isError") and
                            any(t.get("name") == request["tool"] for t in
                                p.get("result", {}).get("details", {}).get("tools", []))
                            for p in discovery), "CRM discovery did not return a requested tool.")
            allowed = {"crm__list_tools", "crm__call_tool"}
            if solution_selling_fixture:
                allowed.add("read")  # SDK-owned read is restricted to discovered project skills.
            require(all(p["toolName"] in allowed for p in calls),
                    "The agent used a tool outside the requested CRM read workflow.")
            business = [p for p in calls if p["toolName"] == "crm__call_tool"]
            require([p["args"] for p in business] == expected,
                    "Require exactly the scoped CRM MCP reads in order; no retries or writes.")
            results = [business_result(p) for p in business]
            if solution_selling_fixture:
                rendered, context, prepared = results
                require(bool(rendered["text"]), "Rendering must return a nonempty draft.")
                require(context["deal"]["uid"] == requests[1]["arguments"]["deal_uid"],
                        "Context returned a different Deal.")
                require(context["interactions"]["items"] and context["sources"],
                        "Context must exercise actual Interaction history and source versions.")
                require(prepared["saved"] is False and prepared["business_issue_status"] == "hypothesis",
                        "Diagnosis preparation must remain an unsaved hypothesis.")
                entries = [entry for row in prepared["draft"]["matrix"].values()
                           for cell in row.values() for entry in cell]
                require(entries and all(e["answer"] is None for e in entries),
                        "The live fixture must exercise copied questions with empty answers.")
                report["read_evidence"] = {"sources": context["sources"], "draft_saved": False,
                                           "prepared_questions": len(entries), "rendered_chars": len(rendered["text"])}
            elif contact_uid:
                require(results[0]["uid"] == contact_uid, "MCP returned a different Contact.")
                report["read_evidence"] = {k: results[0].get(k) for k in ("uid", "version")}
            elif hosted_data:
                require(results[0]["items"] == [] and results[0]["pageInfo"]["totalItems"] == 0,
                        "The unique read-only search must have no matches.")
                report["read_evidence"] = {"total_items": 0}
            else:
                require(results[0]["configuration_version"] > 0,
                        "MCP must read initialized persisted CRM settings.")
                report["read_evidence"] = {
                    "configuration_version": results[0]["configuration_version"],
                }
            report["mcp_read_verified"] = True
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
            for request, result in zip(requests, results, strict=True):
                if "payload" in request:
                    response = client.post(api + request["path"], json=request["payload"])
                    require(response.status_code == 200,
                            f"Fresh read-only POST returned HTTP {response.status_code}.")
                    independent = response.json()
                else:
                    independent = get_json(client, api + request["path"], params=request["params"])
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
    parser.add_argument("--hosted-data", action="store_true",
                        help="Explicit read-only check against the Environment database, not the private local gate.")
    parser.add_argument("--contact-uid", help="Read this exact controlled contact instead of an empty search.")
    parser.add_argument("--solution-selling-fixture", help="JSON file with explicit existing fixture UIDs; exercises all three read helpers.")
    args = parser.parse_args()
    require(not (args.contact_uid and args.solution_selling_fixture), "Choose one live read scenario.")
    if args.pre_push:
        check_push()
    return verify(args.contact_uid, args.solution_selling_fixture, hosted_data=args.hosted_data)


if __name__ == "__main__":
    raise SystemExit(main())
