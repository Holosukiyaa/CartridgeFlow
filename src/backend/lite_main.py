import re

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.main import app


app.title = "CartridgeFlowLite"

_LITE_API_RULES = (
    re.compile(r"^/api/health$"),
    re.compile(r"^/api/base$"),
    re.compile(r"^/api/uploads/file$"),
    re.compile(r"^/api/lab/flows(?:/.*)?$"),
    re.compile(r"^/api/llm/(?:providers(?:/.*)?|assignments|detect|test|import/opencode|config/export)$"),
    re.compile(r"^/api/studio/resources$"),
    re.compile(r"^/api/studio/packages$"),
    re.compile(r"^/api/studio/release/[^/]+/preflight$"),
    re.compile(r"^/api/studio/environment(?:/.*)?$"),
    re.compile(r"^/api/cartridge-runs/[^/]+(?:/.*)?$"),
    re.compile(r"^/api/cartridges/import$"),
    re.compile(r"^/api/cartridges/[^/]+/(?:clone-to-dev|package|dlc/frontend|dlc/assets/.*)$"),
)

_REMOVED_WORKBENCH_PATHS = (
    "/assistant",
    "/steward/",
    "/certification",
)

_HIDDEN_FRAMEWORK_PATHS = {"/docs", "/redoc", "/openapi.json"}


def is_lite_api_allowed(path: str) -> bool:
    if path in _HIDDEN_FRAMEWORK_PATHS:
        return False
    if not path.startswith("/api/"):
        return True
    if path.startswith("/api/lab/flows/") and any(fragment in path for fragment in _REMOVED_WORKBENCH_PATHS):
        return False
    return any(rule.fullmatch(path) for rule in _LITE_API_RULES)


@app.middleware("http")
async def lite_api_surface(request: Request, call_next):
    if is_lite_api_allowed(request.url.path):
        return await call_next(request)
    return JSONResponse(
        status_code=404,
        content={
            "detail": {
                "code": "LITE_CAPABILITY_NOT_AVAILABLE",
                "message": "CartridgeFlowLite only exposes local cartridge workbench capabilities.",
                "path": request.url.path,
            }
        },
    )
