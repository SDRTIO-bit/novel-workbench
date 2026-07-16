from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class AppError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None, status_code: int = 400):
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code


def not_found(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(code=code, message=message, details=details, status_code=404)


def conflict(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(code=code, message=message, details=details, status_code=409)


def bad_request(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(code=code, message=message, details=details, status_code=400)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = exc.errors()
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数无效",
                "details": details,
            }
        },
    )
