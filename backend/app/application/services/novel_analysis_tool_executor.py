from app.domain.entities.agent_runtime import ToolResult


class NovelAnalysisToolExecutor:
    _TOOL_CATEGORIES = {
        "source.search": "read",
        "book.resolve": "read",
        "toc.get": "read",
        "chapter.fetch": "read",
        "evidence.search": "read",
        "evidence.get": "read",
    }

    def __init__(
        self,
        *,
        ingestion_service,
        evidence_service,
        agent_runtime,
        audit_service=None,
        settings_service=None,
    ):
        self._ingestion_service = ingestion_service
        self._evidence_service = evidence_service
        self._agent_runtime = agent_runtime
        self._audit_service = audit_service
        self._settings_service = settings_service

    def handlers(self) -> dict:
        return {
            tool_name: (lambda arguments, name=tool_name: self.ainvoke(name, arguments))
            for tool_name in self._TOOL_CATEGORIES
        }

    async def ainvoke(self, tool_name: str, arguments: dict) -> ToolResult:
        tenant_id = str(arguments.get("tenant_id") or "")
        if not tenant_id:
            return ToolResult(status="rejected", error_code="tenant_id_required")
        category = self._TOOL_CATEGORIES.get(tool_name)
        if category is None:
            return ToolResult(status="rejected", error_code="tool_not_implemented")

        run_id = str(arguments.get("agent_run_id") or "")
        if not run_id or self._agent_runtime.get_run(run_id, tenant_id=tenant_id) is None:
            run_id = self._agent_runtime.create_run(
                tenant_id=tenant_id,
                agent_kind="knowledge",
                input_payload={"tool": tool_name},
            ).id
        invocation = self._agent_runtime.record_tool_invocation(
            run_id=run_id,
            tenant_id=tenant_id,
            tool_name=tool_name,
            category=category,
            arguments=arguments,
        )
        try:
            evidence_ids: list[str] = []
            if tool_name == "source.search":
                search = await self._ingestion_service.search_sources(
                    keyword=str(arguments["keyword"]),
                    source_ids=self._optional_source_ids(arguments.get("source_ids")),
                    author_hint=self._optional_text(arguments.get("author_hint")),
                )
                data = {
                    "items": [
                        {
                            "source_id": item.get("source_id"),
                            "name": item.get("name", ""),
                            "author": item.get("author", ""),
                            "book_url": item.get("bookUrl", ""),
                        }
                        for item in search.get("items", [])[:12]
                    ]
                }
            elif tool_name == "book.resolve":
                data = await self._ingestion_service.resolve_book(
                    source_id=int(arguments["source_id"]),
                    book_url=str(arguments["book_url"]),
                    book_name=str(arguments["book_name"]),
                    author_hint=self._optional_text(arguments.get("author_hint")),
                )
            elif tool_name == "toc.get":
                data = await self._ingestion_service.get_table_of_contents(
                    source_id=int(arguments["source_id"]),
                    book_url=str(arguments["book_url"]),
                    book_name=str(arguments["book_name"]),
                    author_hint=self._optional_text(arguments.get("author_hint")),
                )
            elif tool_name == "chapter.fetch":
                ingested = await self._ingestion_service.fetch_and_ingest_chapter(
                    source_id=int(arguments["source_id"]),
                    book_url=str(arguments["book_url"]),
                    chapter_index=int(arguments["chapter_index"]),
                    book_name=str(arguments["book_name"]),
                    author_hint=(str(arguments["author_hint"]) if arguments.get("author_hint") else None),
                )
                data = {
                    "canonical_work_id": ingested.canonical_work_id,
                    "canonical_chapter_id": ingested.canonical_chapter_id,
                    "content_variant_id": ingested.content_variant_id,
                    "evidence_span_ids": ingested.evidence_span_ids,
                    "content_preview": ingested.content[:1200],
                    "reaudit_task_ids": await self._queue_changed_variant_reaudits(
                        ingested,
                        tenant_id=tenant_id,
                    ),
                }
                evidence_ids = ingested.evidence_span_ids
            elif tool_name == "evidence.search":
                spans = self._evidence_service.list_verified_spans(
                    str(arguments["canonical_chapter_id"]),
                    query=self._optional_text(arguments.get("query")) or "",
                    limit=int(arguments.get("limit", 20)),
                )
                evidence_ids = [span.id for span in spans]
                data = {"items": [self._serialize_span(span) for span in spans]}
            elif tool_name == "evidence.get":
                span = self._evidence_service.get_verified_span(str(arguments["evidence_id"]))
                if span is None:
                    raise LookupError("verified evidence span not found")
                evidence_ids = [span.id]
                data = self._serialize_span(span)
            else:
                raise ValueError("tool_not_implemented")

            result = self._agent_runtime.record_tool_result(
                invocation_id=invocation.id,
                tenant_id=tenant_id,
                status="accepted",
                data=data,
            )
            self._record_evidence(invocation.id, tenant_id, evidence_ids)
            return result
        except (KeyError, LookupError, PermissionError, ValueError, TypeError) as exc:
            return self._agent_runtime.record_tool_result(
                invocation_id=invocation.id,
                tenant_id=tenant_id,
                status="rejected",
                error_code=type(exc).__name__.lower(),
            )
        return self._agent_runtime.record_tool_result(
            invocation_id=invocation.id,
            tenant_id=tenant_id,
            status="rejected",
            error_code="tool_not_implemented",
        )

    def _record_evidence(self, invocation_id: str, tenant_id: str, evidence_ids: list[str]) -> None:
        for evidence_id in evidence_ids:
            span = self._evidence_service.get_verified_span(evidence_id)
            if span is None:
                continue
            self._agent_runtime.record_tool_evidence(
                invocation_id=invocation_id,
                tenant_id=tenant_id,
                evidence_type="evidence_span",
                resource_id=span.id,
                payload={
                    "canonical_chapter_id": span.canonical_chapter_id,
                    "start_offset": span.start_offset,
                    "end_offset": span.end_offset,
                    "excerpt_sha256": span.excerpt_sha256,
                    "content_sha256": span.content_sha256,
                },
            )

    async def _queue_changed_variant_reaudits(self, ingested, *, tenant_id: str) -> list[str]:
        if self._audit_service is None or self._settings_service is None:
            return []
        changed_variant_ids = list(getattr(ingested, "changed_prior_variant_ids", []) or [])
        if not changed_variant_ids:
            return []
        automation = self._settings_service.get_section("agents", "automation").get("value", {})
        if not (
            bool(automation.get("enabled", True))
            and bool(automation.get("background_incremental_enabled", False))
            and not bool(automation.get("emergency_pause", False))
        ):
            return []
        budgets = self._settings_service.get_section("agents", "budgets").get("value", {})
        task_ids: list[str] = []
        for variant_id in changed_variant_ids:
            result = await self._audit_service.queue_reaudit_content_variant(
                variant_id,
                tenant_id=tenant_id,
                policy=budgets,
            )
            task_ids.extend(result.task_ids or [])
        return list(dict.fromkeys(task_ids))

    @staticmethod
    def _serialize_span(span) -> dict:
        return {
            "id": span.id,
            "canonical_chapter_id": span.canonical_chapter_id,
            "start_offset": span.start_offset,
            "end_offset": span.end_offset,
            "excerpt": span.excerpt,
            "excerpt_sha256": span.excerpt_sha256,
            "content_sha256": span.content_sha256,
        }

    @staticmethod
    def _optional_text(value) -> str | None:
        return str(value).strip() if value is not None and str(value).strip() else None

    @staticmethod
    def _optional_source_ids(value) -> list[int] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("source_ids must be a list")
        return [int(source_id) for source_id in value]
