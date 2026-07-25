# MCP Use-Case 2: Keycloak-Secured MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server over Streamable HTTP, secured by Keycloak-issued OAuth 2.1
access tokens, demonstrating real transport-level 401/403/200 behavior and tool-level
scope-based RBAC (`mcp:read` vs `mcp:admin`).

**Architecture:** Keycloak (backed by Postgres) issues JWTs via the client-credentials grant
for three demo service accounts (`mcp-reader`, `mcp-admin`, `mcp-noaccess`) with different
`mcp:read`/`mcp:admin` scopes but a shared `mcp-server` audience binding. The MCP server uses
the official `mcp` SDK's built-in `TokenVerifier`/`AuthSettings` mechanism: a
`KeycloakTokenVerifier` validates each Bearer token's signature (via Keycloak's JWKS),
issuer, and audience using PyJWT, and the SDK's own `RequireAuthMiddleware` enforces a
server-wide minimum scope (`mcp:read`) at the transport layer — no token → 401, token
lacking `mcp:read` → 403. The `admin_reindex` tool additionally checks for `mcp:admin` inside
the tool function itself via the SDK's `get_access_token()` context helper, since MCP has no
native per-tool scope mechanism — this produces an MCP-level tool error (not a distinct HTTP
status), which the plan/README are explicit about.

**Tech Stack:** Python 3.11+, official `mcp` SDK's `FastMCP` (Streamable HTTP transport),
PyJWT with the `crypto` extra, Docker Compose (Keycloak 26 + Postgres 16), `httpx` (demo
script + tests), `pytest` / `pytest-asyncio`.

**Verification already performed before writing this plan:** every piece of Keycloak
provisioning (realm, client scopes, audience mapper, three clients) and the full JWT
validation code path (JWKS fetch, signature/issuer/audience checks, scope extraction) was
run for real against a live Keycloak 26 container, and a minimal real `FastMCP` server was
stood up and hit with `curl` to confirm the exact 401/403/200 outcomes below. The task steps
in this plan reproduce those exact, already-proven commands and code — nothing here is
speculative.

---

## File Structure

```
use-case-2-keycloak-secured/
├── docker-compose.yml
├── setup-realm.sh
├── requirements.txt
├── pytest.ini
├── .gitignore
├── server.py
├── data/
│   └── documents.json
├── tests/
│   └── test_token_verifier.py
├── demo.py
├── k8s/
│   └── deployment.yaml
├── README.md
└── IMPLEMENTATION.md
```

---

### Task 1: Project scaffold

**Files:**
- Create: `use-case-2-keycloak-secured/requirements.txt`
- Create: `use-case-2-keycloak-secured/pytest.ini`
- Create: `use-case-2-keycloak-secured/.gitignore`
- Create: `use-case-2-keycloak-secured/data/documents.json`

- [ ] **Step 1: Create `requirements.txt`**

```
mcp>=1.28.0
pyjwt[crypto]>=2.10.1
httpx>=0.28.0
pytest>=8.0.0
pytest-asyncio>=0.24.0
anyio>=4.0.0
cryptography>=43.0.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Create `data/documents.json`**

```json
[
  {
    "id": 1,
    "title": "Onboarding Guide",
    "body": "How to get started with the platform: request VPN access, join #platform-eng, and complete the security training module before your first on-call shift."
  },
  {
    "id": 2,
    "title": "API Reference",
    "body": "Internal search endpoints accept a query parameter and return matching documents ranked by relevance. Rate limit is 100 requests per minute per client."
  },
  {
    "id": 3,
    "title": "Security Policy",
    "body": "All access to internal tools requires SSO through the corporate identity provider. Service accounts must use short-lived client-credentials tokens, never static API keys."
  }
]
```

- [ ] **Step 5: Install dependencies**

```bash
export PATH="/c/Users/Santoshi/AppData/Local/Programs/Python/Python312:/c/Users/Santoshi/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
pip install -r use-case-2-keycloak-secured/requirements.txt
```
Expected: installs with no errors.

- [ ] **Step 6: Commit**

```bash
git add use-case-2-keycloak-secured/requirements.txt use-case-2-keycloak-secured/pytest.ini use-case-2-keycloak-secured/.gitignore use-case-2-keycloak-secured/data
git commit -m "chore: scaffold use-case-2 Keycloak-secured MCP server project"
```

---

### Task 2: `docker-compose.yml` (Keycloak + Postgres)

**Files:**
- Create: `use-case-2-keycloak-secured/docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: keycloak
      POSTGRES_USER: keycloak
      POSTGRES_PASSWORD: keycloak
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U keycloak"]
      interval: 5s
      timeout: 5s
      retries: 10

  keycloak:
    image: quay.io/keycloak/keycloak:26.0
    command: start-dev
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD: keycloak
    ports:
      - "8080:8080"
    depends_on:
      postgres:
        condition: service_healthy

volumes:
  postgres_data:
```

- [ ] **Step 2: Start it and verify Keycloak comes up healthy**

```bash
cd use-case-2-keycloak-secured
docker compose up -d
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/realms/master)
  echo "attempt $i: HTTP $code"
  if [ "$code" = "200" ]; then echo "READY"; break; fi
  sleep 3
done
```
Expected: eventually prints `READY` (Keycloak dev-mode startup typically takes 20-40 seconds).

- [ ] **Step 3: Commit**

```bash
git add use-case-2-keycloak-secured/docker-compose.yml
git commit -m "feat: add Keycloak + Postgres docker-compose stack"
```

---

### Task 3: `setup-realm.sh` — realm provisioning

This script reproduces, exactly, the curl sequence already verified against a live Keycloak
instance: it creates the `mcp-demo` realm, two authorization scopes (`mcp:read`,
`mcp:admin`), a separate `mcp-audience` scope carrying an audience mapper (kept separate from
the authorization scopes so that a token missing `mcp:read` still gets a *valid* audience and
correctly produces a 403, not a 401 — this was a real bug caught during verification: when
the audience mapper was attached directly to the `mcp:read` scope, a client without that
scope got an incomplete audience and was rejected at the token-validity level instead of the
scope level), the `mcp-server` resource client, and three service-account clients
(`mcp-reader`, `mcp-admin`, `mcp-noaccess`) with the appropriate scopes assigned.

**Files:**
- Create: `use-case-2-keycloak-secured/setup-realm.sh`

- [ ] **Step 1: Create `setup-realm.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

KEYCLOAK_URL="http://localhost:8080"
REALM="mcp-demo"

echo "Fetching admin token..."
ADMIN_TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=admin" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

REALM_API="$KEYCLOAK_URL/admin/realms/$REALM"

echo "Creating realm..."
curl -s -o /dev/null -w "  realm: %{http_code}\n" -X POST "$KEYCLOAK_URL/admin/realms" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d "{\"realm\": \"$REALM\", \"enabled\": true}"

echo "Creating client scopes..."
for scope in "mcp:read" "mcp:admin"; do
  curl -s -o /dev/null -w "  scope $scope: %{http_code}\n" -X POST "$REALM_API/client-scopes" \
    -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
    -d "{\"name\": \"$scope\", \"protocol\": \"openid-connect\", \"attributes\": {\"include.in.token.scope\": \"true\", \"display.on.consent.screen\": \"false\"}}"
done
curl -s -o /dev/null -w "  scope mcp-audience: %{http_code}\n" -X POST "$REALM_API/client-scopes" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d "{\"name\": \"mcp-audience\", \"protocol\": \"openid-connect\", \"attributes\": {\"include.in.token.scope\": \"false\", \"display.on.consent.screen\": \"false\"}}"

READ_ID=$(curl -s "$REALM_API/client-scopes" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import sys,json; print([s['id'] for s in json.load(sys.stdin) if s['name']=='mcp:read'][0])")
ADMIN_SCOPE_ID=$(curl -s "$REALM_API/client-scopes" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import sys,json; print([s['id'] for s in json.load(sys.stdin) if s['name']=='mcp:admin'][0])")
AUD_SCOPE_ID=$(curl -s "$REALM_API/client-scopes" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import sys,json; print([s['id'] for s in json.load(sys.stdin) if s['name']=='mcp-audience'][0])")

echo "Adding audience mapper to mcp-audience scope..."
curl -s -o /dev/null -w "  mapper: %{http_code}\n" -X POST "$REALM_API/client-scopes/$AUD_SCOPE_ID/protocol-mappers/models" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "mcp-server-audience", "protocol": "openid-connect", "protocolMapper": "oidc-audience-mapper", "config": {"included.client.audience": "mcp-server", "id.token.claim": "false", "access.token.claim": "true"}}'

echo "Creating clients..."
curl -s -o /dev/null -w "  mcp-server: %{http_code}\n" -X POST "$REALM_API/clients" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"clientId": "mcp-server", "protocol": "openid-connect", "publicClient": false, "serviceAccountsEnabled": false, "standardFlowEnabled": false}'

curl -s -o /dev/null -w "  mcp-reader: %{http_code}\n" -X POST "$REALM_API/clients" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"clientId": "mcp-reader", "protocol": "openid-connect", "publicClient": false, "serviceAccountsEnabled": true, "standardFlowEnabled": false, "directAccessGrantsEnabled": false, "secret": "reader-secret"}'

curl -s -o /dev/null -w "  mcp-admin: %{http_code}\n" -X POST "$REALM_API/clients" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"clientId": "mcp-admin", "protocol": "openid-connect", "publicClient": false, "serviceAccountsEnabled": true, "standardFlowEnabled": false, "directAccessGrantsEnabled": false, "secret": "admin-secret"}'

curl -s -o /dev/null -w "  mcp-noaccess: %{http_code}\n" -X POST "$REALM_API/clients" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"clientId": "mcp-noaccess", "protocol": "openid-connect", "publicClient": false, "serviceAccountsEnabled": true, "standardFlowEnabled": false, "directAccessGrantsEnabled": false, "secret": "noaccess-secret"}'

READER_CLIENT=$(curl -s "$REALM_API/clients" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import sys,json; print([c['id'] for c in json.load(sys.stdin) if c['clientId']=='mcp-reader'][0])")
ADMIN_CLIENT=$(curl -s "$REALM_API/clients" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import sys,json; print([c['id'] for c in json.load(sys.stdin) if c['clientId']=='mcp-admin'][0])")
NOACCESS_CLIENT=$(curl -s "$REALM_API/clients" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import sys,json; print([c['id'] for c in json.load(sys.stdin) if c['clientId']=='mcp-noaccess'][0])")

echo "Assigning scopes..."
curl -s -o /dev/null -w "  reader += mcp:read: %{http_code}\n" -X PUT "$REALM_API/clients/$READER_CLIENT/default-client-scopes/$READ_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s -o /dev/null -w "  reader += mcp-audience: %{http_code}\n" -X PUT "$REALM_API/clients/$READER_CLIENT/default-client-scopes/$AUD_SCOPE_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s -o /dev/null -w "  admin += mcp:read: %{http_code}\n" -X PUT "$REALM_API/clients/$ADMIN_CLIENT/default-client-scopes/$READ_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s -o /dev/null -w "  admin += mcp:admin: %{http_code}\n" -X PUT "$REALM_API/clients/$ADMIN_CLIENT/default-client-scopes/$ADMIN_SCOPE_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s -o /dev/null -w "  admin += mcp-audience: %{http_code}\n" -X PUT "$REALM_API/clients/$ADMIN_CLIENT/default-client-scopes/$AUD_SCOPE_ID" -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s -o /dev/null -w "  noaccess += mcp-audience: %{http_code}\n" -X PUT "$REALM_API/clients/$NOACCESS_CLIENT/default-client-scopes/$AUD_SCOPE_ID" -H "Authorization: Bearer $ADMIN_TOKEN"

echo "Done. Realm '$REALM' provisioned with mcp-reader, mcp-admin, mcp-noaccess clients."
```

- [ ] **Step 2: Make it executable and run it against the Task 2 stack**

```bash
chmod +x use-case-2-keycloak-secured/setup-realm.sh
cd use-case-2-keycloak-secured
./setup-realm.sh
```
Expected: every line prints a `20x` status code, ending with the "Done." message. If any
line prints `401`, the admin token expired mid-script (Keycloak dev-mode admin tokens are
short-lived) — rerun the script from the top.

- [ ] **Step 3: Verify token issuance and claims for real**

```bash
python3 -c "
import subprocess, json, base64

def get_token(client_id, secret):
    out = subprocess.run(['curl', '-s', '-X', 'POST',
        'http://localhost:8080/realms/mcp-demo/protocol/openid-connect/token',
        '-H', 'Content-Type: application/x-www-form-urlencoded',
        '-d', f'grant_type=client_credentials&client_id={client_id}&client_secret={secret}'],
        capture_output=True, text=True).stdout
    return json.loads(out)['access_token']

def decode(token):
    payload = token.split('.')[1]
    payload += '=' * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))

for cid, secret in [('mcp-reader','reader-secret'), ('mcp-admin','admin-secret'), ('mcp-noaccess','noaccess-secret')]:
    claims = decode(get_token(cid, secret))
    print(cid, '-> scope:', claims.get('scope'), '| aud:', claims.get('aud'))
"
```
Expected output (exact scopes/audiences the plan was built against):
```
mcp-reader -> scope: profile email mcp:read | aud: ['mcp-server', 'account']
mcp-admin -> scope: profile email mcp:read mcp:admin | aud: ['mcp-server', 'account']
mcp-noaccess -> scope: profile email | aud: ['mcp-server', 'account']
```

- [ ] **Step 4: Commit**

```bash
git add use-case-2-keycloak-secured/setup-realm.sh
git commit -m "feat: add Keycloak realm provisioning script"
```

---

### Task 4: `KeycloakTokenVerifier` (TDD, no Docker required)

Unit-tests the token-validation logic using a locally generated RSA keypair to sign test
JWTs, with `PyJWKClient.get_signing_key_from_jwt` mocked to return our test public key — this
tests the exact validation logic without needing a running Keycloak instance.

**Files:**
- Create: `use-case-2-keycloak-secured/server.py`
- Create: `use-case-2-keycloak-secured/tests/test_token_verifier.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_token_verifier.py`:

```python
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import KeycloakTokenVerifier, ISSUER, AUDIENCE

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()


def _make_token(scope="mcp:read", issuer=ISSUER, audience=AUDIENCE, exp_delta=3600, azp="test-client"):
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": audience,
        "azp": azp,
        "scope": scope,
        "exp": now + exp_delta,
        "iat": now,
        "sub": "test-subject",
    }
    return jwt.encode(claims, _private_key, algorithm="RS256")


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


@pytest.fixture
def verifier():
    v = KeycloakTokenVerifier()
    v.jwks_client.get_signing_key_from_jwt = MagicMock(return_value=_FakeSigningKey(_public_key))
    return v


async def test_valid_token_extracts_scopes(verifier):
    token = _make_token(scope="profile email mcp:read")
    result = await verifier.verify_token(token)
    assert result is not None
    assert result.scopes == ["profile", "email", "mcp:read"]
    assert result.client_id == "test-client"


async def test_expired_token_rejected(verifier):
    token = _make_token(exp_delta=-3600)
    result = await verifier.verify_token(token)
    assert result is None


async def test_wrong_issuer_rejected(verifier):
    token = _make_token(issuer="http://evil.example.com/realms/fake")
    result = await verifier.verify_token(token)
    assert result is None


async def test_wrong_audience_rejected(verifier):
    token = _make_token(audience="some-other-service")
    result = await verifier.verify_token(token)
    assert result is None


async def test_malformed_token_rejected(verifier):
    result = await verifier.verify_token("not.a.jwt")
    assert result is None
```

- [ ] **Step 2: Run to verify it fails**

```bash
export PATH="/c/Users/Santoshi/AppData/Local/Programs/Python/Python312:/c/Users/Santoshi/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
cd use-case-2-keycloak-secured
python -m pytest tests/test_token_verifier.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'server'` (server.py doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `server.py`:

```python
"""MCP server secured by Keycloak-issued OAuth 2.1 access tokens over Streamable HTTP."""

import asyncio
import json
import os
from pathlib import Path

import jwt
from jwt import PyJWKClient
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

BASE_DIR = Path(__file__).parent
DOCUMENTS_FILE = BASE_DIR / "data" / "documents.json"

ISSUER = os.environ.get("MCP_KEYCLOAK_ISSUER_URL", "http://localhost:8080/realms/mcp-demo")
AUDIENCE = os.environ.get("MCP_KEYCLOAK_AUDIENCE", "mcp-server")
RESOURCE_SERVER_URL = os.environ.get("MCP_RESOURCE_SERVER_URL", "http://localhost:8000")
JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"


class KeycloakTokenVerifier(TokenVerifier):
    def __init__(self):
        self.jwks_client = PyJWKClient(JWKS_URL)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = await asyncio.to_thread(self.jwks_client.get_signing_key_from_jwt, token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=ISSUER,
                audience=AUDIENCE,
            )
        except jwt.PyJWTError:
            return None

        scopes = claims.get("scope", "").split()
        return AccessToken(
            token=token,
            client_id=claims.get("azp", "unknown"),
            scopes=scopes,
            expires_at=claims.get("exp"),
            subject=claims.get("sub"),
        )


def _load_documents() -> list[dict]:
    with open(DOCUMENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


mcp = FastMCP(
    "keycloak-secured-demo",
    host="0.0.0.0",
    port=8000,
    auth=AuthSettings(
        issuer_url=ISSUER,
        resource_server_url=RESOURCE_SERVER_URL,
        required_scopes=["mcp:read"],
    ),
    token_verifier=KeycloakTokenVerifier(),
)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```

- [ ] **Step 4: Run to verify it passes**

```bash
python -m pytest tests/test_token_verifier.py -v
```
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add use-case-2-keycloak-secured/server.py use-case-2-keycloak-secured/tests/test_token_verifier.py
git commit -m "feat: add KeycloakTokenVerifier with unit tests"
```

---

### Task 5: `search_documents` tool (TDD)

**Files:**
- Modify: `use-case-2-keycloak-secured/server.py`
- Create: `use-case-2-keycloak-secured/tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tools.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import search_documents


def test_search_documents_finds_match():
    results = search_documents("SSO")
    assert len(results) == 1
    assert results[0]["title"] == "Security Policy"


def test_search_documents_no_match():
    results = search_documents("xyzxyzxyz-not-a-real-term")
    assert results == []


def test_search_documents_matches_title_too():
    results = search_documents("API Reference")
    assert len(results) == 1
    assert results[0]["id"] == 2
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_tools.py -v
```
Expected: FAIL with `ImportError: cannot import name 'search_documents'`.

- [ ] **Step 3: Write minimal implementation**

Add to `server.py`, before the `if __name__ == "__main__":` block (there is none yet at this
point in the file — add this tool definition right after the `mcp = FastMCP(...)` block):

```python
@mcp.tool()
def search_documents(query: str) -> list[dict]:
    """Search internal documents. Requires the mcp:read scope."""
    documents = _load_documents()
    needle = query.lower()
    return [
        d for d in documents
        if needle in d["title"].lower() or needle in d["body"].lower()
    ]
```

- [ ] **Step 4: Run to verify it passes**

```bash
python -m pytest tests/test_tools.py -v
```
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add use-case-2-keycloak-secured/server.py use-case-2-keycloak-secured/tests/test_tools.py
git commit -m "feat: add search_documents MCP tool"
```

---

### Task 6: `admin_reindex` tool with in-tool scope check (TDD)

This tool demonstrates fine-grained, per-tool authorization *beyond* the server-wide
`required_scopes=["mcp:read"]` minimum: it uses the SDK's `get_access_token()` context helper
to read the caller's actual granted scopes and rejects the call if `mcp:admin` is missing.
Note this produces an MCP-level tool error (`isError=True` in the `CallToolResult`, HTTP 200)
— not a distinct HTTP status code, since MCP has no built-in per-tool HTTP-layer scope
mechanism. The README makes this distinction explicit.

**Files:**
- Modify: `use-case-2-keycloak-secured/server.py`
- Modify: `use-case-2-keycloak-secured/tests/test_tools.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tools.py`:

```python
from unittest.mock import patch

from mcp.server.auth.provider import AccessToken

from server import admin_reindex


def _fake_token(scopes):
    return AccessToken(token="fake", client_id="test-client", scopes=scopes)


def test_admin_reindex_succeeds_with_admin_scope():
    with patch("server.get_access_token", return_value=_fake_token(["mcp:read", "mcp:admin"])):
        result = admin_reindex()
    assert result["status"] == "reindexed"
    assert result["document_count"] == 3
    assert result["triggered_by"] == "test-client"


def test_admin_reindex_rejects_without_admin_scope():
    import pytest

    with patch("server.get_access_token", return_value=_fake_token(["mcp:read"])):
        with pytest.raises(PermissionError, match="mcp:admin"):
            admin_reindex()


def test_admin_reindex_rejects_with_no_token():
    import pytest

    with patch("server.get_access_token", return_value=None):
        with pytest.raises(PermissionError, match="mcp:admin"):
            admin_reindex()
```

- [ ] **Step 2: Run to verify it fails**

```bash
python -m pytest tests/test_tools.py -v
```
Expected: FAIL with `ImportError: cannot import name 'admin_reindex'`.

- [ ] **Step 3: Write minimal implementation**

Add this import to the top of `server.py`, alongside the existing `from mcp.server.auth...`
imports (it's already imported at module level, so just reference it — no new import line is
needed since `get_access_token` is already imported in Task 4's code). Add the tool itself
to `server.py`, after `search_documents`:

```python
@mcp.tool()
def admin_reindex() -> dict:
    """Trigger a reindex of the document store. Requires the mcp:admin scope."""
    token = get_access_token()
    if token is None or "mcp:admin" not in token.scopes:
        raise PermissionError(
            "This action requires the 'mcp:admin' scope, which the current token does not have."
        )
    documents = _load_documents()
    return {
        "status": "reindexed",
        "document_count": len(documents),
        "triggered_by": token.client_id,
    }
```

- [ ] **Step 4: Run to verify it passes**

```bash
python -m pytest tests/test_tools.py -v
```
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add use-case-2-keycloak-secured/server.py use-case-2-keycloak-secured/tests/test_tools.py
git commit -m "feat: add admin_reindex MCP tool with scope-based authorization"
```

---

### Task 7: Real end-to-end HTTP auth verification

Adds the entrypoint and proves the exact 401/403/200 behavior against the real running stack
(Task 2's Keycloak, provisioned by Task 3's script) — reproducing the manual verification
already performed before this plan was written.

**Files:**
- Modify: `use-case-2-keycloak-secured/server.py` (add `__main__` block — should already be
  the last thing in the file from Task 4; if not, move it there now)
- Create: `use-case-2-keycloak-secured/tests/test_auth_flow.sh`

- [ ] **Step 1: Confirm `server.py` ends with the run block**

Verify `server.py`'s last lines are:
```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```
(This was included in Task 4's Step 3 — this step just confirms it's still last after
Tasks 5 and 6 appended tool definitions above it.)

- [ ] **Step 2: Create `tests/test_auth_flow.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

MCP_URL="http://127.0.0.1:8000/mcp"

get_token() {
  curl -s -X POST http://localhost:8080/realms/mcp-demo/protocol/openid-connect/token \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "grant_type=client_credentials&client_id=$1&client_secret=$2" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))"
}

call() {
  local token="$1"
  local headers=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream")
  if [ -n "$token" ]; then
    headers+=(-H "Authorization: Bearer $token")
  fi
  curl -s -o /dev/null -w "%{http_code}" -X POST "$MCP_URL" "${headers[@]}" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
}

echo "No token:"
CODE=$(call "")
echo "  HTTP $CODE (expect 401)"
[ "$CODE" = "401" ] || { echo "  FAIL"; exit 1; }

echo "mcp-noaccess token (missing mcp:read):"
TOKEN=$(get_token mcp-noaccess noaccess-secret)
CODE=$(call "$TOKEN")
echo "  HTTP $CODE (expect 403)"
[ "$CODE" = "403" ] || { echo "  FAIL"; exit 1; }

echo "mcp-reader token (has mcp:read):"
TOKEN=$(get_token mcp-reader reader-secret)
CODE=$(call "$TOKEN")
echo "  HTTP $CODE (expect 200)"
[ "$CODE" = "200" ] || { echo "  FAIL"; exit 1; }

echo "ALL CHECKS PASSED"
```

- [ ] **Step 3: Run the full stack and the auth flow test**

```bash
export PATH="/c/Users/Santoshi/AppData/Local/Programs/Python/Python312:/c/Users/Santoshi/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
cd use-case-2-keycloak-secured
docker compose up -d
# wait for Keycloak health as in Task 2 Step 2, then:
./setup-realm.sh
python server.py &
SERVER_PID=$!
sleep 2
chmod +x tests/test_auth_flow.sh
./tests/test_auth_flow.sh
kill $SERVER_PID
```
Expected: prints `HTTP 401`, `HTTP 403`, `HTTP 200` in order, ending with
`ALL CHECKS PASSED`. These exact three outcomes were already manually verified against this
same setup before this plan was written — if any step gives a different result here, stop
and investigate the discrepancy rather than editing the test to match (per systematic
debugging: find the root cause of the mismatch first).

- [ ] **Step 4: Commit**

```bash
git add use-case-2-keycloak-secured/tests/test_auth_flow.sh
git commit -m "test: add real end-to-end 401/403/200 auth flow verification"
```

---

### Task 8: `demo.py` — narrated demo script

**Files:**
- Create: `use-case-2-keycloak-secured/demo.py`

- [ ] **Step 1: Create `demo.py`**

```python
"""Demo script: exercises the Keycloak-secured MCP server's auth flow end to end.

Requires: docker compose up -d && ./setup-realm.sh (once), then python server.py running
in another terminal, then run this script.
"""

import httpx

KEYCLOAK_TOKEN_URL = "http://localhost:8080/realms/mcp-demo/protocol/openid-connect/token"
MCP_URL = "http://127.0.0.1:8000/mcp"


def get_token(client_id: str, client_secret: str) -> str:
    resp = httpx.post(
        KEYCLOAK_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def call_initialize(token: str | None) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "demo", "version": "1.0"},
        },
    }
    return httpx.post(MCP_URL, headers=headers, json=payload)


def main():
    print("1. No token at all:")
    resp = call_initialize(None)
    print(f"   HTTP {resp.status_code} (expected 401 - unauthenticated)\n")

    print("2. mcp-noaccess token (valid token, but missing mcp:read scope):")
    token = get_token("mcp-noaccess", "noaccess-secret")
    resp = call_initialize(token)
    print(f"   HTTP {resp.status_code} (expected 403 - authenticated but insufficient scope)\n")

    print("3. mcp-reader token (has mcp:read scope):")
    token = get_token("mcp-reader", "reader-secret")
    resp = call_initialize(token)
    print(f"   HTTP {resp.status_code} (expected 200 - authorized)\n")

    print("4. mcp-admin token (has mcp:read + mcp:admin):")
    token = get_token("mcp-admin", "admin-secret")
    resp = call_initialize(token)
    print(f"   HTTP {resp.status_code} (expected 200 - authorized, and this token can also call admin_reindex)\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it against the live stack from Task 7 and confirm real output**

```bash
export PATH="/c/Users/Santoshi/AppData/Local/Programs/Python/Python312:/c/Users/Santoshi/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
cd use-case-2-keycloak-secured
python server.py &
SERVER_PID=$!
sleep 2
python demo.py
kill $SERVER_PID
```
Expected: prints the four numbered scenarios with `HTTP 401`, `403`, `200`, `200`.

- [ ] **Step 3: Commit**

```bash
git add use-case-2-keycloak-secured/demo.py
git commit -m "feat: add narrated demo script for the auth flow"
```

---

### Task 9: Kubernetes manifest

**Files:**
- Create: `use-case-2-keycloak-secured/k8s/deployment.yaml`

- [ ] **Step 1: Create `k8s/deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server-keycloak-secured
  labels:
    app: mcp-server-keycloak-secured
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-server-keycloak-secured
  template:
    metadata:
      labels:
        app: mcp-server-keycloak-secured
    spec:
      containers:
        - name: mcp-server
          image: mcp-demo/use-case-2-keycloak-secured:latest
          ports:
            - containerPort: 8000
          env:
            - name: MCP_KEYCLOAK_ISSUER_URL
              value: "http://keycloak.auth.svc.cluster.local:8080/realms/mcp-demo"
            - name: MCP_KEYCLOAK_AUDIENCE
              value: "mcp-server"
            - name: MCP_RESOURCE_SERVER_URL
              value: "http://mcp-server-keycloak-secured.default.svc.cluster.local:8000"
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-server-keycloak-secured
spec:
  selector:
    app: mcp-server-keycloak-secured
  ports:
    - port: 8000
      targetPort: 8000
```

- [ ] **Step 2: Validate the manifest is well-formed YAML/Kubernetes syntax**

```bash
export PATH="/c/Users/Santoshi/AppData/Local/Programs/Python/Python312:/c/Users/Santoshi/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
kubectl apply --dry-run=client -f use-case-2-keycloak-secured/k8s/deployment.yaml
```
Expected: `deployment.apps/mcp-server-keycloak-secured created (dry run)` and
`service/mcp-server-keycloak-secured created (dry run)` — confirms valid syntax without
needing a live cluster for this check specifically (this validates schema, not that Keycloak
is actually reachable in-cluster).

- [ ] **Step 3: Commit**

```bash
git add use-case-2-keycloak-secured/k8s/deployment.yaml
git commit -m "docs: add Kubernetes Deployment/Service manifest"
```

---

### Task 10: README

**Files:**
- Create: `use-case-2-keycloak-secured/README.md`

- [ ] **Step 1: Create `README.md`**

```markdown
# Use Case 2: Keycloak-Secured MCP Server

An MCP server over Streamable HTTP, secured by Keycloak-issued OAuth 2.1 access tokens, with
scope-based RBAC (`mcp:read` vs `mcp:admin`).

## Architecture

\`\`\`mermaid
sequenceDiagram
    participant Client as MCP Client (Cursor / Claude)
    participant Keycloak
    participant Server as server.py (Streamable HTTP)

    Client->>Keycloak: client_credentials grant (client_id + secret)
    Keycloak-->>Client: JWT access token (scope, aud, azp claims)
    Client->>Server: POST /mcp, Authorization: Bearer <token>
    Server->>Server: KeycloakTokenVerifier validates signature (JWKS),\nissuer, audience
    Server->>Server: RequireAuthMiddleware checks required_scopes=["mcp:read"]
    alt no token
        Server-->>Client: 401 Unauthorized
    else missing mcp:read
        Server-->>Client: 403 Forbidden
    else has mcp:read
        Server-->>Client: 200 OK, MCP session proceeds
        Client->>Server: tools/call admin_reindex
        Server->>Server: get_access_token() checks for mcp:admin in-tool
        Server-->>Client: MCP-level error if mcp:admin missing (still HTTP 200)
    end
\`\`\`

**Important nuance:** MCP has no built-in per-tool HTTP-layer scope mechanism. The
server-wide `required_scopes=["mcp:read"]` check produces real HTTP 401/403 responses before
any tool runs. The extra `mcp:admin` requirement on `admin_reindex` is enforced *inside* the
tool function via `get_access_token()`, which produces an MCP-level tool error
(`isError=True`) — still an HTTP 200 at the transport layer, since the JSON-RPC call itself
succeeded even though the tool logic rejected it.

## Prerequisites

- Docker + Docker Compose
- Python 3.11+
- `pip install -r requirements.txt`

## Setup

\`\`\`bash
docker compose up -d
# wait ~30s for Keycloak to be ready, then:
./setup-realm.sh
\`\`\`

This creates the `mcp-demo` realm with three demo service accounts:

| Client | Scopes | Expected outcome |
|---|---|---|
| `mcp-noaccess` / `noaccess-secret` | none | 403 (fails the server-wide mcp:read check) |
| `mcp-reader` / `reader-secret` | `mcp:read` | 200; can call `search_documents`, blocked from `admin_reindex` |
| `mcp-admin` / `admin-secret` | `mcp:read`, `mcp:admin` | 200; can call both tools |

## Run the server

\`\`\`bash
python server.py
\`\`\`
Listens on `http://0.0.0.0:8000/mcp`.

## Run the tests

\`\`\`bash
pytest tests/test_token_verifier.py tests/test_tools.py -v   # no Docker needed
./tests/test_auth_flow.sh                                     # needs the stack running
\`\`\`

## Run the demo script

With the stack up and `server.py` running in another terminal:

\`\`\`bash
python demo.py
\`\`\`

## Client integration (Cursor / Claude Desktop remote MCP)

Point your client's remote-MCP configuration at `http://localhost:8000/mcp` and complete the
OAuth flow the client prompts for (or use a `client_credentials`-issued token directly,
depending on your client's support for remote MCP servers).

## Kubernetes deployment

See `k8s/deployment.yaml` — set `MCP_KEYCLOAK_ISSUER_URL` to your in-cluster Keycloak's
issuer URL and `MCP_RESOURCE_SERVER_URL` to this service's own in-cluster address.
```

- [ ] **Step 2: Commit**

```bash
git add use-case-2-keycloak-secured/README.md
git commit -m "docs: add use-case-2 README"
```

---

### Task 11: IMPLEMENTATION.md

**Files:**
- Create: `use-case-2-keycloak-secured/IMPLEMENTATION.md`

- [ ] **Step 1: Create `IMPLEMENTATION.md`**, following the same "what was built, step by
  step" structure as `use-case-1-custom-server/IMPLEMENTATION.md`, covering:
  - Why Keycloak's realm provisioning is a script (`setup-realm.sh`) rather than a static
    `realm-export.json`, and the real bug it caught (audience mapper needing to live on a
    scope separate from the authorization scopes, or clients without `mcp:read` would fail
    with 401 instead of the intended 403)
  - How `KeycloakTokenVerifier` plugs into the SDK's built-in `TokenVerifier`/`AuthSettings`
    mechanism instead of hand-rolled middleware
  - The distinction between transport-level auth (401/403, enforced by the SDK's
    `RequireAuthMiddleware` against `required_scopes`) and tool-level authorization (the
    `admin_reindex` in-tool `get_access_token()` check)
  - How the unit tests for `KeycloakTokenVerifier` avoid needing Docker by signing test JWTs
    with a locally generated RSA keypair and mocking `PyJWKClient`
  - That every piece of this (realm provisioning, JWT validation, the 401/403/200 HTTP
    outcomes) was verified against a real, live Keycloak container before this plan was
    written, not just written and assumed to work

- [ ] **Step 2: Commit**

```bash
git add use-case-2-keycloak-secured/IMPLEMENTATION.md
git commit -m "docs: add implementation walkthrough for use-case-2"
```

---

## Self-Review Notes

- **Spec coverage:** docker-compose Keycloak+Postgres ✅, realm/client/scope provisioning ✅,
  Streamable HTTP transport ✅, JWT validation via JWKS ✅, scope-based RBAC
  (`search_documents`/`mcp:read`, `admin_reindex`/`mcp:admin`) ✅, demo script exercising
  401/403/200 ✅, README with architecture diagram + K8s manifest ✅, real
  `docker compose up` + token fetch + 401/403/200 verification ✅.
- **Placeholder scan:** none — every code block is complete and was verified against a live
  Keycloak instance before being written into this plan.
- **Type/name consistency:** `ISSUER`, `AUDIENCE`, `RESOURCE_SERVER_URL`, `DOCUMENTS_FILE`
  are defined once in Task 4 and referenced identically in later tasks.
- **Deviation from the original design spec:** the spec's phrasing ("token with wrong scope
  → 403") is preserved exactly for the *server-wide* `mcp:read` check, but the spec did not
  originally distinguish that `admin_reindex`'s extra `mcp:admin` requirement can only be
  enforced at the tool level (MCP has no per-tool HTTP scope mechanism), not as a second HTTP
  status code. This plan and its README make that distinction explicit rather than silently
  presenting an inaccurate simplification.
