"""
NovelAgent API v1 - 小说智能体接口

提供小说领域智能体的 RESTful API：
- 对话问答
- 工具调用
- OCR 识别
- 书源管理
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from ...core.response import ok, fail, paginated
from ...core.logging import get_logger
from ...application.services.novel_agent_service import NovelAgentAppService

logger = get_logger("api.v1.novel_agent")

router = APIRouter(prefix="/api/v1/novel-agent", tags=["NovelAgent"])


# ==================== 请求/响应模型 ====================

class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息", min_length=1)
    use_reasonix: bool = Field(False, description="是否使用 Reasonix 模式（需要 LLM）")
    session_id: Optional[str] = Field(None, description="会话 ID")


class ToolCallRequest(BaseModel):
    tool_name: str = Field(..., description="工具名称")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="工具参数")


# ==================== 对话接口 ====================

@router.post("/chat", summary="与智能体对话")
async def chat(req: ChatRequest):
    """
    与小说智能体对话

    - 支持书源查找、小说分析、关系图谱、OCR 等能力
    - 基础模式：规则驱动，无需 LLM
    - Reasonix 模式：LLM 驱动，需要配置 LLM_API
    """
    try:
        service = NovelAgentAppService()
        result = await service.chat(
            message=req.message,
            use_reasonix=req.use_reasonix,
            session_id=req.session_id,
        )
        return ok(
            data={
                "answer": result.answer,
                "tools_used": result.tools_used,
                "iterations": result.iterations,
                "confidence": result.confidence,
            },
            message="对话完成",
        )
    except Exception as e:
        logger.error(f"[API] 对话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 工具接口 ====================

@router.get("/tools", summary="列出可用工具")
async def list_tools(skill: Optional[str] = Query(None, description="按技能筛选")):
    """列出智能体所有可用工具"""
    try:
        service = NovelAgentAppService()
        tools = await service.list_tools(skill)
        return ok(data=tools, message=f"共 {len(tools)} 个工具")
    except Exception as e:
        logger.error(f"[API] 工具列表获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tools/call", summary="调用指定工具")
async def call_tool(req: ToolCallRequest):
    """直接调用指定工具"""
    try:
        service = NovelAgentAppService()
        result = await service.call_tool(req.tool_name, req.params)
        return ok(data=result, message=f"工具 {req.tool_name} 执行完成")
    except Exception as e:
        logger.error(f"[API] 工具调用失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== OCR 接口 ====================

@router.post("/ocr", summary="OCR 文字识别")
async def ocr_recognize(
    file: UploadFile = File(..., description="图片文件"),
    backend: str = Form("paddleocr", description="OCR 后端: paddleocr/manga-ocr/easyocr"),
):
    """
    上传图片进行 OCR 文字识别

    支持的后端：
    - paddleocr: 通用中英文识别（默认）
    - manga-ocr: 漫画气泡专用
    - easyocr: 多语言识别
    """
    try:
        contents = await file.read()
        if not contents:
            return fail(message="文件为空")

        service = NovelAgentAppService()
        result = await service.ocr_recognize(
            image_data=contents,
            backend=backend,
        )

        if not result.get("success"):
            return fail(message=result.get("error", "OCR 识别失败"))

        return ok(
            data=result,
            message=f"识别完成，共 {len(result.get('lines', []))} 行",
        )
    except Exception as e:
        logger.error(f"[API] OCR 识别失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 书源接口 ====================

@router.get("/sources", summary="获取书源列表")
async def list_sources(
    keyword: Optional[str] = Query(None, description="关键词过滤"),
    group: Optional[str] = Query(None, description="分组过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
):
    """获取书源列表"""
    try:
        service = NovelAgentAppService()
        sources = await service.source_list(keyword=keyword, group=group)

        # 简单分页
        total = len(sources)
        start = (page - 1) * page_size
        end = start + page_size
        paged = sources[start:end]

        return paginated(
            items=paged,
            total=total,
            page=page,
            page_size=page_size,
            message=f"共 {total} 个书源",
        )
    except Exception as e:
        logger.error(f"[API] 书源列表获取失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 健康检查 ====================

@router.get("/health", summary="智能体健康检查")
async def health():
    """检查智能体服务状态"""
    try:
        service = NovelAgentAppService()
        result = await service.health_check()
        return ok(data=result, message="NovelAgent 运行中")
    except Exception as e:
        logger.error(f"[API] 健康检查失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 书源互补 ====================

class ComplementChapterRequest(BaseModel):
    book_name: str = Field(..., description="书名", min_length=1)
    chapter_title: str = Field(..., description="章节标题", min_length=1)
    chapter_num: int = Field(..., description="章节序号", ge=0)
    source_urls: List[str] = Field(..., description="互补书源 URL 列表", min_length=1)
    reference_content: Optional[str] = Field("", description="参考内容（当前已有内容）")
    strategy: Optional[str] = Field("hybrid", description="合并策略：best/majority/hybrid")
    max_concurrent: Optional[int] = Field(5, description="最大并发请求数", ge=1, le=20)


@router.post("/complement", summary="书源章节互补")
async def complement_chapter(req: ComplementChapterRequest):
    """
    书源章节内容互补

    服务端并行请求多个书源的对应章节，对比合并后输出最高质量的内容：
    - **事件驱动**：基于事件总线，支持异步进度通知
    - **并行抓取**：多源同时请求，带并发控制和超时保护
    - **智能合并**：多策略内容对比，取最优/多数一致内容
    - **质量评估**：字数、段落、广告占比、完整度多维度评分

    合并策略：
    - `best`：取质量评分最高的单源内容
    - `majority`：多数投票，内容最相似的聚类中取最优
    - `hybrid`：混合策略（推荐），先取高质量 top 再聚类投票
    """
    try:
        service = NovelAgentAppService()
        result = await service.complement_chapter(
            book_name=req.book_name,
            chapter_title=req.chapter_title,
            chapter_num=req.chapter_num,
            source_urls=req.source_urls,
            reference_content=req.reference_content,
            strategy=req.strategy,
            max_concurrent=req.max_concurrent,
        )
        return ok(data=result, message=f"互补完成，状态：{result['status']}")
    except Exception as e:
        logger.error(f"[API] 书源互补失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
