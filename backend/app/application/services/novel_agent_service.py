from uuid import uuid4

from app.core.exceptions import NotFoundException
from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIngestion


class NovelAgentService:
    def __init__(self, platform=None, repo=None):
        self._platform = platform
        self._repo = repo

    async def start_analysis(self, novel_id: str, actor_id: str = "system") -> dict:
        if self._repo is None:
            raise NotFoundException("novel ingestion not found")
        ingestion = self._repo.get_ingestion(novel_id)
        if ingestion is None:
            raise NotFoundException("novel ingestion not found")
        invocation = await self._platform.invoke_chat(
            provider_group="novel",
            model=None,
            payload=self._build_payload(ingestion),
            quota_scope=("user", actor_id),
        )
        task = NovelAnalysisTask(
            id=uuid4().hex,
            novel_id=novel_id,
            actor_id=actor_id,
            status="succeeded",
            provider=invocation.get("provider_name", ""),
            model=invocation.get("model", "gpt-4.1-mini"),
            pipeline="analysis",
            result=self._normalize_output(invocation.get("output")),
            usage=self._normalize_usage(invocation.get("usage")),
        )
        return self._serialize(self._repo.save_task(task))

    @staticmethod
    def _build_payload(ingestion: NovelIngestion) -> dict:
        return {
            "task": "novel_analysis",
            "novel_id": ingestion.id,
            "title": ingestion.title,
            "text": ingestion.source_text,
            "messages": [
                {
                    "role": "system",
                    "content": "Extract novel entities, summary, and structured insights.",
                },
                {
                    "role": "user",
                    "content": f"Title: {ingestion.title}\n\nText:\n{ingestion.source_text}",
                },
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
    def _serialize(task: NovelAnalysisTask) -> dict:
        return {
            "id": task.id,
            "novel_id": task.novel_id,
            "status": task.status,
            "provider": task.provider,
            "model": task.model,
            "pipeline": task.pipeline,
            "result": task.result,
            "usage": task.usage,
            "created_at": task.created_at.isoformat(),
        }
