from uuid import uuid4

from app.core.exceptions import NotFoundException, ServiceUnavailableException
from app.domain.entities.novel_runtime import NovelAnalysisTask, NovelIngestion


class NovelAgentService:
    def __init__(self, platform=None, repo=None, app_service=None):
        self._platform = platform
        self._repo = repo
        self._app_service = app_service

    async def create_conversation(self, owner_scope: str, title: str = "", **kwargs) -> dict:
        if self._app_service is None:
            raise NotFoundException("unified novel agent is not configured")
        return await self._app_service.create_conversation(owner_scope, title, **kwargs)

    def get_conversation(self, owner_scope: str, conversation_id: str) -> dict:
        if self._app_service is None:
            raise NotFoundException("unified novel agent is not configured")
        return self._app_service.get_conversation(owner_scope, conversation_id)

    async def send_message(self, owner_scope: str, conversation_id: str, content: str, **kwargs):
        if self._app_service is None:
            raise NotFoundException("unified novel agent is not configured")
        return await self._app_service.send_message(owner_scope, conversation_id, content, **kwargs)

    async def list_tools(self, owner_scope: str, book_id: int | None = None) -> list[dict]:
        if self._app_service is None:
            return []
        return await self._app_service.list_tools(owner_scope, book_id)

    async def call_tool(self, owner_scope: str, tool_name: str, arguments: dict, **kwargs) -> dict:
        if self._app_service is None:
            raise NotFoundException("unified novel agent is not configured")
        return await self._app_service.call_tool(owner_scope, tool_name, arguments, **kwargs)

    async def start_analysis(self, novel_id: str, actor_id: str = "system", owner_scope: str | None = None) -> dict:
        if self._repo is None:
            raise NotFoundException("novel ingestion not found")
        ingestion = self._repo.get_ingestion(novel_id, owner_scope=owner_scope)
        if ingestion is None and str(novel_id).isdigit():
            book_id = int(novel_id)
            ingestion = next(
                (
                    item
                    for item in self._repo.list_ingestions(owner_scope=owner_scope)
                    if item.book_id == book_id
                ),
                None,
            )
        if ingestion is None:
            raise NotFoundException("novel ingestion not found")
        novel_id = ingestion.id
        try:
            invocation = await self._platform.invoke_chat(
                provider_group="novel_chat",
                model=None,
                payload=self._build_payload(ingestion),
                quota_scope=("user", actor_id),
            )
        except LookupError as exc:
            raise ServiceUnavailableException(str(exc)) from exc
        task = NovelAnalysisTask(
            id=uuid4().hex,
            novel_id=novel_id,
            actor_id=actor_id,
            owner_scope=ingestion.owner_scope,
            book_id=ingestion.book_id,
            status="succeeded",
            provider=invocation.get("provider_name", ""),
            model=invocation.get("model", "gpt-4.1-mini"),
            pipeline="analysis",
            result=self._normalize_output(invocation.get("output")),
            usage=self._normalize_usage(invocation.get("usage")),
        )
        return self._serialize(self._repo.save_task(task))

    @classmethod
    def _build_payload(cls, ingestion: NovelIngestion) -> dict:
        raw_text = ingestion.source_text or ""
        chunk_size = 2000
        chapter_chunks = []
        for i in range(0, max(len(raw_text), 1), chunk_size):
            chunk_text = raw_text[i:i + chunk_size]
            chapter_chunks.append({
                "chapter_id": f"chunk-{len(chapter_chunks)+1}",
                "chapter_index": len(chapter_chunks) + 1,
                "title": f"第{len(chapter_chunks)+1}节",
                "content": chunk_text,
            })

        from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService
        from app.application.services.novel_scene_tension_service import NovelSceneTensionService

        code_report = NovelCodeAnalysisService().analyze(ingestion.id, chapter_chunks[:8])
        tension_service = NovelSceneTensionService()
        climax_scenes = tension_service.extract_climax_scenes(chapter_chunks[:8], top_k=2)

        char_summary_lines = []
        for c in code_report.characters[:5]:
            aliases_str = f" (别名: {', '.join(c.aliases)})" if c.aliases else ""
            char_summary_lines.append(f"- 【{c.importance_tier.upper()}】{c.name}{aliases_str}：频次 {c.count}，中心度 {c.centrality}")

        timeline_lines = []
        for t in code_report.time_mentions[:6]:
            timeline_lines.append(f"- 时序锚点: {t.normalized}")

        climax_lines = []
        for s in climax_scenes:
            climax_lines.append(f"【{s['chapter_title']} 高潮片段 (张力: {s['tension_score']})】\n{s['excerpt'][:260]}...")

        opening_excerpt = raw_text[:600]

        digest_content = (
            f"小说标题: {ingestion.title}\n"
            f"全书字数: 约 {len(raw_text)} 字\n\n"
            f"### 一、核心角色与网络 (代码图谱提取):\n"
            f"{chr(10).join(char_summary_lines) if char_summary_lines else '暂无显著主要角色'}\n\n"
            f"### 二、时序与事件节点:\n"
            f"{chr(10).join(timeline_lines) if timeline_lines else '暂无时间锚点'}\n\n"
            f"### 三、高能/高潮场景节选 (张力算法定位):\n"
            f"{chr(10).join(climax_lines) if climax_lines else '暂无高张力切片'}\n\n"
            f"### 四、故事开篇样本:\n"
            f"{opening_excerpt}"
        )

        return {
            "task": "novel_analysis",
            "novel_id": ingestion.id,
            "title": ingestion.title,
            "text": digest_content,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一位专业的小说结构化分析专家。根据提供的【小说结构化摘要卡片】（包含角色图谱、核心时序与高能高潮片段），综合评判小说的主线剧情、人物弧光、叙事节奏与核心主题，输出严谨深刻的结构化分析报告。",
                },
                {
                    "role": "user",
                    "content": digest_content,
                },
            ],
        }

    def get_analysis_tools_definitions(self) -> list[dict]:
        return [
            {
                "name": "get_character_graph",
                "description": "提取小说文本的人物网络与别名关系",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}},
            },
            {
                "name": "get_timeline",
                "description": "提取小说文本的时间线转折点与时间锚点",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}}},
            },
            {
                "name": "get_climax_scenes",
                "description": "基于张力算法提取小说的高能高潮冲突片段",
                "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}, "top_k": {"type": "integer"}}},
            },
        ]

    def tool_get_character_graph(self, title: str, content: str) -> dict:
        from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService
        chapters = [{"chapter_id": "c1", "chapter_index": 1, "title": title, "content": content}]
        report = NovelCodeAnalysisService().analyze("tool-graph", chapters)
        return report.character_graph or {"nodes": [{"id": c.name, "tier": c.importance_tier} for c in report.characters], "edges": []}

    def tool_get_timeline(self, title: str, content: str) -> list[dict]:
        from app.application.services.novel_code_analysis_service import NovelCodeAnalysisService
        chapters = [{"chapter_id": "c1", "chapter_index": 1, "title": title, "content": content}]
        report = NovelCodeAnalysisService().analyze("tool-timeline", chapters)
        return [{"text": t.text, "normalized": t.normalized, "status": t.anchor_status} for t in report.time_mentions]

    def tool_get_climax_scenes(self, title: str, content: str, top_k: int = 3) -> list[dict]:
        from app.application.services.novel_scene_tension_service import NovelSceneTensionService
        chapters = [{"chapter_id": "c1", "chapter_index": 1, "title": title, "content": content}]
        return NovelSceneTensionService().extract_climax_scenes(chapters, top_k=top_k)

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
