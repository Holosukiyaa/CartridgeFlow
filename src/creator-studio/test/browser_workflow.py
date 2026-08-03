"""Run with: python test/browser_workflow.py

Requires the Python ``playwright`` package and an installed Chromium browser.
The workflow launches the local Vite server, mocks the Creator HTTP API, and
writes an ignored screenshot to test/output/creator-browser-workflow.png.
"""
import json
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "test" / "output" / "creator-browser-workflow.png"
BASE = "http://127.0.0.1:4179"


def projection():
    return {"session_id": "s1", "revision": 1, "intent": "Summarize declared information",
            "semantic_steps": [{"id": "start", "intent": "Begin the work", "plain_inputs": [], "plain_outputs": []}],
            "steps": [{"id": "start", "intent": "Begin the work"}], "relationships": [],
            "sources": [{"id": "source-1", "kind": "source", "digest": "0" * 64, "role": "Declared source", "remote_url": "https://example.com/old"}],
            "pending_proposals": [], "active_freezes": [{"id": "freeze-1", "steps": ["start"], "freeze_revision": {"source_freeze_ids": ["freeze-1"], "expected_revision": 1}}],
            "frozen_steps": ["start"], "history": [{"id": "accept-1", "revision": 1, "summary": "Earlier change"}], "blocked_findings": [],
            "design_checks": {"findings": []}, "generation_readiness": {"ready": True, "blocked_findings": [], "compile_candidate": {"reference": "candidate"}}}


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(["npm.cmd", "run", "dev", "--", "--host", "127.0.0.1", "--port", "4179"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1100})
            seen = []

            def api(route):
                request = route.request
                path = request.url.split("?")[0]
                body = json.loads(request.post_data or "{}")
                seen.append((path, body))
                if request.method == "GET": payload = {"creator": projection()}
                elif path.endswith("/ai-proposals"):
                    payload = {"proposal": {"proposal_id": "ai-1", "revision": 1, "summary": "Frozen AI edit", "changes": [{"id": "ai-change-primary", "target_id": "start", "operation": "set_step_intent"}, {"id": "ai-change-secondary", "target_id": "start", "operation": "set_creator_binding"}]}}
                elif path.endswith("/proposals"):
                    value = body["changes"][0]["value"]
                    assert body["changes"][0]["operation"] == "update_source"
                    assert value["id"] == "source-1" and value["kind"] == "source" and len(value["digest"]) == 64
                    payload = {"proposal": {"proposal_id": "source-1", "revision": 1, "summary": "Source edit", "changes": [{"id": "source-change", "target_id": "source-1", "operation": "update_source"}]}}
                elif path.endswith("/preview"):
                    if "ai-1" in path:
                        assert body["freeze_revision"] == {"source_freeze_ids": ["freeze-1"], "expected_revision": 1, "reason": "Creator approved this revision to the selected frozen design step.", "author": "creator"}
                        selected = body["selected_change_ids"]
                        payload = {"accepted_change_ids": selected, "impact": {"plain_summary": "Frozen AI edit will create revision 2.", "changed_steps": ["start"], "changed_sources": []}}
                    else: payload = {"accepted_change_ids": ["source-change"], "impact": {"plain_summary": "Source edit will create revision 2.", "changed_steps": [], "changed_sources": ["source-1"]}}
                elif path.endswith("/accept"):
                    if "ai-1" in path: assert body["freeze_revision"]["source_freeze_ids"] == ["freeze-1"]
                    payload = {"creator": projection(), "impact": {}, "accepted_change_ids": body["selected_change_ids"]}
                elif path.endswith("/reverse"):
                    route.fulfill(status=409, content_type="application/json", body=json.dumps({"detail": {"code": "AUTHORING_REVERSAL_AMBIGUOUS", "message": "Cannot reverse safely."}})); return
                elif path.endswith("/design-checks"): payload = {"design_checks": {"findings": []}}
                elif path.endswith("/generation-readiness"): payload = {"generation_readiness": projection()["generation_readiness"]}
                elif path.endswith("/compile-candidate"): payload = {"compile_candidate": {"id": "compile-1"}}
                else: payload = {"creator": projection()}
                route.fulfill(content_type="application/json", body=json.dumps(payload))

            page.route("**/api/creator/**", api)
            for _ in range(40):
                try: page.goto(BASE); break
                except Exception: time.sleep(.25)
            else: raise RuntimeError("Vite did not start")
            page.evaluate("localStorage.setItem('creator-session-id', 's1')")
            page.reload(); page.get_by_text("Sources").wait_for()
            page.get_by_label("Edit source source-1").fill("https://example.com/new")
            page.get_by_role("button", name="Update source").click(); page.get_by_text("Source edit will create revision 2.").wait_for()
            page.get_by_role("button", name="Accept selected (1)").click(); page.get_by_role("status").get_by_text("Accepted 1 selected change(s).").wait_for()
            page.get_by_label("Ask AI to modify the design").fill("Improve the frozen step")
            page.get_by_role("button", name="Ask AI").click(); page.get_by_text("Frozen AI edit will create revision 2.").wait_for()
            page.locator(".change input").nth(1).uncheck()
            page.get_by_role("button", name="Preview selected (1)").click(); page.get_by_text("Frozen AI edit will create revision 2.").wait_for()
            page.get_by_role("button", name="Accept selected (1)").click()
            page.get_by_role("status").get_by_text("Accepted 1 selected change(s).").wait_for()
            page.get_by_role("button", name="Reverse").click(); page.get_by_role("status").get_by_text("AUTHORING_REVERSAL_AMBIGUOUS").wait_for()
            page.get_by_role("button", name="Run design check").click(); page.get_by_role("button", name="Check readiness").click(); page.get_by_role("button", name="Create handoff candidate").click(); page.get_by_role("status").get_by_text("not signed or executing").wait_for()
            page.screenshot(path=str(OUTPUT), full_page=True)
            ai_previews = [body for path, body in seen if path.endswith("/ai-1/preview")]
            ai_accepts = [body for path, body in seen if path.endswith("/ai-1/accept")]
            assert ai_previews[-1]["selected_change_ids"] == ["ai-change-primary"]
            assert ai_accepts == [{"selected_change_ids": ["ai-change-primary"], "freeze_revision": {"source_freeze_ids": ["freeze-1"], "expected_revision": 1, "reason": "Creator approved this revision to the selected frozen design step.", "author": "creator"}}]
            assert any(path.endswith("/compile-candidate") for path, _ in seen)
            browser.close()
    finally:
        subprocess.run(["taskkill", "/PID", str(server.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)


if __name__ == "__main__": main()
