from __future__ import annotations

from datetime import timezone

import pytest

from app.infrastructure.database.mongodb import MongoDB
import app.infrastructure.database.mongodb as mongodb_module


class _FakeMotorClient:
    def __init__(self, uri: str, **kwargs: object) -> None:
        self.uri = uri
        self.kwargs = kwargs
        self.closed = False

    def __getitem__(self, db_name: str) -> dict[str, str]:
        return {"name": db_name}

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_connect_configures_timezone_aware_utc_decoding(monkeypatch) -> None:
    monkeypatch.setattr(mongodb_module, "AsyncIOMotorClient", _FakeMotorClient)

    await MongoDB.connect("mongodb://example", "app_db")

    assert isinstance(MongoDB.client, _FakeMotorClient)
    assert MongoDB.client.uri == "mongodb://example"
    assert MongoDB.client.kwargs == {"tz_aware": True, "tzinfo": timezone.utc}
    assert MongoDB.db == {"name": "app_db"}
