import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db, AICharacterResultModel, AIWorldResultModel, AIStorylineResultModel, BookSourceModel
from ..models import ApiResponse
from ..core.dependencies import get_auth_context, require_permission, AuthContext
from ..core.config import settings
from ..core.redis_client import redis_client

router = APIRouter(prefix="/api/v1/llm", tags=["ai"])


# ==================== Mock AI Service (Framework) ====================
# 当未配置真实 LLM 时，返回结构化模板数据供前端展示和测试
# 生产环境可替换为真实大模型调用

class MockAIService:
    """AI 服务框架 - 未配置 LLM 时返回模拟数据"""
    
    @staticmethod
    def parse_characters(book_name: str, sample_text: str = "") -> dict:
        return {
            "book_name": book_name,
            "characters": [
                {
                    "name": "主角",
                    "identity": "主要人物",
                    "faction": "正道",
                    "relations": [
                        {"target": "师父", "type": "师徒", "sentiment": "敬爱"},
                        {"target": "反派", "type": "敌对", "sentiment": "仇恨"}
                    ],
                    "traits": ["坚韧", "聪明", "正义感"]
                },
                {
                    "name": "师父",
                    "identity": "引导者",
                    "faction": "正道",
                    "relations": [
                        {"target": "主角", "type": "师徒", "sentiment": "关爱"}
                    ],
                    "traits": ["睿智", "沉稳", "严厉"]
                },
                {
                    "name": "反派",
                    "identity": "主要对手",
                    "faction": "魔道",
                    "relations": [
                        {"target": "主角", "type": "敌对", "sentiment": "嫉妒"}
                    ],
                    "traits": ["阴险", "野心勃勃", "强大"]
                }
            ],
            "graph": {
                "nodes": [
                    {"id": " protagonist", "label": "主角", "group": "正道"},
                    {"id": "master", "label": "师父", "group": "正道"},
                    {"id": "villain", "label": "反派", "group": "魔道"}
                ],
                "edges": [
                    {"from": "protagonist", "to": "master", "label": "师徒", "arrows": "to"},
                    {"from": "protagonist", "to": "villain", "label": "敌对", "arrows": "to,from"}
                ]
            }
        }
    
    @staticmethod
    def parse_world(book_name: str) -> dict:
        return {
            "book_name": book_name,
            "world": {
                "name": f"{book_name}世界",
                "era": "架空时代",
                "geography": {
                    "continents": ["东大陆", "西大陆"],
                    "important_locations": [
                        {"name": "青云山", "type": "修炼圣地", "description": "正道第一大派所在地"},
                        {"name": "幽冥谷", "type": "禁地", "description": "魔道势力聚集地"}
                    ]
                },
                "power_system": {
                    "name": "修真体系",
                    "levels": ["练气", "筑基", "金丹", "元婴", "化神", "渡劫", "大乘"],
                    "description": "通过吸收天地灵气提升境界"
                },
                "factions": [
                    {"name": "青云门", "type": "正道", "strength": "天下第一"},
                    {"name": "幽冥宗", "type": "魔道", "strength": "势力庞大"}
                ],
                "races": ["人族", "妖族", "魔族"],
                "rules": ["弱肉强食", "实力为尊", "因果轮回"]
            }
        }
    
    @staticmethod
    def parse_storyline(book_name: str) -> dict:
        return {
            "book_name": book_name,
            "timeline": [
                {
                    "chapter": "开篇",
                    "title": "命运转折",
                    "events": ["主角出身平凡", "偶遇机缘", "踏上修炼之路"],
                    "importance": "high",
                    "foreshadowing": ["师父身份之谜", "体内神秘力量"]
                },
                {
                    "chapter": "中期",
                    "title": "宗门大比",
                    "events": ["崭露头角", "结识挚友", "与反派首次交锋"],
                    "importance": "high",
                    "foreshadowing": ["反派背后势力", "秘境开启预告"]
                },
                {
                    "chapter": "后期",
                    "title": "正邪大战",
                    "events": ["师门遭难", "实力突破", "揭开真相"],
                    "importance": "high",
                    "foreshadowing": ["最终BOSS身份", "世界法则之谜"]
                }
            ],
            "main_arc": "从凡人成长为拯救世界的强者",
            "sub_arcs": ["师徒情深", "兄弟情义", "爱恨纠葛"],
            "key_turning_points": ["获得传承", "师门覆灭", "正邪对决"]
        }
    
    @staticmethod
    def fix_source(source: dict, error_msg: str) -> dict:
        return {
            "analysis": f"检测到错误: {error_msg}",
            "suggestions": [
                "检查 searchUrl 是否包含正确的搜索参数",
                "验证 ruleSearch.bookList 选择器是否能匹配结果列表",
                "确认章节链接是否使用了正确的相对路径处理"
            ],
            "fixed_rules": {
                "searchUrl": source.get("searchUrl", "") + " || 建议添加搜索参数",
                "ruleSearch": source.get("ruleSearch", {}) or {"bookList": "建议检查选择器"}
            }
        }
    
    @staticmethod
    def review_content(text: str) -> dict:
        return {
            "sensitive_score": 0.1,
            "classification": "正常内容",
            "flags": [],
            "summary": "内容检测通过，未发现敏感信息"
        }
    
    @staticmethod
    def chat(book_name: str, question: str) -> dict:
        return {
            "question": question,
            "answer": f"根据《{book_name}》的内容，这是一个关于该作品的测试回答。实际生产环境将接入真实大模型进行智能问答。",
            "sources": ["小说原文", "人物设定"],
            "confidence": 0.85
        }


async def _record_ai_usage(db: Session, auth: AuthContext, action: str, chars: int = 0):
    """记录 AI 调用配额（Redis 实时计数 + DB 持久化）"""
    if not auth.api_key:
        return
    
    # Redis 实时增加
    await redis_client.increment_quota(auth.api_key.id, "ai_chars", chars)
    
    # 数据库持久化（异步降级）
    from ..database import QuotaUsageModel
    from datetime import datetime
    today = datetime.utcnow().strftime("%Y-%m-%d")
    usage = db.query(QuotaUsageModel).filter(
        QuotaUsageModel.api_key_id == auth.api_key.id,
        QuotaUsageModel.date == today
    ).first()
    if not usage:
        usage = QuotaUsageModel(api_key_id=auth.api_key.id, date=today, ai_chars=chars)
        db.add(usage)
    else:
        usage.ai_chars = (usage.ai_chars or 0) + chars
    db.commit()


# ==================== AI APIs ====================

@router.post("/character", response_model=ApiResponse)
async def ai_character(
    book_url: str,
    book_name: Optional[str] = None,
    sample_text: Optional[str] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("use_ai_character"))
):
    """AI 提取小说人物关系"""
    await _record_ai_usage(db, auth, "character", len(sample_text or ""))
    
    result = MockAIService.parse_characters(book_name or "未知书籍", sample_text or "")
    
    # 保存结果
    record = AICharacterResultModel(
        book_url=book_url,
        book_name=book_name,
        characters_json=result["characters"],
        graph_data=result.get("graph"),
        created_by=auth.user.id if auth.user else None
    )
    db.add(record)
    db.commit()
    
    return ApiResponse(data=result, message="Character analysis complete")


@router.post("/world", response_model=ApiResponse)
async def ai_world(
    book_url: str,
    book_name: Optional[str] = None,
    sample_text: Optional[str] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("use_ai_world"))
):
    """AI 解析小说世界观设定"""
    await _record_ai_usage(db, auth, "world", len(sample_text or ""))
    
    result = MockAIService.parse_world(book_name or "未知书籍")
    
    record = AIWorldResultModel(
        book_url=book_url,
        book_name=book_name,
        world_json=result["world"],
        created_by=auth.user.id if auth.user else None
    )
    db.add(record)
    db.commit()
    
    return ApiResponse(data=result, message="World analysis complete")


@router.post("/storyline", response_model=ApiResponse)
async def ai_storyline(
    book_url: str,
    book_name: Optional[str] = None,
    chapters: Optional[List[str]] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("use_ai_storyline"))
):
    """AI 生成剧情时间线"""
    await _record_ai_usage(db, auth, "storyline", sum(len(c) for c in (chapters or [])))
    
    result = MockAIService.parse_storyline(book_name or "未知书籍")
    
    record = AIStorylineResultModel(
        book_url=book_url,
        book_name=book_name,
        timeline_json=result["timeline"],
        created_by=auth.user.id if auth.user else None
    )
    db.add(record)
    db.commit()
    
    return ApiResponse(data=result, message="Storyline analysis complete")


@router.post("/review", response_model=ApiResponse)
async def ai_review(
    text: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("use_ai_chat"))
):
    """AI 全文内容合规审查"""
    await _record_ai_usage(db, auth, "review", len(text))
    result = MockAIService.review_content(text)
    return ApiResponse(data=result, message="Content review complete")


@router.post("/chat", response_model=ApiResponse)
async def ai_chat(
    book_url: str,
    question: str,
    book_name: Optional[str] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("use_ai_chat"))
):
    """小说智能问答"""
    await _record_ai_usage(db, auth, "chat", len(question))
    result = MockAIService.chat(book_name or "未知书籍", question)
    return ApiResponse(data=result, message="Chat response generated")


@router.post("/fix", response_model=ApiResponse)
async def ai_fix_source(
    source_url: str,
    error_message: Optional[str] = None,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(require_permission("use_ai_fix"))
):
    """AI 修复失效书源"""
    source = db.query(BookSourceModel).filter(BookSourceModel.bookSourceUrl == source_url).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    
    source_dict = {k: v for k, v in source.__dict__.items() if not k.startswith("_")}
    result = MockAIService.fix_source(source_dict, error_message or "Unknown error")
    
    await _record_ai_usage(db, auth, "fix", 1000)
    return ApiResponse(data=result, message="Source fix suggestions generated")


# ==================== Query Results ====================

@router.get("/character/{book_url:path}", response_model=ApiResponse)
async def get_character_result(
    book_url: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context)
):
    record = db.query(AICharacterResultModel).filter(AICharacterResultModel.book_url == book_url).order_by(
        AICharacterResultModel.id.desc()
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="No character analysis found")
    return ApiResponse(data={
        "book_name": record.book_name,
        "characters": record.characters_json,
        "graph": record.graph_data
    })


@router.get("/world/{book_url:path}", response_model=ApiResponse)
async def get_world_result(
    book_url: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context)
):
    record = db.query(AIWorldResultModel).filter(AIWorldResultModel.book_url == book_url).order_by(
        AIWorldResultModel.id.desc()
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="No world analysis found")
    return ApiResponse(data={
        "book_name": record.book_name,
        "world": record.world_json
    })


@router.get("/storyline/{book_url:path}", response_model=ApiResponse)
async def get_storyline_result(
    book_url: str,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context)
):
    record = db.query(AIStorylineResultModel).filter(AIStorylineResultModel.book_url == book_url).order_by(
        AIStorylineResultModel.id.desc()
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="No storyline analysis found")
    return ApiResponse(data={
        "book_name": record.book_name,
        "timeline": record.timeline_json
    })
