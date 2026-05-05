import logging
import random
import string

logger = logging.getLogger(__name__)


def generate_pin(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


async def deliver_pin(phone: str, code: str) -> None:
    logger.info("[PIN STUB] phone=+91%s code=%s", phone, code)
    print(f"\n{'='*44}\n  [PIN STUB]  +91{phone}  →  {code}\n{'='*44}\n", flush=True)
