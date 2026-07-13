"""
AI 增强服务接口层 (v1 - Pro API)

职责：
- 接收 HTTP 请求
- 调用 LLM 驱动（应用层）
- 发布 AI 领域事件
- 统一异常处理
- 全链路日志
"""

import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends

from ....core.response import ok, fail
from ....core.logging import get_logger
from ....core.exceptions import (
    AuthenticationException, QuotaExceededException,
    NotFoundException, ExternalServiceException, ValidationException
)
from ....core.dependencies import get_auth_context, require_permission, AuthContext
from ....core.events import publish_event, AIAnalysisCompletedEvent, QuotaExceededEvent
from ....core.redis_client import redis_client

logger = get_logger("api.ai")

router = APIRouter(prefix="/api/v1/llm", tags=["ai"])


class LLMService:
    """
    LLM 驱动服务 - 封装大模型调用

    特点：
    - 统一日志（请求/响应/耗时/Token）
    - 统一异常（超时/API 错误/配额超限）
    - Mock 模式（无 API Key 时返回模板数据）
    - 发布 AIAnalysisCompletedEvent 事件
    """

    def __init__(self):
        self.mock_mode = True  # 默认 Mock，配置 API Key 后切换真实调用

    async def call_llm(self, prompt: str, system: str = "", max_tokens: int = 2000) -> str:
        """
        调用 LLM（Mock 或真实 API）

        日志覆盖：
        - 请求发送时间、prompt 长度
        - 响应时间、Token 消耗
        - 异常：超时 / API 错误 / 配额耗尽
        """
        from ....core.config import settings

        if not settings.LLM_API_URL or not settings.LLM_API_KEY:
            return await self._mock_response(prompt)

        start = time.time()
        prompt_len = len(prompt)

        logger.info(
            f"[LLM] 请求发送: prompt_len={prompt_len}, model={settings.LLM_MODEL}",
            extra={"action": "llm_request", "prompt_length": prompt_len}
        )

        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {
                    "model": settings.LLM_MODEL,
                    "messages": [],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                }
                if system:
                    payload["messages"].append({"role": "system", "content": system})
                payload["messages"].append({"role": "user", "content": prompt})

                headers = {
                    "Authorization": f"Bearer {settings.LLM_API_KEY}",
                    "Content-Type": "application/json",
                }

                async with session.post(settings.LLM_API_URL, json=payload, headers=headers) as resp:
                    elapsed_ms = (time.time() - start) * 1000

                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"[LLM] API 错误: HTTP {resp.status}",
                            extra={
                                "action": "llm_response",
                                "status_code": resp.status,
                                "duration_ms": round(elapsed_ms, 2),
                                "error": error_text[:500],
                            }
                        )
                        raise ExternalServiceException(
                            f"LLM API 返回错误: HTTP {resp.status}",
                            details={"status_code": resp.status, "response": error_text[:500]}
                        )

                    data = await resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    tokens = data.get("usage", {}).get("total_tokens", 0)

                    logger.info(
                        f"[LLM] 响应成功: tokens={tokens}, elapsed={elapsed_ms:.0f}ms",
                        extra={
                            "action": "llm_response",
                            "tokens": tokens,
                            "duration_ms": round(elapsed_ms, 2),
                        }
                    )

                    return content

        except ExternalServiceException:
            raise
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            logger.error(
                f"[LLM] 调用异常: {type(e).__name__}: {e}",
                extra={
                    "action": "llm_response",
                    "error": str(e),
                    "duration_ms": round(elapsed_ms, 2),
                },
                exc_info=True
            )
            raise ExternalServiceException(
                f"LLM 服务暂不可用: {type(e).__name__}",
                details={"error": str(e)[:500]}
            )

    async def _mock_response(self, prompt: str) -> str:
        """Mock 模式：返回结构化模板数据"""
        logger.info(f"[LLM] Mock 模式响应", extra={"action": "llm_mock"})
        return '{"mock": true, "message": "LLM API 未配置，使用模拟数据"}'


# 全局 LLM 服务实例
llm_service = LLMService()


# ==================== AI 分析接口 ====================

@router.post("/character")
async def analyze_characters(
    book_url: str,
    book_name: Optional[str] = None,
    sample_text: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """人物关系提取"""
    if not book_url:
        raise ValidationException("book_url 不能为空")

    start = time.time()
    logger.info(
        f"[AI] 人物关系分析请求: book={book_name or book_url}",
        extra={"action": "ai_character", "book_url": book_url}
    )

    chars = len(sample_text or "")
    await _check_ai_quota(auth, "ai_character", chars)

    try:
        prompt = f"分析小说《{book_name or ''}》的人物关系。\n书源URL: {book_url}\n"
        if sample_text:
            prompt += f"样本文本:\n{sample_text[:3000]}\n"
        prompt += "请以JSON格式输出人物关系图，包含人物名称、关系类型、关系描述。"

        result_text = await llm_service.call_llm(prompt, system="你是一个专业的小说分析助手，擅长提取人物关系。")

        # 发布事件
        elapsed = (time.time() - start) * 1000
        await publish_event(AIAnalysisCompletedEvent(
            analysis_type="character",
            book_url=book_url,
            book_name=book_name,
            chars_consumed=chars,
            status="success"
        ))

        logger.info(
            f"[AI] 人物关系分析完成: book={book_name}, elapsed={elapsed:.0f}ms",
            extra={"action": "ai_character", "book_url": book_url, "duration_ms": round(elapsed, 2)}
        )

        return ok({
            "book_url": book_url,
            "book_name": book_name,
            "characters": result_text,
            "mock": llm_service.mock_mode,
        })

    except QuotaExceededException:
        raise
    except Exception as e:
        logger.error(
            f"[AI] 人物关系分析失败: {type(e).__name__}: {e}",
            extra={"action": "ai_character", "book_url": book_url, "error": str(e)},
            exc_info=True
        )
        await publish_event(AIAnalysisCompletedEvent(
            analysis_type="character", book_url=book_url, book_name=book_name,
            chars_consumed=chars, status="error"
        ))
        raise ExternalServiceException(f"人物关系分析失败: {e}")


@router.post("/world")
async def analyze_world(
    book_url: str,
    book_name: Optional[str] = None,
    sample_text: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """世界观解析"""
    if not book_url:
        raise ValidationException("book_url 不能为空")

    logger.info(f"[AI] 世界观分析请求: book={book_name or book_url}", extra={"action": "ai_world", "book_url": book_url})

    chars = len(sample_text or "")
    await _check_ai_quota(auth, "ai_world", chars)

    try:
        prompt = f"分析小说《{book_name or ''}》的世界观设定。\n书源URL: {book_url}\n"
        if sample_text:
            prompt += f"样本文本:\n{sample_text[:3000]}\n"
        prompt += "请以JSON格式输出世界观设定，包含世界类型、核心规则、势力分布、地理结构等。"

        result_text = await llm_service.call_llm(prompt, system="你是一个专业的小说分析助手，擅长提取世界观设定。")

        await publish_event(AIAnalysisCompletedEvent(
            analysis_type="world", book_url=book_url, book_name=book_name,
            chars_consumed=chars, status="success"
        ))

        return ok({"book_url": book_url, "book_name": book_name, "world": result_text, "mock": llm_service.mock_mode})

    except QuotaExceededException:
        raise
    except Exception as e:
        logger.error(f"[AI] 世界观分析失败: {type(e).__name__}: {e}", extra={"action": "ai_world", "book_url": book_url, "error": str(e)}, exc_info=True)
        raise ExternalServiceException(f"世界观分析失败: {e}")


@router.post("/storyline")
async def analyze_storyline(
    book_url: str,
    book_name: Optional[str] = None,
    chapters: Optional[list] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """剧情时间线"""
    if not book_url:
        raise ValidationException("book_url 不能为空")

    logger.info(f"[AI] 剧情时间线请求: book={book_name or book_url}", extra={"action": "ai_storyline", "book_url": book_url})

    chars = sum(len(c) for c in (chapters or []))
    await _check_ai_quota(auth, "ai_storyline", chars)

    try:
        prompt = f"分析小说《{book_name or ''}》的剧情时间线。\n书源URL: {book_url}\n"
        if chapters:
            prompt += f"章节列表: {chapters[:20]}\n"
        prompt += "请以JSON格式输出剧情时间线，包含关键事件、时间节点、人物参与。"

        result_text = await llm_service.call_llm(prompt, system="你是一个专业的小说分析助手，擅长构建剧情时间线。")

        await publish_event(AIAnalysisCompletedEvent(
            analysis_type="storyline", book_url=book_url, book_name=book_name,
            chars_consumed=chars, status="success"
        ))

        return ok({"book_url": book_url, "book_name": book_name, "timeline": result_text, "mock": llm_service.mock_mode})

    except QuotaExceededException:
        raise
    except Exception as e:
        logger.error(f"[AI] 剧情分析失败: {type(e).__name__}: {e}", extra={"action": "ai_storyline", "book_url": book_url, "error": str(e)}, exc_info=True)
        raise ExternalServiceException(f"剧情分析失败: {e}")


@router.post("/chat")
async def ai_chat(
    book_url: str,
    question: str,
    context: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """智能问答"""
    if not question:
        raise ValidationException("question 不能为空")

    logger.info(f"[AI] 智能问答请求: book={book_url}, q={question[:50]}", extra={"action": "ai_chat", "book_url": book_url})

    chars = len(question) + len(context or "")
    await _check_ai_quota(auth, "ai_chat", chars)

    try:
        prompt = f"关于小说《{book_url}》的问题：{question}\n"
        if context:
            prompt += f"上下文：{context[:2000]}\n"

        answer = await llm_service.call_llm(prompt, system="你是一个小说阅读助手，根据提供的上下文回答问题。")

        await publish_event(AIAnalysisCompletedEvent(
            analysis_type="chat", book_url=book_url, book_name="",
            chars_consumed=chars, status="success"
        ))

        return ok({"book_url": book_url, "question": question, "answer": answer, "mock": llm_service.mock_mode})

    except QuotaExceededException:
        raise
    except Exception as e:
        logger.error(f"[AI] 问答失败: {type(e).__name__}: {e}", extra={"action": "ai_chat", "book_url": book_url, "error": str(e)}, exc_info=True)
        raise ExternalServiceException(f"智能问答失败: {e}")


@router.post("/fix")
async def fix_source(
    source_url: str,
    error_msg: Optional[str] = None,
    source_config: Optional[dict] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """书源修复建议"""
    if not source_url:
        raise ValidationException("source_url 不能为空")

    logger.info(f"[AI] 书源修复请求: url={source_url}", extra={"action": "ai_fix", "source_url": source_url})

    chars = 1000
    await _check_ai_quota(auth, "ai_fix", chars)

    try:
        prompt = f"书源URL: {source_url}\n"
        if error_msg:
            prompt += f"错误信息: {error_msg}\n"
        if source_config:
            import json
            prompt += f"当前配置:\n```json\n{json.dumps(source_config, ensure_ascii=False, indent=2)}\n```\n"
        prompt += "请分析问题并给出修复建议，以JSON格式输出修复后的配置和修复说明。"

        result = await llm_service.call_llm(prompt, system="你是 Legado 书源调试专家，擅长修复失效书源。")

        await publish_event(AIAnalysisCompletedEvent(
            analysis_type="fix", book_url=source_url, book_name="",
            chars_consumed=chars, status="success"
        ))

        return ok({"source_url": source_url, "suggestions": result, "mock": llm_service.mock_mode})

    except QuotaExceededException:
        raise
    except Exception as e:
        logger.error(f"[AI] 修复分析失败: {type(e).__name__}: {e}", extra={"action": "ai_fix", "source_url": source_url, "error": str(e)}, exc_info=True)
        raise ExternalServiceException(f"书源修复分析失败: {e}")


@router.post("/review")
async def review_content(
    text: str,
    auth: AuthContext = Depends(get_auth_context)
):
    """内容合规审查"""
    if not text:
        raise ValidationException("text 不能为空")

    logger.info(f"[AI] 内容审查请求: text_len={len(text)}", extra={"action": "ai_review"})

    chars = len(text)
    await _check_ai_quota(auth, "ai_chat", chars)

    try:
        prompt = f"请审查以下内容的合规性，检查是否包含违法、暴力、色情等不当内容。\n\n内容:\n{text[:5000]}"
        result = await llm_service.call_llm(prompt, system="你是内容安全审查助手，判断文本是否合规。")

        await publish_event(AIAnalysisCompletedEvent(
            analysis_type="review", book_url="", book_name="",
            chars_consumed=chars, status="success"
        ))

        return ok({"review": result, "mock": llm_service.mock_mode})

    except QuotaExceededException:
        raise
    except Exception as e:
        logger.error(f"[AI] 内容审查失败: {type(e).__name__}: {e}", extra={"action": "ai_review", "error": str(e)}, exc_info=True)
        raise ExternalServiceException(f"内容审查失败: {e}")


# ==================== 查询接口 ====================

@router.get("/character/{book_url:path}")
async def get_character_result(book_url: str, auth: AuthContext = Depends(get_auth_context)):
    """获取人物关系缓存结果"""
    from ....database import SessionLocal, AICharacterResultModel
    db = SessionLocal()
    try:
        result = db.query(AICharacterResultModel).filter(AICharacterResultModel.book_url == book_url).first()
        if not result:
            raise NotFoundException(f"未找到 {book_url} 的人物关系分析结果")
        return ok({"characters_json": result.characters_json, "graph_data": result.graph_data})
    finally:
        db.close()


@router.get("/world/{book_url:path}")
async def get_world_result(book_url: str, auth: AuthContext = Depends(get_auth_context)):
    """获取世界观缓存结果"""
    from ....database import SessionLocal, AIWorldResultModel
    db = SessionLocal()
    try:
        result = db.query(AIWorldResultModel).filter(AIWorldResultModel.book_url == book_url).first()
        if not result:
            raise NotFoundException(f"未找到 {book_url} 的世界观分析结果")
        return ok({"world_json": result.world_json})
    finally:
        db.close()


@router.get("/storyline/{book_url:path}")
async def get_storyline_result(book_url: str, auth: AuthContext = Depends(get_auth_context)):
    """获取剧情时间线缓存结果"""
    from ....database import SessionLocal, AIStorylineResultModel
    db = SessionLocal()
    try:
        result = db.query(AIStorylineResultModel).filter(AIStorylineResultModel.book_url == book_url).first()
        if not result:
            raise NotFoundException(f"未找到 {book_url} 的剧情时间线分析结果")
        return ok({"timeline_json": result.timeline_json})
    finally:
        db.close()


# ==================== 内部函数 ====================

async def _check_ai_quota(auth: AuthContext, metric: str, chars: int):
    """检查 AI 配额，不足则发布告警事件并抛出异常"""
    if not auth.api_key:
        return

    # 检查每日配额
    today_usage = await redis_client.get_quota(auth.api_key.id, "ai_chars")
    limit = auth.api_key.daily_ai_quota

    if today_usage + chars > limit:
        logger.warning(
            f"[AI] 配额超限: key={auth.api_key.id}, used={today_usage}, limit={limit}, need={chars}",
            extra={"action": "quota_check", "api_key_id": auth.api_key.id, "metric": "ai_chars"}
        )
        await publish_event(QuotaExceededEvent(
            api_key_id=auth.api_key.id,
            metric="ai_chars",
            used=today_usage,
            limit=limit
        ))
        raise QuotaExceededException(
            f"AI 配额已用完 (已使用 {today_usage}/{limit})",
            details={"used": today_usage, "limit": limit, "requested": chars}
        )

    # 记录配额使用
    await redis_client.increment_quota(auth.api_key.id, "ai_chars", chars)

    logger.debug(
        f"[AI] 配额记录: key={auth.api_key.id}, +{chars}, total={today_usage + chars}/{limit}",
        extra={"action": "quota_record", "api_key_id": auth.api_key.id, "amount": chars}
    )


# ==================== NovelAgent 智能体接口 ====================
# 参考 DeepSeek-Reasonix 架构模式

_agent_instance = None


def get_agent():
    """获取全局 Agent 实例（单例模式）"""
    global _agent_instance
    if _agent_instance is None:
        try:
            from ....services.novel_agent import NovelAgent, AgentConfig, MCPInterface
            config = AgentConfig()
            _agent_instance = {
                'agent': NovelAgent(config=config),
                'mcp': None,
            }
            _agent_instance['mcp'] = MCPInterface(_agent_instance['agent'])
        except Exception as e:
            logger.error(f"[Agent] 初始化失败: {e}", exc_info=True)
            return None
    return _agent_instance


@router.post("/agent/chat")
async def agent_chat(
    message: str,
    book_url: Optional[str] = None,
    chapters_data: Optional[list] = None,
    graph_data: Optional[dict] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """NovelAgent 智能体对话

    参考 DeepSeek-Reasonix 的 ReAct 模式：
    - Think: 分析目标，制定计划
    - Act: 调用工具执行
    - Observe: 观察结果，生成回答
    """
    if not message:
        raise ValidationException("message 不能为空")

    logger.info(
        f"[Agent] 对话请求: msg={message[:50]}",
        extra={"action": "agent_chat", "message_len": len(message)}
    )

    agent_data = get_agent()
    if not agent_data:
        raise ExternalServiceException("NovelAgent 初始化失败")

    agent = agent_data['agent']

    if chapters_data and graph_data:
        try:
            agent.store.load_from_json(chapters_data, graph_data)
        except Exception as e:
            logger.error(f"[Agent] 数据加载失败: {e}", exc_info=True)

    start = time.time()
    try:
        response = agent.run(message)
        elapsed = (time.time() - start) * 1000

        logger.info(
            f"[Agent] 对话完成: tools={len(response.tools_used)}, elapsed={elapsed:.0f}ms",
            extra={
                "action": "agent_chat_done",
                "tools_used": response.tools_used,
                "iterations": response.iterations,
                "duration_ms": round(elapsed, 2),
            }
        )

        return ok({
            "answer": response.answer,
            "thought": response.steps[0].thought if response.steps else "",
            "tools_used": response.tools_used,
            "iterations": response.iterations,
            "confidence": response.confidence,
            "steps": [
                {
                    "step": s.step,
                    "tool": s.tool,
                    "thought": s.thought,
                    "observation": s.observation,
                    "error": s.error,
                }
                for s in response.steps
            ],
            "mock": llm_service.mock_mode,
        })

    except Exception as e:
        logger.error(f"[Agent] 对话失败: {e}", exc_info=True)
        raise ExternalServiceException(f"Agent 对话失败: {e}")


@router.get("/agent/tools")
async def agent_tools(
    auth: AuthContext = Depends(get_auth_context)
):
    """获取 Agent 可用工具列表"""
    agent_data = get_agent()
    if not agent_data:
        raise ExternalServiceException("NovelAgent 初始化失败")

    tools = agent_data['agent'].list_available_tools()
    skills = agent_data['agent'].list_available_skills()

    return ok({
        "skills": skills,
        "tools": tools,
        "tool_count": len(tools),
        "skill_count": len(skills),
    })


@router.get("/agent/stats")
async def agent_stats(
    auth: AuthContext = Depends(get_auth_context)
):
    """获取 Agent 统计信息"""
    agent_data = get_agent()
    if not agent_data:
        raise ExternalServiceException("NovelAgent 初始化失败")

    stats = agent_data['agent'].get_stats()
    return ok(stats)


@router.post("/agent/load_data")
async def agent_load_data(
    chapters: list,
    graph: Optional[dict] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """加载小说数据到 Agent 中"""
    if not chapters:
        raise ValidationException("chapters 不能为空")

    agent_data = get_agent()
    if not agent_data:
        raise ExternalServiceException("NovelAgent 初始化失败")

    try:
        agent_data['agent'].store.load_from_json(chapters, graph)
        stats = agent_data['agent'].store.stats()
        return ok({
            "status": "success",
            "message": "数据加载成功",
            "stats": stats,
        })
    except Exception as e:
        logger.error(f"[Agent] 数据加载失败: {e}", exc_info=True)
        raise ExternalServiceException(f"数据加载失败: {e}")


@router.post("/agent/mcp/tools")
async def agent_mcp_tools(
    auth: AuthContext = Depends(get_auth_context)
):
    """MCP 协议：列出工具（tools/list）"""
    agent_data = get_agent()
    if not agent_data or not agent_data['mcp']:
        raise ExternalServiceException("NovelAgent MCP 初始化失败")

    result = agent_data['mcp'].list_tools()
    return ok(result)


@router.post("/agent/mcp/call")
async def agent_mcp_call(
    tool_name: str,
    arguments: Optional[dict] = None,
    auth: AuthContext = Depends(get_auth_context)
):
    """MCP 协议：调用工具（tools/call）"""
    if not tool_name:
        raise ValidationException("tool_name 不能为空")

    agent_data = get_agent()
    if not agent_data or not agent_data['mcp']:
        raise ExternalServiceException("NovelAgent MCP 初始化失败")

    try:
        result = agent_data['mcp'].call_tool(tool_name, arguments or {})
        return ok(result)
    except Exception as e:
        logger.error(f"[Agent] MCP 工具调用失败: {e}", exc_info=True)
        raise ExternalServiceException(f"工具调用失败: {e}")


@router.post("/agent/generate_graph")
async def agent_generate_graph(
    output_path: Optional[str] = "data/graph.html",
    auth: AuthContext = Depends(get_auth_context)
):
    """生成关系图谱 HTML"""
    agent_data = get_agent()
    if not agent_data:
        raise ExternalServiceException("NovelAgent 初始化失败")

    try:
        result = agent_data['agent'].registry.call(
            'generate_graph_html',
            output_path=output_path
        )
        return ok(result)
    except Exception as e:
        logger.error(f"[Agent] 图谱生成失败: {e}", exc_info=True)
        raise ExternalServiceException(f"图谱生成失败: {e}")


@router.post("/agent/audit")
async def agent_audit(
    min_confidence: Optional[float] = 0.5,
    auth: AuthContext = Depends(get_auth_context)
):
    """执行图谱质量审计"""
    agent_data = get_agent()
    if not agent_data:
        raise ExternalServiceException("NovelAgent 初始化失败")

    try:
        conflicts = agent_data['agent'].registry.call('detect_conflicts')
        stats = agent_data['agent'].registry.call('graph_stats')
        audit_all = agent_data['agent'].registry.call('audit_all', min_confidence=min_confidence)

        return ok({
            "conflicts": conflicts,
            "stats": stats,
            "low_confidence_issues": audit_all,
            "total_issues": conflicts.get('total', 0) + audit_all.get('total', 0),
        })
    except Exception as e:
        logger.error(f"[Agent] 审计失败: {e}", exc_info=True)
        raise ExternalServiceException(f"审计失败: {e}")
