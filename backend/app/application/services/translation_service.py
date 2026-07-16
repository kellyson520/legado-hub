from uuid import uuid4
from math import ceil

import httpx

from app.core.exceptions import NotFoundException
from app.domain.entities.translation_runtime import TranslationChunk, TranslationJob


class TranslationService:
    def __init__(self, platform=None, repo=None, canonical_repo=None, max_chunk_chars: int = 2000, max_chunk_attempts: int = 2):
        self._platform = platform
        self._repo = repo
        self._canonical_repo = canonical_repo
        self._max_chunk_chars = max_chunk_chars
        self._max_chunk_attempts = max_chunk_attempts

    async def list_jobs(self) -> list[dict]:
        if self._repo is None:
            return []
        return [self._serialize_job(job) for job in self._repo.list_jobs()]

    async def list_jobs_page(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        search: str = "",
        status: str | None = None,
    ) -> dict:
        if hasattr(self._repo, "list_jobs_page"):
            rows, total = self._repo.list_jobs_page(
                page=page,
                page_size=page_size,
                search=search,
                status=status,
            )
        else:
            all_rows = self._repo.list_jobs()
            normalized = search.strip().lower()
            filtered = [
                item for item in all_rows
                if (not normalized or normalized in f"{item.id} {item.source_language} {item.target_language} {item.provider}".lower())
                and (not status or item.status == status)
            ]
            total = len(filtered)
            rows = filtered[(page - 1) * page_size : page * page_size]
        return {
            "items": [self._serialize_job(item) for item in rows],
            "meta": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": ceil(total / page_size) if total else 0,
                "search": search,
                **({"status": status} if status else {}),
            },
        }

    async def review_job(self, job_id: str, *, reviewer_id: str, memory_note: dict) -> dict:
        if self._repo is None:
            raise NotFoundException("Translation job not found")
        job = self._repo.get_job(job_id)
        if job is None:
            raise NotFoundException("Translation job not found")
        payload = dict(job.memory_payload)
        notes = list(payload.get('notes', []))
        notes.append(memory_note)
        payload['notes'] = notes
        payload['reviewed_by'] = reviewer_id
        updated = self._repo.update_job_review(
            job_id,
            review_status='reviewed',
            memory_payload=payload,
        )
        return self._serialize_job(updated)

    async def create_job(self, payload: dict, actor_id: str = "system") -> dict:
        text = payload.get("text", "")
        content_variant_id = payload.get("content_variant_id")
        if not text and content_variant_id:
            if self._canonical_repo is None:
                raise NotFoundException("Content variant not found")
            variant = self._canonical_repo.get_content_variant(content_variant_id)
            if variant is None:
                raise NotFoundException("Content variant not found")
            text = variant.content
        model = payload.get("model") or None
        provider_group = payload.get("provider_group", "translation")
        chunks = self._split_text(text, payload.get("chunk_size", self._max_chunk_chars))

        translated_chunks: list[TranslationChunk] = []
        for chunk_index, chunk_text in enumerate(chunks):
            translated_chunks.append(
                await self._translate_chunk(
                    chunk_index=chunk_index,
                    chunk_text=chunk_text,
                    payload=payload,
                    actor_id=actor_id,
                    provider_group=provider_group,
                    model=model,
                )
            )

        result_text = "".join(chunk.translated_text for chunk in translated_chunks)
        provider = translated_chunks[0].provider if translated_chunks else ""
        saved = TranslationJob(
            id=uuid4().hex,
            actor_id=actor_id,
            source_language=payload.get("source_language", ""),
            target_language=payload.get("target_language", ""),
            status="succeeded",
            provider=provider,
            model=translated_chunks[0].model if translated_chunks else (model or ""),
            source_text=text,
            result_text=result_text,
            content_variant_id=content_variant_id,
            review_status="candidate",
            memory_payload={"content_variant_id": content_variant_id} if content_variant_id else {},
            chunk_count=len(translated_chunks),
            chunks=translated_chunks,
        )
        if self._repo is None:
            return self._serialize_job(saved)
        return self._serialize_job(self._repo.save_job(saved))

    async def _translate_chunk(
        self,
        chunk_index: int,
        chunk_text: str,
        payload: dict,
        actor_id: str,
        provider_group: str,
        model: str | None,
    ) -> TranslationChunk:
        last_error: Exception | None = None
        for attempt in range(1, self._max_chunk_attempts + 1):
            try:
                invocation = await self._platform.invoke_chat(
                    provider_group=provider_group,
                    model=model,
                    payload=self._build_translation_payload(chunk_index, chunk_text, payload),
                    quota_scope=("user", actor_id),
                )
                output = invocation.get("output")
                translated = output.get("text", "") if isinstance(output, dict) else str(output or "")
                return TranslationChunk(
                    id=uuid4().hex,
                    chunk_index=chunk_index,
                    source_text=chunk_text,
                    translated_text=translated,
                    status="succeeded",
                    provider=invocation.get("provider_name", ""),
                    model=invocation.get("model", model),
                    usage=self._normalize_usage(invocation.get("usage")),
                    attempt_count=attempt,
                )
            except Exception as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {400, 422}:
                    raise
                last_error = exc
        assert last_error is not None
        raise last_error

    @staticmethod
    def _split_text(text: str, chunk_size: int) -> list[str]:
        if not text:
            return [""]
        return [text[index:index + chunk_size] for index in range(0, len(text), chunk_size)]

    @staticmethod
    def _build_translation_payload(chunk_index: int, chunk_text: str, payload: dict) -> dict:
        source_language = payload.get("source_language", "")
        target_language = payload.get("target_language", "")
        return {
            "task": "translation",
            "chunk_index": chunk_index,
            "text": chunk_text,
            "source_language": source_language,
            "target_language": target_language,
            "messages": [
                {
                    "role": "system",
                    "content": f"Translate the user text from {source_language} to {target_language}.",
                },
                {"role": "user", "content": chunk_text},
            ],
        }

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

    def _serialize_job(self, job: TranslationJob) -> dict:
        progress = "100%" if job.status == "succeeded" else "0%"
        return {
            "id": job.id,
            "name": f"{job.source_language}->{job.target_language}",
            "status": job.status,
            "provider": job.provider,
            "model": job.model,
            "source_language": job.source_language,
            "target_language": job.target_language,
            "source_text": job.source_text,
            "content_variant_id": job.content_variant_id,
            "review_status": job.review_status,
            "memory_payload": job.memory_payload,
            "progress": progress,
            "chunk_count": job.chunk_count,
            "result_text": job.result_text,
            "chunks": [
                {
                    "id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "status": chunk.status,
                    "provider": chunk.provider,
                    "model": chunk.model,
                    "attempt_count": chunk.attempt_count,
                    "usage": chunk.usage,
                    "translated_text": chunk.translated_text,
                }
                for chunk in job.chunks
            ],
            "created_at": job.created_at.isoformat(),
        }
