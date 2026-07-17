# Passwordless Intranet Access Design

**Date:** 2026-07-16  
**Status:** Approved

## Problem

The application currently contains three independent access gates:

1. application-wide role tokens and a signed authentication cookie;
2. a separate administrator password and session for the API integration center;
3. a Canvas access token and access dialog.

For the intended trusted intranet deployment these gates add operational friction and duplicate state. The product owner has approved removing every password or token login requirement, including the administrator-password re-entry previously required for permanently purging integration data.

## Goals

- All application pages and business APIs are usable without a password, role token, login cookie, or Canvas access token.
- The integration center opens directly without an administrator login session.
- Permanent integration-data purge uses an explicit confirmation phrase instead of a password.
- Password-related environment variables, bootstrap utilities, login pages, browser redirects, and obsolete tests are removed.
- Network and operational protections unrelated to login remain active.

## Non-goals

- Removing or exposing third-party API credentials. API keys remain secrets and may still use password-style masked inputs.
- Removing Host or Origin validation, CSRF/source checks where still applicable, request IDs, upload validation, rate limits, audit records, or task safeguards.
- Redesigning the broader authorization model for public or Internet deployment. The resulting application is explicitly a trusted-intranet system.

## Design

### Application access

The global authentication middleware and role-token enforcement are removed from the request path. Business routes no longer depend on a current user or role. Code that only exists to issue, parse, rotate, or validate application session tokens is deleted.

Legacy browser URLs such as `/app/login` redirect to `/app` without presenting a form. Obsolete login submission endpoints are removed. Any frontend code that redirects unauthenticated responses to a login page is deleted.

### Integration center

`/app/api-connections` renders directly. The dedicated login page, login JavaScript, password-hash configuration, administrator session, password verification, and login throttling are removed from the active integration-center flow.

Integration audit records continue to identify the operation and request context. They no longer claim that a password was verified.

### Permanent purge

The purge request no longer contains a password. It contains a fixed confirmation phrase defined by the API contract. The backend validates that phrase before deleting data. The UI requires the same phrase and continues to present the action as irreversible.

### Canvas

Canvas routes no longer accept or validate `CANVAS_ACCESS_TOKEN`. The access dialog and client-side token storage are removed from source and rebuilt production assets. Canvas provider API keys remain protected as application configuration secrets and are outside the login-removal scope.

### Configuration and documentation

The following configuration families are removed from examples, startup requirements, and documentation:

- `FACAI_AUTH_*` and application role tokens;
- `FACAI_INTEGRATIONS_ADMIN_PASSWORD_HASH` and integration administrator session secrets used only for login;
- `CANVAS_ACCESS_TOKEN`.

Startup scripts must not generate, require, or inject these values. Documentation will state that the service is passwordless and must remain on a trusted, access-controlled network.

### Retained security controls

- trusted Host and Origin validation;
- request correlation IDs and security headers;
- upload/archive/parser limits;
- task and AI usage rate limits;
- sensitive-operation audit logging;
- irreversible-action confirmation;
- third-party credential encryption/masking and outbound URL controls.

## Compatibility

Old login page bookmarks redirect to their corresponding application page for one compatibility period. Programmatic callers no longer need authentication headers. Authentication-only response fields and endpoints may be removed where no current client consumes them.

The change intentionally removes role separation: any device that can reach the service can perform every operation. Deployment documentation must make this trust boundary explicit.

## Verification

- Add failing tests proving general pages/APIs, the integration center, and Canvas work without credentials.
- Add purge contract tests proving the confirmation phrase is required and passwords are neither accepted nor checked.
- Remove or rewrite tests whose sole purpose is password hashing, login sessions, role tokens, or Canvas access tokens.
- Search production sources and shipped assets for obsolete password-login strings and environment variables.
- Run targeted authentication, integration, Canvas, and purge tests during implementation.
- Run the complete Python test suite, Playwright suite, compilation checks, dependency checks, and live `/healthz`/`/readyz` plus browser-route verification before completion.

## Risks and mitigations

- **Risk:** accidental exposure outside the trusted network grants full access.  
  **Mitigation:** preserve Host/Origin controls, document the boundary prominently, and verify the runtime bind/firewall topology during handoff.
- **Risk:** old frontend assets continue prompting for tokens.  
  **Mitigation:** rebuild Canvas assets and test the shipped bundle, not only source modules.
- **Risk:** deleting authentication helpers also deletes unrelated security controls.  
  **Mitigation:** remove password-specific paths surgically and retain focused regression tests for Host/Origin, limits, headers, and audit behavior.
