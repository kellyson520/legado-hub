# Source-Build Agent Enhancement Design

## Context

The deterministic source-build engine can synthesize and validate common public HTML book sources, but its DOM heuristics intentionally stop when a site needs extra inspection or a rule repair. A model can improve coverage only if it operates like a bounded coding agent: it observes real evidence, calls narrowly scoped tools, proposes a patch, and verifies the patch against the live reading chain. It must never receive arbitrary shell access, arbitrary network access, or source publication authority.

## Goal

When an administrator enables Agent-enhanced source building, invoke an OpenAI-compatible tool-calling agent only after deterministic source building has failed, produced incomplete rules, or failed full-chain validation. The agent may read and test the target site's public pages, produce a standard Legado source-rule patch, and submit a fully validated candidate to the existing review queue.

## Non-Goals

- Do not invoke the model for ordinary deterministic successes.
- Do not let the model execute code, call the shell, access arbitrary hosts, read credentials, or publish sources.
- Do not automatically make an agent-produced rule enabled or published.
- Do not send full page bodies, cookies, authorization headers, or arbitrary response data to the model.

## Settings and Authorization

Add a persistent system setting named `source_build_agent_enabled`, defaulting to `false`.

- `GET /api/system/source-build-agent-settings` returns the setting and whether an LLM provider is configured.
- `PUT /api/system/source-build-agent-settings` changes the boolean and requires `system.settings.manage`.
- The System Settings page displays an Agent-enhanced source-build switch with an explanation that it uses the configured LLM only after deterministic validation fails.
- Enabling the switch does not bypass quota limits or create an LLM provider. If no provider is configured, a repair is recorded as `skipped_not_configured` and remains reviewable.

The setting is stored through a small generic system-settings repository/table instead of overloading provider credentials. The UI does not receive provider secrets.

## Invocation Policy

1. Run the existing deterministic generator, DOM synthesis, and fresh-session full-chain probe.
2. If search, TOC, and content all validate, preserve the existing deterministic candidate flow and do not invoke the model.
3. If the policy selects `llm_repair`, invoke the Agent only when the system setting is enabled and a provider is available.
4. Give the Agent the existing source rule, sanitized deterministic probe evidence, target origin, remaining budget, and a compact tool transcript.
5. An Agent-produced patch is merged only in memory for validation. A successful full-chain validation persists a candidate version and creates a review item. A failed run persists its trace and remains an escalation; neither path publishes the source.

## Bounded Tool Loop

The existing `SourceBuildAIRepairService` becomes a bounded observe-act-verify loop with explicit function schemas and a maximum of four model turns. It is inspired by coding agents' tool loop, but tools operate only on the one source-building problem.

| Tool | Capability | Limits |
| --- | --- | --- |
| `source.inspect` | Return existing sanitized rule and deterministic evidence. | Read-only; no request arguments. |
| `page.inspect` | GET an entry, search, book, or chapter URL and return status, final URL, forms, link patterns, DOM outline, and a short sanitized text excerpt. | Same origin as submitted source; GET; response excerpt and metadata are bounded. |
| `page.request` | Submit a bounded GET or form-encoded POST needed to test a discovered public search flow. | Same origin; only GET/POST; no custom sensitive headers; request body and response excerpts are bounded. |
| `source.probe` | Return the most recent full-chain probe summary. | Read-only. |
| `rule.propose` | Store an in-memory patch limited to Legado rule fields. | Existing allowlist; no source identity, enablement, or publishing fields. |
| `rule.validate` | Apply the proposed patch in memory and rerun search, TOC, and content using a fresh client session. | One bounded live validation per proposed patch; returns stage evidence only. |
| `review.request` | Create a review request after validation evidence is available. | Candidate-only; cannot publish. |

Tool arguments are validated against concrete JSON schemas. Tool handlers may be asynchronous; the registry keeps its synchronous API for existing callers and adds an awaited invocation path for the agent loop. Every invocation and result is saved through `AgentRuntimeService`.

## Network and Data Safety

- The target origin is captured from the submitted canonical URL. Page tools accept only URLs that resolve to that origin; redirects to a different origin are reported but not followed by subsequent Agent calls.
- Page tools reuse the project's HTTP client protections and close their client in all paths.
- Request/response evidence strips cookies and authorization-like fields, truncates text and HTML-derived summaries, and records no full response body in the prompt.
- The LLM receives no system secrets, provider API keys, persisted cookies, or arbitrary page-script execution capability.
- Existing provider quota enforcement applies to every model turn. The loop stops at the first validated full chain, an explicit review request, a tool rejection, or the four-turn limit.

## Agent Prompt

The versioned system prompt directs the model to:

1. inspect the known evidence before guessing;
2. use `page.inspect` and `page.request` only to understand a public HTML/search flow;
3. propose only standard Legado fields and selectors;
4. call `rule.validate` after each material rule change;
5. request review only after search, TOC, and content all pass;
6. never publish, enable, exfiltrate data, invoke unlisted tools, or return prose in place of a rule patch.

The persisted trace includes prompt version, model/provider metadata, tool calls, sanitised results, proposed fields, validation evidence, and the review item ID.

## Result States

| State | Meaning |
| --- | --- |
| `not_requested` | Switch is off or deterministic validation passed. |
| `skipped_not_configured` | Switch is on but no provider is available. |
| `running` | A bounded Agent tool loop is in progress. |
| `validated_for_review` | Full chain passed; candidate and review item were created. |
| `failed` | Tool/model/validation failure; evidence is retained for manual review. |
| `budget_exhausted` | The loop reached its model-turn or quota boundary. |

## Test Plan

1. System setting defaults to off, persists through the authorized API, and appears in the settings UI.
2. A deterministic full-chain success never invokes the provider even when the switch is on.
3. A deterministic failure invokes the Agent only when the setting and provider are available.
4. A fake tool-calling provider can inspect a form, submit a same-origin POST, propose a patch, and validate search/TOC/content.
5. Cross-origin URLs, sensitive headers, unsupported methods, oversized bodies, and unregistered tools are rejected.
6. A successful Agent validation creates a candidate review item and never publishes or enables the source.
7. Provider failure, quota failure, and loop exhaustion produce structured evidence without breaking the source-build job.
