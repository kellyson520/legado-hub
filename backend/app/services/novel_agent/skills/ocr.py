"""
OCR 技能 - OCR Skill

轻量包装层，调用底层 OCR 基础设施。
不包含具体 OCR 实现，只做参数转换和结果格式化。

架构原则（参考 OpenClaw）：
- 能力下沉到底层 infrastructure
- Skill 只做领域适配和结果格式化
- 多个 Skill 可共享同一基础设施
"""

from typing import List, Dict, Any
from ..registry import BaseSkill, ToolDefinition
from ..infrastructure import ocr_engine


class OCRSkill(BaseSkill):
    """OCR 技能 - 图像文字识别

    调用底层 OCREngine 基础设施，提供面向小说/漫画场景的工具。
    """

    name = "ocr"

    def get_tools(self) -> List[ToolDefinition]:
        return [
            ToolDefinition(
                name="ocr_recognize",
                description="识别图片中的文字，返回文本和位置信息。支持漫画、小说截图、封面等各种图片。",
                parameters={
                    "image_path": {"type": "string", "required": True, "desc": "图片文件路径"},
                    "is_base64": {"type": "bool", "default": False, "desc": "是否为 base64 编码"},
                    "lang": {"type": "string", "default": "ch", "desc": "语言：ch/en/ch_sim+en/japan"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="ocr_extract_text",
                description="从图片中提取纯文本，适合漫画气泡、小说截图等场景。自动合并相近文字。",
                parameters={
                    "image_path": {"type": "string", "required": True, "desc": "图片文件路径"},
                    "is_base64": {"type": "bool", "default": False, "desc": "是否为 base64 编码"},
                    "merge_lines": {"type": "bool", "default": True, "desc": "是否合并同一气泡内的文字"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="ocr_comic_bubbles",
                description="漫画专用：识别漫画页面的所有气泡文字，按阅读顺序排列。",
                parameters={
                    "image_path": {"type": "string", "required": True, "desc": "漫画图片路径"},
                    "is_base64": {"type": "bool", "default": False, "desc": "是否为 base64 编码"},
                    "sort_by": {"type": "string", "default": "position", "desc": "排序方式：position（位置）/confidence（置信度）"},
                },
                skill=self.name,
            ),
            ToolDefinition(
                name="ocr_batch_recognize",
                description="批量识别多张图片，适合漫画章节批量处理。",
                parameters={
                    "image_dir": {"type": "string", "required": True, "desc": "图片目录路径"},
                    "image_pattern": {"type": "string", "default": "*.jpg", "desc": "文件名匹配模式"},
                    "output_format": {"type": "string", "default": "text", "desc": "输出格式：text/json/srt"},
                },
                skill=self.name,
            ),
        ]

    def execute(self, tool_name: str, **params) -> Dict[str, Any]:
        engine = ocr_engine(
            backend=self.config.get("ocr.backend", "paddleocr") if self.config else "paddleocr"
        )

        if tool_name == "ocr_recognize":
            return self._recognize(engine, params)
        elif tool_name == "ocr_extract_text":
            return self._extract_text(engine, params)
        elif tool_name == "ocr_comic_bubbles":
            return self._comic_bubbles(engine, params)
        elif tool_name == "ocr_batch_recognize":
            return self._batch_recognize(engine, params)

        return {"error": f"Unknown tool: {tool_name}", "tool": tool_name}

    def _recognize(self, engine, params) -> Dict[str, Any]:
        result = engine.recognize(
            image_path=params.get("image_path", ""),
            is_base64=params.get("is_base64", False),
            lang=params.get("lang", "ch"),
        )

        if not result.success:
            return {
                "error": result.error or "OCR 识别失败",
                "backend": result.backend,
                "success": False,
            }

        return {
            "success": True,
            "backend": result.backend,
            "total": len(result.lines),
            "lines": [
                {
                    "text": line.text,
                    "confidence": line.confidence,
                    "bbox": line.bbox,
                }
                for line in result.lines
            ],
            "average_confidence": result.avg_confidence,
            "full_text": result.full_text,
            "elapsed_ms": result.elapsed_ms,
        }

    def _extract_text(self, engine, params) -> Dict[str, Any]:
        result = engine.recognize(
            image_path=params.get("image_path", ""),
            is_base64=params.get("is_base64", False),
        )
        return {
            "success": result.success,
            "text": result.full_text,
            "backend": result.backend,
            "line_count": len(result.lines),
            "error": result.error,
        }

    def _comic_bubbles(self, engine, params) -> Dict[str, Any]:
        result = engine.recognize(
            image_path=params.get("image_path", ""),
            is_base64=params.get("is_base64", False),
        )

        if not result.success:
            return {
                "error": result.error or "OCR 识别失败",
                "success": False,
            }

        sort_by = params.get("sort_by", "position")
        lines = list(result.lines)

        if sort_by == "position" and all(line.bbox for line in lines):
            lines = sorted(lines, key=lambda l: (l.bbox[0][1], l.bbox[0][0]))
        elif sort_by == "confidence":
            lines = sorted(lines, key=lambda l: l.confidence, reverse=True)

        return {
            "success": True,
            "backend": result.backend,
            "bubble_count": len(lines),
            "bubbles": [
                {
                    "order": i + 1,
                    "text": line.text,
                    "confidence": line.confidence,
                    "bbox": line.bbox,
                }
                for i, line in enumerate(lines)
            ],
            "full_text": "\n".join(line.text for line in lines),
        }

    def _batch_recognize(self, engine, params) -> Dict[str, Any]:
        import os
        import glob

        image_dir = params.get("image_dir", "")
        pattern = params.get("image_pattern", "*.jpg")
        output_format = params.get("output_format", "text")

        if not os.path.isdir(image_dir):
            return {"error": f"目录不存在: {image_dir}", "success": False}

        image_files = sorted(glob.glob(os.path.join(image_dir, pattern)))
        if not image_files:
            return {"error": f"未找到匹配的图片: {os.path.join(image_dir, pattern)}", "success": False}

        results = []
        for img_path in image_files:
            result = engine.recognize(image_path=img_path)
            results.append({
                "file": os.path.basename(img_path),
                "text": result.full_text,
                "line_count": len(result.lines),
                "confidence": result.avg_confidence,
                "success": result.success,
            })

        all_text = "\n\n".join(f"[{r['file']}]\n{r['text']}" for r in results)

        return {
            "success": True,
            "total_files": len(image_files),
            "results": results,
            "output_format": output_format,
            "full_text": all_text,
        }
