"""Browser smoke test for the Creator Studio discovery-to-recipe loop."""
from playwright.sync_api import sync_playwright


def main() -> None:
    errors: list[str] = []
    requests: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("request", lambda request: requests.append(request.url) if "/api/creator/possibilities" in request.url else None)
        page.goto("http://127.0.0.1:5180/", wait_until="networkidle")
        page.get_by_label("Creative intent").fill("我想持续了解 AI 行业的变化")
        page.get_by_role("button", name="帮我打开思路").click()
        try:
            page.get_by_role("heading", name="可以从这里开始").wait_for(timeout=5000)
        except Exception as exc:
            raise AssertionError(f"Discovery did not render: {page.locator('main').inner_text()}; requests={requests}; console={errors}") from exc
        page.get_by_role("button", name="选择这个方向").first.click()
        page.get_by_role("heading", name="设计流程").wait_for()
        assert page.get_by_role("button", name="发现并审核相关公开来源").is_visible()
        assert not errors, f"Browser console errors: {errors}"
        browser.close()


if __name__ == "__main__":
    main()
