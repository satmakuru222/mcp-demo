# MCP + Keycloak Production-Grade Demo — Design Spec

**Date:** 2026-07-24
**Status:** Approved
**Owner:** Santoshi Atmakuru (The AI Stackk)

## Purpose

Produce a realistic, runnable teaching demo on the Model Context Protocol (MCP) that any
engineer can follow, covering: MCP fundamentals, building a custom MCP server, using
Keycloak to secure an MCP server, the different types of MCP servers, integrating MCP into
common clients (Claude, Cursor, Gemini, Codex), Kubernetes deployment, top enterprise use
cases, security best practices, and pros/cons/when-to-use guidance. Intended as source
material for The AI Stackk's course/video content, and as a reference the audience can clone
and run locally.

## Location

New, self-contained top-level folder, independent of the existing `rag-demo/` work on this
branch:

```
mcp-demos/
├── GUIDE.md
├── use-case-1-custom-server/
├── use-case-2-keycloak-secured/
├── use-case-3-ldap-wildfly-bridge/
└── use-case-4-odh-model-serving/
```

Rationale: keeps this teaching artifact decoupled from the production RAG platform's setup
complexity (SSO, Drive ingestion, audit logs), so it stays fast to run and easy to reproduce
for an external audience.

**Note on scope growth:** this spec was expanded after initial approval, at the requester's
direction, to cover a broader enterprise open-source landscape (LDAP, WildFly, Open Data
Hub/RHOAI) beyond the original two use cases.

## 1. GUIDE.md — conceptual reference

Single markdown file, diagrams in richly-styled Mermaid (colored nodes, grouped subgraphs,
clear labeling — not bare boxes-and-arrows), so it renders natively on GitHub and most
viewers with no extra tooling. Sections, in order:

1. **What is MCP** — one mental model: Host (Claude/Cursor) → MCP Client → MCP Server →
   Tools/Resources, over JSON-RPC. One Mermaid sequence diagram showing a single tool-call
   round trip end to end.
2. **Core primitives** — Tools, Resources, Prompts, Sampling, presented as a short
   comparison table (not prose).
3. **Transports** — stdio (local process) vs. Streamable HTTP (remote/enterprise), and when
   each applies. This sets up why use-case-1 is stdio and use-case-2 is HTTP + auth.
4. **Types of MCP servers** — local dev servers, remote hosted servers, gateway/proxy
   servers, auth-fronted enterprise servers — one real-world-flavored example each.
5. **Client integration** — config snippets for Claude Code, Claude Desktop, and Cursor
   (all three actually tested against the stdio- and HTTP-based demos in this repo), plus
   documented (untested in this session) config for Gemini CLI and Codex CLI.
6. **Kubernetes deployment pattern** — a Deployment/Service manifest for an MCP server pod,
   showing where Keycloak fits as an external auth dependency.
7. **Enterprise use cases** — presented as categories with realistic framing, not
   unverifiable company-specific claims: internal knowledge search, DevOps/Kubernetes
   copilot, ITSM/ticketing automation, database query assistants, CI/CD control, SOC/security
   tooling.
8. **Securing MCP** — maps directly to what use-case-2 demonstrates: OAuth 2.1/OIDC per the
   MCP authorization spec, token audience/issuer validation, scope-based RBAC, no secrets in
   prompts, tool allow-listing, output validation against prompt injection via tool results,
   rate limiting, audit logging.
9. **Enterprise architecture patterns** — two patterns, both actually built and run in this
   project (not diagram-only):
   - *LDAP-federated identity + legacy Java EE app* — use-case-3: Keycloak federates users
     from a real OpenLDAP directory instead of its own DB; a legacy-style WildFly app is
     fronted by an MCP server. This is the standard "AD/LDAP as source of truth, Keycloak as
     the OIDC broker" pattern used across large enterprises.
   - *AI/ML platform model serving (RHOAI / Open Data Hub)* — use-case-4, using **Open Data
     Hub (ODH)**, the open-source upstream project Red Hat OpenShift AI (RHOAI) is built
     from, running on the machine's existing OpenShift Local (CRC) cluster. The guide states
     plainly that RHOAI itself is Red Hat's entitlement-gated, supported distribution of the
     same components (KServe-based model serving), so this demo proves the identical
     integration pattern — an MCP tool calling a `KServe InferenceService` — without
     depending on subscription state we can't verify.
10. **Pros/cons and when to use MCP** vs. plain function-calling/custom plugins.

### 1a. Companion visual page (Artifact)

A separate `mcp-demos/GUIDE.html` (or hosted as a Claude Artifact) covering the same
concepts as GUIDE.md's diagram-bearing sections (MCP mental model, primitives, transports,
types of servers, the four use-case architectures, security layers) as custom-designed SVG
diagrams rather than Mermaid — higher visual fidelity, meant to be screen-recorded for
course/video production rather than read as reference docs. GUIDE.md links to it; it is not
a substitute for GUIDE.md, which remains the authoritative, plain-markdown reference that
works with no browser.

## 2. use-case-1-custom-server/ — build your own MCP server

- **Stack:** Python, official `mcp` SDK (FastMCP-style), stdio transport.
- **Tools exposed** (offline/mock — no external API keys required):
  - `get_deployment_status(service)` — mock internal deployment/CI status lookup
  - `search_knowledge_base(query)` — searches a small local doc corpus
  - `create_support_ticket(title, description)` — writes to a local JSON file (demonstrates
    a write/side-effect tool)
- **README:** prereqs (Python 3.11+), architecture diagram, code walkthrough, a
  `claude_desktop_config.json` snippet, a `.cursor/mcp.json` snippet, sample prompts to try.
- **Verification:** a small test client script using the MCP SDK calls each tool directly
  and asserts expected output, proving the server works without a GUI client open. The
  README then shows how to plug the same server into Cursor/Claude Desktop for a live run.

## 3. use-case-2-keycloak-secured/ — Keycloak as the auth layer for MCP

- **Stack:** `docker-compose.yml` with Keycloak + Postgres, pre-seeded via a realm-export
  JSON (realm `mcp-demo`, a confidential client, a demo user, scopes `mcp:read` /
  `mcp:admin`), so it comes up ready. README also documents the manual console steps for
  understanding.
- **Server:** Python MCP server over Streamable HTTP, with middleware that validates the
  incoming Bearer JWT against Keycloak's JWKS endpoint (issuer + audience check), then
  enforces scopes per tool:
  - `search_documents(query)` — requires `mcp:read`
  - `admin_reindex()` — requires `mcp:admin` (demonstrates scope-based RBAC — different
    clients/users get different access)
- **Dataset:** small in-memory toy document set (not the production rag-demo app) — the
  lesson is "how Keycloak secures MCP," not "how RAG works."
- **Demo script:** exercises the full arc — no token → 401, token with wrong scope → 403,
  valid token + correct scope → 200 — plus a client-credentials token-fetch example.
- **README:** architecture diagram, prereqs (Docker), `docker compose up` instructions, how
  to point Cursor/Claude Desktop's remote-MCP config at it, and a Kubernetes
  Deployment/Service manifest showing how this pattern deploys in-cluster.
- **Verification:** actually run `docker compose up`, fetch a real token from Keycloak, and
  exercise all three auth outcomes (401/403/200) so the demo is proven working, not just
  documented.

## 4. use-case-3-ldap-wildfly-bridge/ — LDAP identity federation + legacy Java EE bridge

- **Stack:** `docker-compose.yml` with OpenLDAP (seeded via LDIF with an org unit, a handful
  of users and groups), Keycloak (configured with an LDAP User Federation provider pointing
  at the OpenLDAP instance — Keycloak's DB no longer holds the users, LDAP is the source of
  truth), and WildFly running a minimal legacy-style Java EE app (a JAX-RS endpoint such as
  `GET /employees/{id}`, backed by an in-memory/H2 dataset — not a real corporate app).
- **MCP server:** Python, Streamable HTTP, the same JWT-validation middleware pattern as
  use-case-2. Exposes `lookup_employee(id)`, which calls the WildFly app's REST endpoint.
  Auth still flows through Keycloak, but the identity now genuinely originates from LDAP —
  demonstrating "MCP fronting a legacy enterprise Java app, with identity coming from a real
  directory service," a very common real-world enterprise topology.
- **README:** architecture diagram (LDAP → Keycloak federation → MCP server → WildFly app),
  prereqs (Docker), `docker compose up`, how to inspect the federated users in Keycloak's
  admin console, how to point Cursor/Claude Desktop at the MCP server.
- **Verification:** run `docker compose up`, confirm Keycloak pulls the seeded LDAP users
  (via its admin REST API or console), fetch a token, and call `lookup_employee` end to end.

## 5. use-case-4-odh-model-serving/ — MCP + Open Data Hub (RHOAI pattern) on OpenShift

- **Cluster:** the machine's existing CRC (OpenShift Local) installation — started for this
  demo, not left running afterward.
- **Platform:** Open Data Hub (ODH) operator installed via OperatorHub — the open-source
  upstream of Red Hat OpenShift AI (RHOAI). A small pre-trained model (e.g. a scikit-learn
  or lightweight HF text-classification model) is deployed as a `KServe InferenceService`
  (RawDeployment mode, to avoid also standing up Knative/Service Mesh).
- **MCP server:** Python, exposes a tool (e.g. `classify(text)` or `predict(features)`) that
  calls the InferenceService's REST predict endpoint from inside/outside the cluster.
- **README:** architecture diagram (Cursor/Claude → MCP server → KServe InferenceService →
  ODH/RHOAI serving runtime), prereqs (CRC, a registered Red Hat pull secret, `oc`/`kubectl`),
  step-by-step from `crc start` through model deployment through the MCP tool call, and an
  explicit callout: "this project installed ODH (free, open-source); RHOAI is Red Hat's
  supported distribution of the same components — the MCP integration pattern shown here is
  identical for both."
- **Verification:** start CRC, install the ODH operator, deploy the InferenceService, and
  call it through the MCP tool end to end in this session, then document teardown
  (`crc stop`) so the demo doesn't leave a large cluster running unnecessarily.

## Error handling

- Use-case 1: MCP SDK schema validation surfaces bad tool arguments as structured tool
  errors.
- Use-case 2: expired/invalid token → 401 with a clear message; wrong scope → 403; Keycloak
  unreachable at server startup → clear log instructing the user to run
  `docker compose up` first.
- Use-case 3: same 401/403 pattern as use-case 2; if Keycloak's LDAP federation sync fails
  (e.g. OpenLDAP not yet ready), Keycloak logs a clear federation error and the README notes
  the expected startup ordering/retry.
- Use-case 4: MCP tool call surfaces a clear error if the InferenceService isn't yet ready
  (KServe returns 503 during model load) or if CRC/the cluster isn't reachable, rather than a
  raw connection-refused traceback.

## Testing

- Use-case 1: a pytest/script-based test that starts the server over stdio, calls each tool
  through the MCP client SDK, and asserts expected output.
- Use-case 2: a script that waits for Keycloak health, fetches a real token, and asserts the
  401/403/200 behaviors against the running server.
- Use-case 3: a script that waits for OpenLDAP + Keycloak health, confirms the federated
  users are visible in Keycloak, fetches a token, and calls `lookup_employee` end to end.
- Use-case 4: a script/checklist that waits for the InferenceService to report Ready, then
  calls the MCP tool and asserts a valid prediction response.

## Out of scope

- No integration with the existing `rag-demo/` production app.
- No automated testing/verification of Gemini CLI or Codex CLI integration in this session
  (config is documented, not executed).
- No CI pipeline for this demo folder — it's a teaching artifact, not shipped software.
- No installation or testing of actual Red Hat OpenShift AI (RHOAI) — Open Data Hub (ODH) is
  used as its open-source, entitlement-free equivalent; the guide states this explicitly.
- No Oracle PeopleSoft/Unifier/WebLogic ERP use case — dropped from scope entirely (was
  previously planned as diagram-only; removed per requester's direction).
- CRC/OpenShift is started only for the duration of building and verifying use-case-4, then
  stopped — it is not left running as part of this project's steady state.
