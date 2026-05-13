from typing import Protocol


class OtpSender(Protocol):
    """Send a one-time code to a phone."""
    async def send(self, phone: str, code: str) -> None: ...
