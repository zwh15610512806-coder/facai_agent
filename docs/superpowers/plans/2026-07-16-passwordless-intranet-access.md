# Passwordless Intranet Access Implementation Plan

> **For Codex:** Execute this plan task by task with red-green-refactor discipline and fresh verification evidence.

**Goal:** Remove every application, integration-center, and Canvas password/token login while retaining non-login security controls and replacing purge password re-entry with an explicit confirmation phrase.

**Architecture:** Requests receive a fixed trusted-intranet actor for rate limiting and audit ownership, but no credential is read or validated. Integration mutations use a local integration actor digest rather than an administrator session. Canvas paid operations use the same open intranet boundary as the rest of the application. Host/Origin validation, request IDs, rate limits, audit writes, credential encryption, and dangerous-action confirmation remain independent controls.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy, Jinja2, TypeScript, Vite, Vitest, Playwright, Python unittest.

---

## Task 1: Pin the passwordless application contract

**Files:**
- Create: `tests/test_passwordless_access.py`
- Modify: `tests/test_security_hardening.py`
- Modify: `tests/test_operations_routes.py`

1. Add tests proving `/app`, a representative business API, and an audited/rate-limited mutation proceed without authentication environment variables, cookies, or headers.
2. Add tests proving `/app/login` redirects to `/app` and the old `/api/auth/login` route is absent.
3. Preserve and run Host, Origin, cross-site, body-limit, security-header, request-ID, rate-limit, and audit tests.
4. Run the new tests and confirm they fail for the expected authentication behavior.
5. Refactor `main.py` and `services/security.py` to use a fixed local actor and remove role-token/session/CSRF-login branches.
6. Remove `routers/auth.py`, `templates/login.html`, `scripts/bootstrap_auth.py`, and their obsolete tests; remove imports and startup assertions from service launchers.
7. Re-run the targeted tests until green.

## Task 2: Remove the integration-center login boundary

**Files:**
- Create: `integrations/actor.py`
- Create: `integrations/request_context.py`
- Modify: `routers/integrations.py`
- Modify: `integrations/settings.py`
- Modify: `integrations/schemas.py`
- Modify: `main.py`
- Modify: `tests/test_integration_pages.py`
- Modify: integration API/OAuth tests that currently install session cookies
- Delete: `templates/api_connections_login.html`
- Delete: `static/js/api-connections-login.js`
- Delete or reduce: `integrations/admin_auth.py`

1. Rewrite page tests to require direct `200` access to `/app/api-connections` and a redirect from the legacy login URL.
2. Add API tests proving integration administrative endpoints work without a session cookie.
3. Run the focused tests and confirm they fail because the current login session is required.
4. Introduce a non-secret local integration actor/digest for audit attribution and replace `AdminSessionClaims`/`require_integration_admin` dependencies.
5. Move forwarded-request context parsing needed by Origin handling into a password-neutral module.
6. Remove login/session/logout routes, schemas, settings fields, UI assets, login audit paths, and password/session environment requirements.
7. Make integration credential readiness depend only on credential, URL, archive, worker, and database configuration.
8. Re-run integration page, settings, app-config, OAuth, management, public-boundary, and feature-acceptance tests until green.

## Task 3: Replace purge password re-entry with confirmation-only validation

**Files:**
- Modify: `integrations/schemas.py`
- Modify: `routers/integrations.py`
- Modify: `static/js/api-connections.js`
- Modify: `tests/test_integration_management_api.py`
- Modify: `tests/test_integration_audit.py`

1. Add/adjust tests proving the purge schema rejects a `password` field, requires `confirmation`, and accepts the exact connection display name.
2. Add endpoint tests proving password verification is never called and a mismatched confirmation remains rejected and audited.
3. Run the focused tests and confirm failure against the current password field/check.
4. Remove the password field/check and retain display-name confirmation plus irreversible-action UI copy.
5. Remove `password_invalid` audit semantics from active production/frontend code.
6. Re-run focused management and audit tests until green.

## Task 4: Remove Canvas access-token gates

**Files:**
- Modify: `routers/canvas/__init__.py`
- Modify: `routers/canvas/exports.py`
- Modify: `routers/canvas/generations.py`
- Modify: `routers/canvas/providers.py`
- Modify: `frontend/canvas/src/api/generations.ts`
- Modify: `frontend/canvas/src/components/workspace.ts`
- Modify: `frontend/canvas/src/admin.ts`
- Modify: relevant Vitest tests
- Modify: `config.py`
- Modify: `scripts/e2e_server.py`
- Delete: `routers/canvas/access.py`
- Delete: `services/canvas/access.py`
- Delete: `frontend/canvas/src/components/access-dialog.ts`
- Replace: `tests/test_canvas_access.py` with passwordless route coverage

1. Rewrite Canvas access tests to prove paid endpoints are governed only by their normal validation/configuration and never return access-token `401/503` responses.
2. Update frontend tests to prove generation and provider actions do not request an unlock token.
3. Run focused Python/Vitest tests and confirm failure against the existing access gate.
4. Remove access router, service, dependencies, API methods, dialogs, CSS, configuration, and E2E token injection.
5. Keep provider API-key forms masked and unchanged.
6. Run TypeScript typecheck, Vitest, and Canvas Python tests until green.
7. Rebuild `static/canvas` and search the shipped bundle for access-token/login prompts.

## Task 5: Remove obsolete configuration and documentation

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `scripts/generate_integration_secrets.py`
- Modify: `scripts/e2e_server.py`
- Modify: runtime/configuration tests

1. Add assertions that password-login environment keys and instructions are absent from shipped examples and runtime setup.
2. Run focused documentation/configuration tests and confirm failure.
3. Remove `FACAI_AUTH_*`, role tokens, integration password/session keys, and Canvas access keys from examples, scripts, and docs.
4. Change integration secret generation to emit only secrets still required for credential encryption/OAuth.
5. Document that any reachable client has full access and the service must remain on a trusted, access-controlled network.
6. Re-run the focused tests and repository searches until green.

## Task 6: Full regression and live acceptance

**Files:**
- Modify only defects exposed by verification.

1. Run `python -m compileall -q .` (excluding dependency/cache directories if needed).
2. Run `python -m unittest discover -s tests -q`.
3. Run `npm.cmd run typecheck:canvas` and `npm.cmd run test:canvas`.
4. Run `npm.cmd run test:e2e` (which rebuilds Canvas first).
5. Run `python -m pip check` and the repository dependency audit commands available in the workspace.
6. Start/restart the supervised application only after identifying the process/workspace relationship.
7. Verify `/healthz`, `/readyz`, `/app`, `/app/api-connections`, `/app/canvas`, representative APIs, legacy login redirects, and absence of password prompts in a browser.
8. Run `git diff --check`, record branch/HEAD, list every uncommitted file, and report any remaining password references that are third-party credentials rather than login gates.

## Completion constraints

- Do not push GitHub.
- Do not modify unrelated user work.
- Do not claim completion from stale test output.
- Do not remove third-party API credential masking or encryption.
- If a public deployment is later required, authentication must be designed again rather than resurrected through hidden environment switches.
