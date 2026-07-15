# Interactive Browser Verification Design

## Goal

When a source build encounters an access verification page, first make one bounded attempt with a standard Chromium session. If the page still requires a human interaction, pause the candidate and let its owner complete that interaction directly inside the Legado Hub web application. The source Agent then continues only in that same short-lived browser session.

This is an authorised, human-in-the-loop inspection channel. It is not a Cloudflare bypass feature.

## Non-goals and safety boundary

- Do not solve CAPTCHAs automatically or contract a solving service.
- Do not spoof browser fingerprints, rotate proxies, use stealth plugins, or replay clearance cookies through ordinary HTTP clients.
- Do not publish a candidate unless normal search, TOC, and content validation all pass.
- Do not expose VNC, the browser DevTools endpoint, or a browser profile on the public network.
- Do not persist browser cookies after the session ends.

The user must only use a manual verification session for sites they own or are authorised to access.

## User experience

The source-build result distinguishes ordinary parse failures from access verification:

1. A probe detects a known verification response (for example a verification redirect or challenge shell) and reports `verification_required` instead of the generic `content_failed`.
2. The runtime starts one standard, isolated Chromium attempt without evasion settings. If normal JavaScript/browser navigation reaches readable content, the runtime validates the source without asking the user.
3. If human interaction remains necessary, the candidate moves to `awaiting_manual_verification`. The source-build page shows **Open verification session**.
4. The owner opens the session in an embedded browser panel in Hub, completes any permitted interaction, and presses **Continue validation**.
5. The runtime performs a bounded re-validation in that exact session. Results remain candidate-only and are published only through the existing review path.
6. Completing, cancelling, timing out, or failing the job closes Chromium and deletes its temporary profile.

The panel must clearly show the target host, remaining session time, and a **Cancel and destroy session** control.

## Architecture

```text
source probe / Agent
        |
        | verification_required
        v
InteractiveBrowserService -----> isolated Chromium profile
        |                                |
        | short-lived session id          | loopback-only browser display/control
        v                                v
Hub API + authenticated UI <----- internal browser relay
        |
        | same-session DOM evidence and validation only
        v
source validation -> candidate/review workflow
```

### Backend components

`InteractiveBrowserService` owns the lifecycle for one session:

- Creates a random profile directory, generated session identifier, owner id, source-version id, target origin, expiry, and state.
- Starts Chromium with a normal browser configuration and loopback-only control/display services.
- Enforces one active session per source candidate and bounded concurrent session count.
- Accepts only same-origin navigation below the candidate's approved origin list. It blocks arbitrary URLs, downloads, file URLs, extension installation, and arbitrary DevTools commands.
- Supplies a sanitised page snapshot to the source Agent and source validator; the Agent never receives raw cookies or a generic browser-control tool.
- Destroys the browser and profile in `finally` for every terminal state.

`InteractiveBrowserRelay` provides the embedded panel without public VNC access:

- Hub authenticates the user normally, then creates a single-use, short-lived relay token scoped to one session and owner.
- The browser stream/control WebSocket is reverse-proxied through Hub on the existing application origin. The underlying service binds to loopback only.
- CSRF/origin checks, token expiry, idle timeout, and audit events apply to every action.

`SourceProbeService` gains a verification classification:

- `verification_required` for challenge redirects/shells.
- `content_failed` only when the site actually returns an accessible page that cannot be parsed.
- A source Agent decision records whether automatic browser inspection was attempted, whether manual interaction was requested, and the terminal evidence.

### Frontend components

- Source build result and agent-run cards render `verification_required` with a plain-language explanation.
- `ManualVerificationPanel` opens only for the candidate owner and shows the embedded browser relay after an explicit confirmation.
- The panel has countdown, host indicator, continue, cancel, and terminal-result states. It cannot edit source rules or invoke arbitrary tools.
- System Settings adds an administrator-controlled enablement switch, max concurrent sessions, and session timeout. The default remains disabled.

## Automatic-first policy

The system attempts standard browser inspection only after an HTTP probe classifies access verification. It has a strict per-candidate timeout and one attempt per audit cycle. It may execute normal page JavaScript and follow the permitted origin path, but it must stop on a CAPTCHA, explicit user-interaction challenge, cross-origin navigation, or timeout.

If it reaches content without interaction, the regular parser must still pass search, TOC, and content checks. If it cannot, the system requests the owner to use the interactive panel or leaves the candidate deferred; it never treats browser rendering alone as a valid source.

## Data and audit model

Add an `interactive_browser_sessions` record with:

- id, source_version_id, owner_id, allowed_origins, state, created_at, expires_at, closed_at;
- automatic_attempted, manual_interaction_started, terminal_reason;
- no cookies, browser storage, page HTML, screenshots, or credentials.

Append audit records for creation, panel open, manual-confirm, validation request, cancellation, timeout, and cleanup. Tool evidence may contain a bounded, sanitised DOM summary and response classification, never cookie or authentication header values.

## Failure handling

| Condition | Outcome |
| --- | --- |
| Standard browser reaches readable content | Run normal validation automatically. |
| Challenge requires interaction | Pause as `awaiting_manual_verification`. |
| Owner cancels, session expires, or browser crashes | Close and remove profile; retain candidate with a clear terminal reason. |
| Candidate owner changes or candidate is deleted | Immediately revoke relay token and destroy the session. |
| Validation still fails after interaction | Record the real parse error and do not publish. |

## Tests

- Probe classifies the bqgiu-style verification redirect as `verification_required`.
- Automatic inspection is attempted once and is never treated as success without full-chain validation.
- A manual session is owner-scoped, expires, rejects a different origin/user, and removes its profile on all terminal paths.
- The Agent receives only sanitised page evidence and cannot call arbitrary browser-control commands.
- Relay access requires a valid, single-use authenticated token and is unavailable after cancellation/expiry.
- UI covers automatic success, awaiting manual verification, continue, cancel, timeout, and cleanup states.
- Existing source-build, provider routing, Agent tool, and production frontend builds remain green.

## Rollout

The administrator toggle is disabled by default. Enable it only on a VPS with a locally installed Chromium runtime. Start with one concurrent session, a five-minute expiry, and an allow-list generated from the candidate source/probe origin. Monitor audit events and resource use before raising limits.
