"""
Development OTP provider: prints the code to stdout instead of sending an SMS.

Replace with a real provider (Twilio, MSG91) for production. Keep this stub
under MOCK_SMS=true in dev to avoid burning SMS credits.
"""
import logging

logger = logging.getLogger(__name__)


class StubSmsSender:
    async def send(self, phone: str, code: str) -> None:
        bar = "=" * 44
        logger.info("[PIN STUB] phone=+91%s code=%s", phone, code)
        print(f"\n{bar}\n  [PIN STUB]  +91{phone}  →  {code}\n{bar}\n", flush=True)
