import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError

from app.auth.jwks import get_jwks_client
from app.core.config import Settings


def decode_stack_access_token(token: str, settings: Settings) -> dict:
    try:
        jwks = get_jwks_client(settings.stack_jwks_url)
        signing_key = jwks.get_signing_key_from_jwt(token)
        issuers = [settings.stack_issuer_user, settings.stack_issuer_anonymous]
        last: Exception | None = None
        for issuer in issuers:
            try:
                return jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256"],
                    issuer=issuer,
                    options={"verify_aud": False},
                )
            except jwt.InvalidIssuerError as e:
                last = e
                continue
        if last:
            raise last
        raise jwt.InvalidTokenError("no issuer matched")
    except InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid access token") from e
