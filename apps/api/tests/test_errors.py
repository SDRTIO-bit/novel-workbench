from fastapi.testclient import TestClient
from app.main import app
from app.errors import AppError

client = TestClient(app)


async def test_app_error_format():
    @app.get("/_test_error")
    async def _test_error():
        raise AppError(code="TEST_ERROR", message="测试错误", details={"field": "test"})

    response = client.get("/_test_error")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "TEST_ERROR"
    assert body["error"]["message"] == "测试错误"
    assert body["error"]["details"] == {"field": "test"}
