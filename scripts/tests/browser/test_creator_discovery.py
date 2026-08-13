"""Browser acceptance for the two-layer Creator and capability journey."""

import os

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
        page.locator(".creator-discovery textarea").fill(
            "我想更高效地处理每天收到的信息。"
        )
        page.get_by_role("button", name="拆解想法").click()

        page.locator(
            ".creator-model-setup, .creator-clarification, "
            ".creator-discovery-error"
        ).first.wait_for(timeout=30000)
        if page.locator(".creator-model-setup").is_visible():
            if os.environ.get("SAME_ORIGIN_PRODUCT") == "1":
                raise AssertionError("Full product acceptance stopped at model setup")
            assert not discovery_requests, "Unbound Creator must not call the discovery API"
            unexpected = [
                error for error in console_errors if "status of 409" not in error
            ]
            assert not unexpected, f"Browser console errors: {unexpected}"
            browser.close()
            return

        if page.locator(".creator-discovery-error").is_visible():
            if os.environ.get("SAME_ORIGIN_PRODUCT") == "1":
                raise AssertionError(
                    "Full product acceptance skipped a discovery failure: "
                    + page.locator(".creator-discovery-error").inner_text()
                )
            assert discovery_requests, "Intent Studio did not call the discovery API"
            browser.close()
            return

        page.locator(".creator-clarification").wait_for(timeout=5000)
        assert "你希望" in page.locator(".creator-clarification h2").inner_text()
        page.get_by_role("button", name="每天生成一份可审核的中文简报").click()
        page.locator(".creator-possibilities article").first.wait_for(timeout=5000)
        assert "中文" in page.locator(".creator-possibilities article").nth(1).inner_text()

        page.get_by_role("button", name="用这个方向生成方案").first.click()
        page.locator(".creator-node").first.wait_for(timeout=30000)
        assert "/projects/" in page.url and page.url.endswith("/studio")

        if os.environ.get("SAME_ORIGIN_PRODUCT") == "1":
            page.locator(".creator-node-unresolved").first.click()
            deep_link = page.locator(".creator-capability-gap a")
            deep_link.wait_for(timeout=5000)
            deep_link.click()
            page.locator(".creator-handoff").wait_for(timeout=10000)
            assert page.locator(".handoff-path > div").count() == 2
            page.locator(".return-to-creator").wait_for()
            page.locator(".creator-handoff form button").click()
            page.locator(".workshop-tabs").wait_for(timeout=10000)
            page.locator(".creator-handoff-banner").wait_for()
            page.locator(".creator-handoff-banner a").wait_for()

        assert not console_errors, f"Browser console errors: {console_errors}"
        browser.close()


if __name__ == "__main__":
    main()
