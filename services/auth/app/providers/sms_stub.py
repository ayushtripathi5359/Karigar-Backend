import logging

logger = logging.getLogger(__name__)


class StubSmsSender:
    async def send(self, phone: str, code: str) -> None:
        bar = "=" * 44
        logger.info("[PIN STUB] phone=+91%s code=%s", phone, code)
        print(f"\n{bar}\n  [PIN STUB]  +91{phone}  ->  {code}\n{bar}\n", flush=True)
