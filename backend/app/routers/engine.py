from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..models import ApiResponse, GenerateSourceRequest
from ..services.generator import SourceGenerator
from ..core.compatibility import compat_engine
from ..database import get_db, BookSourceModel
from ..core.dependencies import get_auth_context, AuthContext

router = APIRouter(prefix="/api/engine", tags=["engine"])

generator = SourceGenerator()

@router.post("/generate", response_model=ApiResponse)
async def generate_source(
    req: GenerateSourceRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context)
):
    """
    自动写源引擎 - 根据 URL 智能生成书源
    
    流程：
    1. 尝试 AI/爬虫自动解析页面结构
    2. 若自动解析不充分，使用兼容性规则兜底
    3. 最终返回完整书源配置
    """
    logs = []
    
    # 步骤1: 尝试自动解析
    result = await generator.generate(req.url, req.sourceType, req.sourceName)
    logs.extend(result.get("logs", []))
    
    source = result.get("source")
    
    # 步骤2: 评估自动生成的质量
    if source:
        score_info = compat_engine.get_compatibility_score(source)
        logs.append(f"自动解析兼容性评分: {score_info['grade']} ({score_info['score']}/100)")
        
        if score_info["score"] < 70:
            # 质量不够，使用兼容性规则兜底
            logs.append("自动解析质量不足，启用兼容性规则兜底...")
            fallback = compat_engine.generate_from_url(req.url, req.sourceName)
            
            # 合并：自动解析的 + 兜底补充的
            for key, value in fallback.items():
                if not source.get(key) or source.get(key) == "":
                    source[key] = value
                    logs.append(f"  补充字段: {key}")
            
            # 再次评估
            score_info = compat_engine.get_compatibility_score(source)
            logs.append(f"兜底后评分: {score_info['grade']} ({score_info['score']}/100)")
    else:
        # 完全失败，直接使用兜底
        logs.append("自动解析失败，使用兼容性规则生成...")
        source = compat_engine.generate_from_url(req.url, req.sourceName)
        score_info = compat_engine.get_compatibility_score(source)
        logs.append(f"兜底评分: {score_info['grade']} ({score_info['score']}/100)")
    
    # 步骤3: 自动修复常见问题
    if source:
        repaired = compat_engine.repair_source(source)
        if repaired.get("_fixes"):
            logs.append(f"自动修复 {len(repaired['_fixes'])} 个问题:")
            for fix in repaired["_fixes"]:
                logs.append(f"  - {fix}")
            source = {k: v for k, v in repaired.items() if not k.startswith("_")}
    
    # 步骤4: 如果用户有权限，自动保存到数据库
    if source and auth.can_edit_source and score_info.get("is_usable"):
        try:
            existing = db.query(BookSourceModel).filter(
                BookSourceModel.bookSourceUrl == source["bookSourceUrl"]
            ).first()
            if not existing:
                new_source = BookSourceModel(**source)
                db.add(new_source)
                db.commit()
                logs.append("书源已自动保存到数据库")
        except Exception as e:
            logs.append(f"自动保存失败: {e}")
    
    return ApiResponse(
        success=source is not None and score_info.get("is_usable", False),
        message=result.get("message", "") if source else "使用兼容性规则生成",
        data={
            "source": source,
            "logs": logs,
            "compatibility": score_info
        }
    )


@router.post("/repair", response_model=ApiResponse)
async def repair_existing_source(source: dict):
    """修复已有书源的常见问题"""
    score_before = compat_engine.get_compatibility_score(source)
    repaired = compat_engine.repair_source(source)
    fixes = repaired.pop("_fixes", [])
    score_after = compat_engine.get_compatibility_score(repaired)
    
    return ApiResponse(data={
        "source": repaired,
        "fixes": fixes,
        "score_before": score_before,
        "score_after": score_after
    })


@router.post("/evaluate", response_model=ApiResponse)
async def evaluate_source(source: dict):
    """评估书源兼容性得分"""
    score_info = compat_engine.get_compatibility_score(source)
    return ApiResponse(data=score_info)
