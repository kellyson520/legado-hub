from uuid import uuid4
import re
from collections.abc import Awaitable, Callable

from app.domain.entities.ai_runtime import AITask


class AIService:
    def __init__(self, platform=None, repo=None):
        self._platform = platform
        self._repo = repo

    async def list_tasks(self) -> list[dict]:
        if self._repo is None:
            return []
        return [self._serialize(task) for task in self._repo.list_tasks()]

    async def run_character_analysis(self, payload: dict, actor_id: str = "system") -> dict:
        invocation = await self._platform.invoke_chat(
            provider_group=payload.get("provider_group", "ai"),
            model=payload.get("model") or None,
            payload=self._build_character_payload(payload),
            quota_scope=("user", actor_id),
        )
        task = AITask(
            id=uuid4().hex,
            kind="character_analysis",
            actor_id=actor_id,
            provider=invocation.get("provider_name", ""),
            model=invocation.get("model", payload.get("model", "gpt-4.1-mini")),
            status="succeeded",
            prompt_payload=payload,
            result=self._normalize_output(invocation.get("output")),
            usage=self._normalize_usage(invocation.get("usage")),
            cost=invocation.get("cost", {}),
        )
        if self._repo is None:
            return self._serialize(task)
        return self._serialize(self._repo.save_task(task))

    async def run_source_build_repair(
        self,
        payload: dict,
        actor_id: str = "system",
        runner: Callable[[], Awaitable[dict]] | None = None,
    ) -> dict:
        """Execute a bounded source-build repair and always persist its final outcome."""
        try:
            invocation = await (
                runner()
                if runner is not None
                else self._platform.invoke_chat(
                    provider_group=payload.get("provider_group", "source_build"),
                    model=payload.get("model") or None,
                    payload=payload,
                    quota_scope=("tenant", actor_id),
                )
            )
            result = {
                "source_version_id": payload.get("source_version_id"),
                "agent_run_id": payload.get("agent_run_id"),
                "url": payload.get("url"),
                "output": self._normalize_output(invocation.get("output")),
            }
            if isinstance(invocation.get("repair"), dict):
                result["repair"] = invocation["repair"]
            task = AITask(
                id=uuid4().hex,
                kind="source_build_repair",
                actor_id=actor_id,
                provider=invocation.get("provider_name", ""),
                model=invocation.get("model", payload.get("model", "")),
                status="succeeded",
                prompt_payload=payload,
                result=result,
                usage=self._normalize_usage(invocation.get("usage")),
                cost=invocation.get("cost", {}),
            )
        except Exception as exc:
            task = AITask(
                id=uuid4().hex,
                kind="source_build_repair",
                actor_id=actor_id,
                model=str(payload.get("model") or ""),
                status="failed",
                prompt_payload=payload,
                result={
                    "source_version_id": payload.get("source_version_id"),
                    "agent_run_id": payload.get("agent_run_id"),
                    "url": payload.get("url"),
                    "error": self._sanitize_error(exc),
                },
            )
        if self._repo is None:
            return self._serialize(task)
        return self._serialize(self._repo.save_task(task))

    @staticmethod
    def _sanitize_error(exc: Exception) -> str:
        message = str(exc)
        message = re.sub(r"(?i)(bearer|authorization|api[_ -]?key)\s+[^\s,;]+", r"\1 [redacted]", message)
        return message[:500]

    @staticmethod
    def _build_character_payload(payload: dict) -> dict:
        title = payload.get("title", "")
        content = payload.get("content", "")
        return {
            "task": "character_analysis",
            "title": title,
            "content": content,
            "messages": [
                {
                    "role": "system",
                    "content": "You analyze novels and return concise structured character insights.",
                },
                {"role": "user", "content": f"Title: {title}\n\nContent:\n{content}"},
            ],
        }

    @staticmethod
    def _normalize_output(output) -> dict:
        if isinstance(output, dict):
            return output
        if output is None:
            return {}
        return {"text": str(output)}

    @staticmethod
    def _normalize_usage(usage) -> dict:
        if not isinstance(usage, dict):
            return {}
        input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
        output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _serialize(task: AITask) -> dict:
        return {
            "id": task.id,
            "name": task.prompt_payload.get("title") or task.kind,
            "type": task.kind,
            "status": task.status,
            "provider": task.provider,
            "model": task.model,
            "usage": task.usage,
            "cost": task.cost.get("total", 0),
            "result": task.result,
            "created_at": task.created_at.isoformat(),
        }
