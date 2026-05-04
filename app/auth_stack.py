import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError, PyJWKClient

from app.config import Settings

_jwks_clients: dict[str, PyJWKClient] = {}


def _jwks_client(jwks_url: str) -> PyJWKClient:
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=600,
            max_cached_keys=8,
        )
    return _jwks_clients[jwks_url]


def decode_stack_access_token(token: str, settings: Settings) -> dict:
    try:
        jwks = _jwks_client(settings.stack_jwks_url)
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
