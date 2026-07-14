# OpenAI Compatible Provider Contract

## Goal

Keep the provider boundary predictable when invoking OpenAI-compatible chat APIs: send only supported request options, and retain the provider response needed by downstream agent tooling.

## Request boundary

`OpenAICompatibleProvider.invoke_chat()` will construct the outgoing payload from its required chat fields plus an explicit allowlist of supported optional fields. Unknown keys supplied through `options` are ignored. This prevents accidental forwarding of internal metadata or unsupported provider-specific input.

The existing supported tool-related fields (`tools` and `tool_choice`) and generation controls (`max_tokens` and `temperature`) remain forwarded unchanged.

## Response boundary

The normalized result will expose:

- `output.text`: an empty string when the provider returns no text content;
- `output.message`: the complete first choice message from the provider;
- `output.tool_calls`: that message's tool call list;
- `output.raw`: the complete provider response.

The API credential is used solely in the authorization header and is never included in the normalized result.

## Error handling

This change does not alter existing HTTP error handling or provider response validation. A missing message content continues to normalize safely to an empty text value.

## Verification

Extend the existing mock-transport contract test to assert allowlist filtering, output fidelity, tool-call preservation, and credential non-disclosure. Run the focused provider test, then the provider-platform regression test.
