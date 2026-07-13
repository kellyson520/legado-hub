"""
写源引擎接口层 (v0 - 兼容 API)
"""

from fastapi import APIRouter, Depends

from ....core.response import ok, fail
from ....services.generator import SourceGenerator
from ....core.compatibility import compat_engine
from ....core.dependencies import get_auth_context, AuthContext
from ....application.services import SourceAppService
from ..dependencies import get_source_service

router = APIRouter(prefix="/api/engine", tags=["engine"])

generator = SourceGenerator()


@router.post("/generate")
async def generate_source(
    req: dict,
    auth: AuthContext = Depends(get_auth_context),
    svc: SourceAppService = Depends(get_source_service)
):
    """
    自动写源引擎 - 根据 URL 智能生成书源
    
    流程：
    1. 尝试 AI/爬虫自动解析页面结构
    2. 若自动解析不充分，使用兼容性规则兜底
    3. 最终返回完整书源配置
    """
    logs = []
    url = req.get("url", "")
    source_type = req.get("sourceType", "book")
    source_name = req.get("sourceName", "")
    
    # 步骤1: 尝试自动解析
    from ....models import GenerateSourceRequest
    gen_req = GenerateSourceRequest(url=url, sourceType=source_type, sourceName=source_name)
    result = await generator.generate(gen_req.url, gen_req.sourceType, gen_req.sourceName)
    logs.extend(result.get("logs", []))
    
    source = result.get("source")
    
    # 步骤2: 评估自动生成的质量
    if source:
        score_info = compat_engine.get_compatibility_score(source)
        logs.append(f"自动解析兼容性评分: {score_info['grade']} ({score_info['score']}/100)")
        
        if score_info["score"] < 70:
            logs.append("自动解析质量不足，启用兼容性规则兜底...")
            fallback = compat_engine.generate_from_url(url, source_name)
            for key, value in fallback.items():
                if not source.get(key) or source.get(key) == "":
                    source[key] = value
                    logs.append(f"  补充字段: {key}")
            score_info = compat_engine.get_compatibility_score(source)
            logs.append(f"兜底后评分: {score_info['grade']} ({score_info['score']}/100)")
    else:
        logs.append("自动解析失败，使用兼容性规则生成...")
        source = compat_engine.generate_from_url(url, source_name)
        score_info = compat_engine.get_compatibility_score(source)
        logs.append(f"兜底评分: {score_info['grade']} ({score_info['score']}/100)")
    
    # 步骤3: 自动修复
    if source:
        repaired = compat_engine.repair_source(source)
        if repaired.get("_fixes"):
            logs.append(f"自动修复 {len(repaired['_fixes'])} 个问题")
            source = {k: v for k, v in repaired.items() if not k.startswith("_")}
    
    # 步骤4: 自动保存
    if source and auth.can_edit_source and score_info.get("is_usable"):
        try:
            existing = await svc._repo.get_book_source(source["bookSourceUrl"])
            if not existing:
                from ....domain.entities.source import BookSource as BookSourceEntity
                entity = BookSourceEntity.from_dict(source)
                await svc._repo.save_book_source(entity)
                logs.append("书源已自动保存到数据库")
        except Exception as e:
            logs.append(f"自动保存失败: {e}")
    
    return ok({
        "source": source,
        "logs": logs,
        "compatibility": score_info
    }, result.get("message", "") if source else "使用兼容性规则生成")


@router.post("/repair")
async def repair_existing_source(source: dict):
    """修复已有书源"""
    score_before = compat_engine.get_compatibility_score(source)
    repaired = compat_engine.repair_source(source)
    fixes = repaired.pop("_fixes", [])
    score_after = compat_engine.get_compatibility_score(repaired)
    
    return ok({
        "source": repaired,
        "fixes": fixes,
        "score_before": score_before,
        "score_after": score_after
    })


@router.post("/evaluate")
async def evaluate_source(source: dict):
    """评估书源兼容性"""
    score_info = compat_engine.get_compatibility_score(source)
    return ok(score_info)
