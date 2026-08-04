# OpenHarness Integration Plan

## 1. Protocol boundary

- Add typed OpenHarness v1 request/response models with unknown-field
  tolerance and explicit version checks.
- Add capability constants, action directive builders, and safe error mapping.
- Keep the upstream protocol reference and license metadata in project docs.

## 2. Provider adapters

- Extract shared HTTP/normalization helpers where that reduces duplication.
- Preserve the existing OpenAI-compatible adapter behavior.
- Add Anthropic Messages and Gemini `generateContent` adapters behind the same
  ProviderAdapter port, including text, tools, tool calls, model discovery,
  usage normalization, and endpoint normalization.
- Carry `provider_type` through provider persistence, factory construction, and
  provider settings while defaulting old records to `openai_compatible`.

## 3. Engine endpoint

- Add an authenticated `/api/harness/v1/execute` route.
- Reuse current identity, AI workspace, provider routing, and audit services.
- Return protocol-native action directives and capability denials.
- Do not expose arbitrary host actions or raw credentials.

## 4. Tests and verification

- Add protocol model and version/unknown-field tests.
- Add MockTransport tests for Anthropic and Gemini wire conversion.
- Add endpoint tests for success, unsupported versions, request ID echo,
  authentication, and error redaction.
- Run focused tests, then the complete backend test suite and static checks
  available in the repository.
