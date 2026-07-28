# OpenAI Compatible Provider Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the OpenAI-compatible provider's request allowlist and complete chat response while preventing credential disclosure.

**Architecture:** `OpenAICompatibleProvider` remains the sole HTTP boundary. Its existing explicit optional-field allowlist constructs the request, and its normalized output retains the first response message, tool calls, and raw provider body. The work item is a regression-contract strengthening: the provider already implements the specified behavior, so no production behavior change is planned unless the focused test exposes a discrepancy.

**Tech Stack:** Python 3, httpx, pytest, pytest-asyncio.

---

## File Structure

- `backend/app/infrastructure/providers/openai_compatible.py`: Builds the outbound chat-completion payload and normalizes the upstream response; expected to remain unchanged unless verification finds a contract failure.
- `backend/tests/test_openai_compatible_provider.py`: Mock-transport regression test for allowed request fields, output fidelity, tool calls, and credential non-disclosure.

### Task 1: Lock the provider boundary with a mock-transport contract

**Files:**
- Modify: `backend/tests/test_openai_compatible_provider.py:28-84`
- Verify: `backend/app/infrastructure/providers/openai_compatible.py:23-58`

- [ ] **Step 1: Preserve the focused contract test**

```python
response_body = {
    "model": "deepseek-chat",
    "choices": [{"message": {"content": None, "tool_calls": [{"id": "call-1"}]}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
}

result = await provider.invoke_chat(
    "deepseek-chat",
    {
        "messages": [],
        "tools": [{"type": "function"}],
        "tool_choice": "auto",
        "max_tokens": 32,
        "temperature": 0.2,
        "unexpected": "must-not-be-forwarded",
    },
)

assert "unexpected" not in captured
assert result["output"]["text"] == ""
assert result["output"]["message"] == response_body["choices"][0]["message"]
assert result["output"]["tool_calls"] == response_body["choices"][0]["message"]["tool_calls"]
assert result["output"]["raw"] == response_body
assert "provider-api-key-should-not-leak" not in str(result)
```

- [ ] **Step 2: Run the focused provider contract**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_openai_compatible_provider.py -q`

Expected: PASS. The provider's existing allowlist forwards `tools`, `tool_choice`, `max_tokens`, and `temperature`, ignores `unexpected`, and returns the full normalized response without exposing the API key.

- [ ] **Step 3: Inspect the verified implementation boundary**

Confirm `OpenAICompatibleProvider.invoke_chat()` builds `request_body` from `model`, `messages`, and the explicit `("tools", "tool_choice", "temperature", "max_tokens")` allowlist; it must not iterate through every payload item. Confirm the normalized output includes `text`, `message`, `tool_calls`, and `raw`.

- [ ] **Step 4: Run the provider-platform regression**

Run: `backend/.venv/Scripts/python.exe -m pytest tests/test_openai_compatible_provider.py tests/test_provider_platform_service.py tests/test_api_provider_platform.py -q`

Expected: PASS with no failures.

- [ ] **Step 5: Commit the contract test**

```bash
git add backend/tests/test_openai_compatible_provider.py
git commit -m "test: strengthen OpenAI provider contract"
```
