from jwt import PyJWKClient

_clients: dict[str, PyJWKClient] = {}


def get_jwks_client(jwks_url: str) -> PyJWKClient:
    if jwks_url not in _clients:
        _clients[jwks_url] = PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=600,
            max_cached_keys=8,
        )
    return _clients[jwks_url]
