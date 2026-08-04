"""Browser smoke test for the Creator Studio's real discovery boundary."""
import os
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright


def main() -> None:
    errors: list[str] = []
    requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: requests.append(request.url) if "/api/creator/possibilities" in request.url else None)
        page.goto(os.environ.get("CREATOR_STUDIO_URL", "http://127.0.0.1:5180/"), wait_until="networkidle")
        page.get_by_label("Creative intent").fill("我想持续了解 AI 行业的变化")
        page.get_by_role("button", name="帮我打开思路").click()
        if os.environ.get("CREATOR_DISCOVERY_EXPECT_READY") != "1":
            page.get_by_role("status").filter(has_text="AI 方向发现尚未连接").wait_for(timeout=5000)
            assert requests, "Creator did not call the discovery API"
            assert not page.get_by_role("heading", name="可以从这里开始").count()
            unexpected_errors = [error for error in errors if "status of 409" not in error]
            assert not unexpected_errors, f"Browser console errors: {unexpected_errors}"
            browser.close()
            return
        try:
            page.get_by_role("heading", name="可以从这里开始").wait_for(timeout=5000)
        except Exception as exc:
            raise AssertionError(f"Discovery did not render: {page.locator('main').inner_text()}; requests={requests}; console={errors}") from exc
        page.get_by_role("button", name="选择这个方向").first.click()
        page.get_by_role("heading", name="设计流程").wait_for()
        assert "/projects/project-" in page.url and page.url.endswith("/creator")
        if os.environ.get("SAME_ORIGIN_PRODUCT") == "1":
            location = urlsplit(page.url)
            project_id = page.url.split("/projects/", 1)[1].split("/", 1)[0]
            page.goto(f"{location.scheme}://{location.netloc}/projects/{project_id}/developer", wait_until="networkidle")
            try:
                page.get_by_role("heading", name="工程验证").wait_for(timeout=5000)
            except Exception as exc:
                raise AssertionError(f"Developer project view did not render: {page.locator('main').inner_text()}; console={errors}") from exc
            assert "我想持续了解 AI 行业的变化" not in page.locator("main").inner_text()
        assert not errors, f"Browser console errors: {errors}"
        browser.close()


if __name__ == "__main__":
    main()
