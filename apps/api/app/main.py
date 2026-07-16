from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from app.config import settings
from app.db import init_db
from app.errors import AppError, app_error_handler, validation_error_handler

# Import models to ensure they are registered with Base.metadata
import app.models.project  # noqa: F401
import app.models.chapter  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)

from app.routers.projects import router as projects_router  # noqa: E402
from app.routers.chapters import router as chapters_router  # noqa: E402
from app.routers.import_export import router as import_export_router  # noqa: E402

app.include_router(projects_router)
app.include_router(chapters_router)
app.include_router(import_export_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
