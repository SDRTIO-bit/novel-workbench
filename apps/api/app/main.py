from contextlib import asynccontextmanager, AsyncExitStack
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from app.config import settings
from app.db import init_db, async_session
from app.errors import AppError, app_error_handler, validation_error_handler
from app.mcp_server import mcp, mcp_http_app
from app.mcp_auth import MCPAuthMiddleware

# Import models to ensure they are registered with Base.metadata
import app.models.project  # noqa: F401
import app.models.chapter  # noqa: F401
import app.models.prompt  # noqa: F401
import app.models.provider  # noqa: F401
import app.models.workflow  # noqa: F401
import app.models.generation  # noqa: F401
import app.models.detector_feedback  # noqa: F401


@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mcp_http_app.lifespan(app))
        await init_db()
        async with async_session() as session:
            from app.services.prompt_service import PromptService
            prompt_svc = PromptService(session)
            await prompt_svc.init_builtins()

            from app.services.provider_service import ProviderService
            provider_svc = ProviderService(session)
            await provider_svc.init_builtins()

            from app.services.workflow_service import WorkflowService
            workflow_svc = WorkflowService(session)
            await workflow_svc.init_builtin_default()

            await session.commit()
        yield


app = FastAPI(title=settings.app_name, lifespan=combined_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(MCPAuthMiddleware)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

from app.routers.projects import router as projects_router  # noqa: E402
from app.routers.chapters import router as chapters_router  # noqa: E402
from app.routers.import_export import router as import_export_router  # noqa: E402
from app.routers.prompts import router as prompts_router  # noqa: E402
from app.routers.providers import router as providers_router  # noqa: E402
from app.routers.workflows import router as workflows_router  # noqa: E402
from app.routers.context import router as context_router  # noqa: E402
from app.routers.runs import router as runs_router  # noqa: E402
from app.routers.detector_feedbacks import router as detector_feedbacks_router  # noqa: E402

app.include_router(projects_router)
app.include_router(chapters_router)
app.include_router(import_export_router)
app.include_router(prompts_router)
app.include_router(providers_router)
app.include_router(workflows_router)
app.include_router(context_router)
app.include_router(runs_router)
app.include_router(detector_feedbacks_router)

app.mount("/mcp", mcp_http_app)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
