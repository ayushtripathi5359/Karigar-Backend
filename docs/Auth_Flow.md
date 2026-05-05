# Authentication — Flow & Data Model

## Workflow (sequence diagram)

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend (Web/Mobile)
    participant Stack as Stack Auth (external IdP)
    participant API as FastAPI Backend
    participant JWKS as PyJWKClient cache<br/>(auth/jwks.py)
    participant DB as PostgreSQL<br/>app_users

    User->>FE: 1. Open app, click Login
    FE->>Stack: 2. POST credentials / OAuth
    Stack-->>FE: 3. Access JWT (ES256, signed by Stack)

    User->>FE: triggers protected action
    FE->>API: 4. GET /v1/me<br/>Authorization: Bearer <JWT>

    Note over API: middleware<br/>RequestId + AccessLog
    Note over API: deps/auth.py — BearerDep<br/>strip "Bearer ", trim

    API->>JWKS: 5a. need signing key for token kid?
    alt cache miss / first call
        JWKS->>Stack: 5b. GET .../.well-known/jwks.json
        Stack-->>JWKS: public keys
    end
    JWKS-->>API: signing key

    Note over API: auth/stack.py<br/>jwt.decode(token, key, ES256, issuer)<br/>try issuer = user OR anonymous
    alt invalid signature / wrong issuer / expired
        API-->>FE: 401 UNAUTHORIZED<br/>{error: "UNAUTHORIZED", message: "invalid access token"}
    end

    Note over API: services/user_service.py<br/>sync_user_from_claims(claims)
    API->>DB: SELECT * FROM app_users WHERE stack_user_id = sub
    alt first time login
        API->>DB: INSERT app_users(stack_user_id, email)
    else email changed in claims
        API->>DB: UPDATE email
    end
    DB-->>API: AppUser row

    opt route requires role
        Note over API: deps/roles.py — require_role(...)
        alt user.role not allowed
            API-->>FE: 403 FORBIDDEN
        end
    end

    Note over API: routers/users.py<br/>build MeResponse
    API-->>FE: 7. 200 OK + MeResponse JSON<br/>X-Request-ID echoed
    FE-->>User: render profile
```

## Data model (ER)

Stack Auth owns identity. Your DB owns one mirror table that links via Stack's `sub` claim.

```mermaid
erDiagram
    STACK_AUTH_USER ||--|| APP_USERS : "linked by sub claim"

    STACK_AUTH_USER {
        string sub PK "owned by Stack — never stored locally"
        string email
        string name
        boolean email_verified
        string iss "issuer URL"
        int exp "JWT expiry"
    }

    APP_USERS {
        uuid id PK "local primary key"
        string stack_user_id UK "= JWT sub claim, indexed"
        string email "synced from claims"
        string display_name
        string role "user / dealer / admin / vendor"
        timestamp onboarding_completed_at
        text raw_profile
        timestamp created_at
        timestamp updated_at
    }
```

### Why a mirror table

| What | Where it lives | Why |
|---|---|---|
| Email + password, MFA, OAuth, password reset | Stack Auth | We never store credentials |
| `sub` (Stack user id) | JWT claim — re-derived per request | Source of truth for identity |
| `role`, `onboarding_completed_at`, app-specific profile | `app_users` (local) | Stack doesn't know about your app's domain |
| Foreign keys from saved_diamonds, transactions, etc. | local DB → `app_users.id` | Joins stay inside Postgres |

## Request lifecycle (top-down)

```mermaid
flowchart TD
    A[Bearer token arrives] --> B{header present<br/>and starts with 'Bearer '?}
    B -- no --> E1[401 UNAUTHORIZED<br/>missing bearer token]
    B -- yes --> C[fetch signing key from JWKS cache]
    C --> D{signature + issuer<br/>valid?}
    D -- no --> E2[401 UNAUTHORIZED<br/>invalid access token]
    D -- yes --> F[claims dict]
    F --> G{sub present?}
    G -- no --> E3[401 UNAUTHORIZED<br/>token missing sub]
    G -- yes --> H[SELECT app_users WHERE stack_user_id = sub]
    H --> I{row exists?}
    I -- no --> J[INSERT new AppUser<br/>role = 'user']
    I -- yes --> K{email differs<br/>from claims?}
    K -- yes --> L[UPDATE email]
    K -- no --> M[use existing row]
    J --> N[AppUser ready]
    L --> N
    M --> N
    N --> O{route uses<br/>require_role?}
    O -- yes --> P{user.role<br/>allowed?}
    P -- no --> E4[403 FORBIDDEN<br/>insufficient role]
    P -- yes --> Q
    O -- no --> Q[run route handler]
    Q --> R{slowapi rate<br/>limit ok?}
    R -- no --> E5[429 RATE_LIMITED]
    R -- yes --> S[200 OK + response body]

    classDef err fill:#ffe3e3,stroke:#c92a2a;
    classDef ok  fill:#d3f9d8,stroke:#2f9e44;
    class E1,E2,E3,E4,E5 err
    class S ok
```

## Components → files map

| Component | File |
|---|---|
| App entrypoint, middleware wiring, CORS, lifespan | [app/main.py](../app/main.py) |
| Settings (env + Stack URLs) | [app/core/config.py](../app/core/config.py) |
| Logging | [app/core/logging_config.py](../app/core/logging_config.py) |
| DB session + Base | [app/db/session.py](../app/db/session.py) |
| `AppUser` model | [app/models/user.py](../app/models/user.py) |
| Pydantic schemas (`MeResponse`, onboarding) | [app/schemas/](../app/schemas/) |
| Bearer header dep + current_user | [app/deps/auth.py](../app/deps/auth.py) |
| Role gate | [app/deps/roles.py](../app/deps/roles.py) |
| JWT verify against Stack | [app/auth/stack.py](../app/auth/stack.py) |
| JWKS cache | [app/auth/jwks.py](../app/auth/jwks.py) |
| First-login upsert / email sync | [app/services/user_service.py](../app/services/user_service.py) |
| Onboarding completion | [app/services/onboarding_service.py](../app/services/onboarding_service.py) |
| Routes — `/v1/me` | [app/routers/users.py](../app/routers/users.py) |
| Routes — `/v1/onboarding/complete` | [app/routers/onboarding.py](../app/routers/onboarding.py) |
| Routes — `/health` | [app/routers/health.py](../app/routers/health.py) |
| Request ID middleware | [app/middleware/request_id.py](../app/middleware/request_id.py) |
| Access log middleware | [app/middleware/logging_access.py](../app/middleware/logging_access.py) |
| Rate limiter | [app/limiter/rate_limit.py](../app/limiter/rate_limit.py) |
| Centralized error envelope | [app/errors.py](../app/errors.py) |

## Failure modes (what you actually see)

| Symptom | HTTP | Cause |
|---|---|---|
| `{"error":"UNAUTHORIZED","message":"missing bearer token"}` | 401 | header missing or not `Bearer ...` |
| `{"error":"UNAUTHORIZED","message":"invalid access token"}` | 401 | bad signature / expired / wrong issuer / unknown kid |
| `{"error":"UNAUTHORIZED","message":"token missing sub"}` | 401 | malformed claims |
| `{"error":"FORBIDDEN","message":"insufficient role"}` | 403 | role gate failed |
| `{"error":"RATE_LIMITED",...}` | 429 | slowapi tripped |
| `{"error":"VALIDATION_ERROR",...}` | 422 | request body / params don't match schema |
| `{"error":"INTERNAL_ERROR",...}` | 500 | unhandled — check `request_id` in logs |

Every response includes `X-Request-ID`; the same id is in the access log line, so a single grep ties browser → log → trace.
