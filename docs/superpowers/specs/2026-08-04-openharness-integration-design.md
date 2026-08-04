# OpenHarness Integration Design

## Status

Approved implementation direction for the OpenHarness integration.

## Upstream basis

This integration follows `SynSwarm/OpenHarness` at commit
`9c86454cf4f0b51e63ec081cb6bed7c84357968b` (MIT). The upstream repository is
primarily a transport-agnostic protocol specification, JSON Schema, examples,
and Shell adapters. It does not contain a universal OpenAI/Anthropic/Gemini
model adapter runtime. Model translation therefore remains an Engine concern.

The normative wire contract is OpenHarness `v1.0.0-draft`:

- Shell to Engine messages contain `protocol_version`, request/correlation IDs,
  capabilities, and a `request.context`.
- Engine to Shell messages contain echoed IDs, supported capabilities, an
  explicit status/error, and ordered `action_directives`.
- Unknown fields are ignored; unknown side-effecting action types are never
  executed by default.
- Attachments are references, not embedded binary data, and long-lived secrets
  remain outside the JSON body.

## Goals

1. Add a standards-compatible OpenHarness v1 Engine boundary to Legado Hub.
2. Reuse the existing ProviderPlatformService, provider routing, quotas,
   AgentRuntimeService, AgentToolRegistry, and AI workspace authorization.
3. Keep model selection independent from the OpenHarness wire contract.
4. Make OpenAI-compatible, Anthropic, and Gemini transports implement the same
   internal provider port, so DeepSeek, GPT, Qwen, Kimi, Ollama, Claude, and
   Gemini-style deployments can be selected without changing Engine code.
5. Preserve all existing `/api/ai`, source-build, novel-agent, and Legado rule
   harness behavior.

## Non-goals

- Do not implement the private DeepSeek Harness protocol.
- Do not claim the OpenHarness upstream repository already supplies model
  adapters that it does not contain.
- Do not expose arbitrary filesystem or shell execution through the protocol.
- Do not replace the existing Agent audit, authorization, or tool registry.
- Do not make streaming normative before OpenHarness publishes a normative
  streaming profile. The first endpoint is request/response with capability
  negotiation.

## Architecture

```text
Shell request
    |
    v
OpenHarness v1 parser and capability validator
    |
    v
OpenHarness Engine service
    |-- identity, tenant and authorization boundary
    |-- AI workspace / AgentRuntime audit boundary
    |-- ProviderPlatformService route selection
    v
Provider adapter factory
    |-- openai_compatible -> OpenAI-compatible chat/embedding API
    |-- anthropic         -> Anthropic Messages API
    `-- gemini            -> Gemini generateContent API
    |
    v
Normalized model result -> OpenHarness action_directives
```

The OpenHarness boundary is a protocol adapter, not a second agent runtime.
The Engine may return `render_message` for model text, and namespaced
`com.legadohub.tool_call` directives for tool calls that require Shell-side
execution. Existing in-process AI workspace calls continue to execute tools
through their current authorization and audit path.

## Provider contract

All model adapters implement the existing `ProviderAdapter` shape:

```text
invoke_chat(model, payload) -> normalized result
list_models() -> model IDs
aclose()
```

The normalized result keeps the existing `output.text`, `output.message`,
`output.tool_calls`, `usage`, and `raw` fields. Each adapter owns only its
vendor wire format, tool-call representation, endpoint normalization, and
response normalization. Secrets never appear in normalized errors or audit
payloads.

Provider accounts gain an explicit `provider_type` with a backward-compatible
default of `openai_compatible`. Existing accounts and legacy LLM settings keep
their current behavior.

## OpenHarness endpoint

The Engine exposes an authenticated endpoint at:

```text
POST /api/harness/v1/execute
```

The HTTP identity is authoritative for tenant and permissions. Body `auth`
fields are treated as opaque references and cannot move a request across
tenants. The endpoint:

- validates protocol version and returns `protocol_version_unsupported` for an
  unsupported major line;
- echoes `request_id` and `correlation_id`;
- publishes supported capabilities and explicit denials;
- maps `context.user_intent` into the existing AI Engine;
- emits safe `render_message`, approval, or error directives;
- records the run/request through existing AgentRuntimeService where an agent
  invocation is performed.

## Compatibility

The existing Legado rule harness at `/api/engine/test` remains unchanged. The
OpenHarness endpoint is a separate protocol surface and must not be imported
as a rule evaluator.

## Verification

- Pydantic request/response fixtures cover success, errors, unknown fields,
  capability negotiation, and unknown action types.
- Provider tests use `httpx.MockTransport`; no real provider calls are made.
- HTTP tests assert authentication, tenant isolation, ID echoing, version
  rejection, and safe error responses.
- Existing provider, AI workspace, agent runtime, and rule harness tests remain
  part of the verification set.
