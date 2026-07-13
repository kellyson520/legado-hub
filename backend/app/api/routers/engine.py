from fastapi import APIRouter
from ..models import ApiResponse, GenerateSourceRequest
from ..services.generator import SourceGenerator

router = APIRouter(prefix="/api/engine", tags=["engine"])

generator = SourceGenerator()

@router.post("/generate", response_model=ApiResponse)
async def generate_source(req: GenerateSourceRequest):
    """自动写源引擎 - 根据 URL 生成源"""
    result = await generator.generate(req.url, req.sourceType, req.sourceName)
    return ApiResponse(
        success=result["success"],
        message=result["message"],
        data={
            "source": result.get("source"),
            "logs": result.get("logs", [])
        }
    )
