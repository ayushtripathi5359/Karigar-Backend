from typing import Protocol


class OtpSender(Protocol):
    """Send a one-time code to a phone. Implementations: sms_stub, twilio, msg91."""

    async def send(self, phone: str, code: str) -> None: ...
