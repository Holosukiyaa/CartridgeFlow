"""Browser smoke test for the Intent Studio discovery boundary."""

import os
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def main() -> None:
    console_errors: list[str] = []
    discovery_requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 864})
        page.on(
            "console",
            lambda message: console_errors.append(message.text)
            if message.type == "error"
            else None,
        )
        page.on(
            "request",
            lambda request: discovery_requests.append(request.url)
            if "/api/creator/possibilities" in request.url
            else None,
        )

        page.goto(
            os.environ.get("INTENT_STUDIO_URL", "http://127.0.0.1:5180/"),
            wait_until="networkidle",
        )
        page.get_by_role("button", name="方向探索").click()
        page.locator(".creator-discovery textarea").fill(
            "我想持续了解 AI 行业变化，并生成可以审核来源的中文日报。"
        )
        page.get_by_role("button", name="探索方向").click()

        page.locator(
            ".creator-model-setup, .creator-possibilities article, "
            ".creator-discovery-error"
        ).first.wait_for(timeout=30000)
        if page.locator(".creator-model-setup").is_visible():
            unexpected = [
                error for error in console_errors if "status of 409" not in error
            ]
            assert not unexpected, f"Browser console errors: {unexpected}"
            browser.close()
            return

        if page.locator(".creator-discovery-error").is_visible():
            assert discovery_requests, "Intent Studio did not call the discovery API"
            browser.close()
            return

        page.get_by_role("button", name="沿这个方向编排").first.wait_for(
            timeout=5000
        )

        page.get_by_role("button", name="沿这个方向编排").first.click()
        page.get_by_role("button", name="方案编排").wait_for()
        assert "/projects/project-" in page.url and page.url.endswith("/studio")

        if os.environ.get("SAME_ORIGIN_PRODUCT") == "1":
            location = urlsplit(page.url)
            project_id = page.url.split("/projects/", 1)[1].split("/", 1)[0]
            page.goto(
                f"{location.scheme}://{location.netloc}/projects/{project_id}/capabilities",
                wait_until="networkidle",
            )
            page.get_by_text("能力工坊", exact=True).first.wait_for(timeout=5000)

        assert not console_errors, f"Browser console errors: {console_errors}"
        browser.close()


if __name__ == "__main__":
    main()
