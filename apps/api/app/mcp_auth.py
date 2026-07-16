from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings


class MCPAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/mcp"):
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {settings.mcp_access_token}"
            if auth != expected:
                return Response(
                    content='{"error":{"code":"UNAUTHORIZED","message":"MCP access token required"}}',
                    status_code=401,
                    media_type="application/json",
                )
        return await call_next(request)
