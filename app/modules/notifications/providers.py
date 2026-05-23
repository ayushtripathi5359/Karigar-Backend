from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx


@dataclass(frozen=True)
class PushMessage:
    outbox_id: UUID
    push_token: str
    title: str
    body: str | None
    data: dict | None


@dataclass(frozen=True)
class PushDeliveryResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


class PushProvider:
    async def send(self, message: PushMessage) -> PushDeliveryResult:
        raise NotImplementedError


class StubPushProvider(PushProvider):
    async def send(self, message: PushMessage) -> PushDeliveryResult:
        return PushDeliveryResult(ok=True, provider_message_id=f"stub:{message.outbox_id}")


class ExpoPushProvider(PushProvider):
    endpoint = "https://exp.host/--/api/v2/push/send"

    async def send(self, message: PushMessage) -> PushDeliveryResult:
        payload = {
            "to": message.push_token,
            "title": message.title,
            "body": message.body or "",
            "data": message.data or {},
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.endpoint, json=payload)
            if response.status_code >= 400:
                return PushDeliveryResult(ok=False, error=response.text)
            data = response.json()
            ticket = data.get("data") if isinstance(data, dict) else None
            return PushDeliveryResult(
                ok=True,
                provider_message_id=ticket.get("id") if isinstance(ticket, dict) else None,
            )
        except Exception as exc:  # noqa: BLE001
            return PushDeliveryResult(ok=False, error=str(exc))

