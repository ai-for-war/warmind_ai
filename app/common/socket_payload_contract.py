from __future__ import annotations

"""Shared payload helpers for outbound Socket.IO business events."""

from typing import Any


def enrich_socket_payload(
    data: dict[str, Any],
    organization_id: str | None = None,
) -> dict[str, Any]:
    """Return an additive payload containing top-level organization context.

    Existing payload fields are preserved. If organization_id is already present
    in `data`, that value is kept to avoid overriding emitter-specific payloads.
    """
    payload = dict(data)

    if organization_id:
        payload.setdefault("organization_id", organization_id)

    return payload
