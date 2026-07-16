from app.db import async_session


def mcp_db():
    return async_session()
