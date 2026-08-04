import asyncio
import inspect


def complete_text(provider, prompt: str, *, system: str = "") -> str | None:
    if provider is None:
        return None
    method = getattr(provider, "generate", None) or getattr(provider, "complete", None)
    if not callable(method):
        return None
    try:
        result = method(prompt=prompt, system=system)
    except TypeError:
        try:
            result = method(prompt)
        except TypeError:
            result = method([{"role": "system", "content": system}, {"role": "user", "content": prompt}])
    if inspect.isawaitable(result):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            result = asyncio.run(result)
        else:
            return None
    if isinstance(result, tuple):
        result = result[0] if result else ""
    if isinstance(result, dict):
        result = result.get("text") or result.get("content") or result.get("answer") or ""
    text = str(result or "").strip()
    return text or None
