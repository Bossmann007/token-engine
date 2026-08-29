"""Harness client and API integration tests."""

import json
from pathlib import Path

import pytest

from token_engine.core.types import ContentItem, ContentType
from token_engine.harness.client import HarnessClient

FIXTURES = Path(__file__).parent.parent / "benchmarks" / "fixtures"


class TestHarnessClientLocal:
    def test_optimize_context_in_process(self):
        client = HarnessClient(prefer_api=False)
        data = json.loads((FIXTURES / "agent_context.json").read_text(encoding="utf-8"))
        items = [
            ContentItem(
                id=item["id"],
                content=item["content"],
                content_type=ContentType(item.get("content_type", "unknown")),
                source=item.get("source", ""),
                metadata=item.get("metadata", {}),
            )
            for item in data["items"]
        ]
        out = client.optimize_context(items, task_query="fix authentication login")
        assert out["content"]
        assert out["stats"]["tokens_saved"] > 0
        assert "AuthService" in out["content"]

    def test_optimize_messages(self):
        client = HarnessClient(prefer_api=False)
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Fix login bug in auth module"},
            {"role": "assistant", "content": "I'll inspect auth/login.py"},
        ]
        out = client.optimize_messages(messages)
        assert out["content"]
        assert "login" in out["content"].lower()

    def test_health_in_process(self):
        client = HarnessClient(prefer_api=False)
        assert client.health()["status"] == "ok"


@pytest.fixture
def api_client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from token_engine.api.server import app

    return TestClient(app)


class TestHarnessAPI:
    def test_optimize_context_endpoint(self, api_client):
        payload = {
            "items": [
                {
                    "id": "log",
                    "content": "ERROR: fail\n" + "INFO: ok\n" * 50,
                    "content_type": "log",
                    "source": "pytest",
                }
            ],
            "quality": "balanced",
            "task_query": "fix test failure",
        }
        response = api_client.post("/optimize-context", json=payload)
        assert response.status_code == 200
        body = response.json()
        assert body["stats"]["tokens_saved"] >= 0
        assert "ERROR" in body["content"]
        assert "metadata" in body or "stats" in body

    def test_harness_client_via_api(self, api_client, monkeypatch):
        client = HarnessClient(prefer_api=True)
        monkeypatch.setattr(client, "_api_available", lambda: True)
        monkeypatch.setattr(client, "_post", lambda path, payload: api_client.post(path, json=payload).json())
        out = client.optimize_messages([{"role": "user", "content": "hello " * 200}])
        assert out["content"]
