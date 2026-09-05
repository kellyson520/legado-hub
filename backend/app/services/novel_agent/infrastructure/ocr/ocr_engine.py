"""
OCR 基础设施 - OCR Engine

底层 OCR 能力，支持多后端切换。
上层 Skill 通过统一接口调用，不感知具体实现。

参考 OpenClaw 的 "能力下沉" 原则：
- 通用 OCR 能力不属于任何特定 Skill
- 作为基础设施被多个 Skill 复用
- 懒加载 + 降级策略
"""

from __future__ import annotations

import base64
import io
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class OCRLine:
    text: str
    confidence: float
    bbox: Optional[List[List[float]]] = None


@dataclass
class OCRResult:
    lines: List[OCRLine] = field(default_factory=list)
    engine: str = ""
    total: int = 0
    average_confidence: float = 0.0

    @property
    def full_text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class OCREngine:
    """OCR 引擎 - 底层基础设施

    设计原则（参考 OpenClaw 窄腰架构）：
    - 单一职责：只做 OCR 识别
    - 多后端可插拔
    - 懒加载：首次调用才初始化
    - 降级策略：无引擎时返回安装提示
    """

    def __init__(self, backend: str = "paddleocr"):
        self.backend = backend
        self._engine = None
        self._engine_name = None
        self._available = False

    def is_available(self) -> bool:
        return self._available

    def _init(self) -> bool:
        if self._engine is not None:
            return self._available

        backends_to_try = [self.backend, "paddleocr", "easyocr", "manga_ocr"]
        tried = set()

        for backend in backends_to_try:
            if backend in tried:
                continue
            tried.add(backend)

            if backend == "paddleocr":
                try:
                    from paddleocr import PaddleOCR
                    self._engine = PaddleOCR(
                        use_angle_cls=True,
                        lang="ch",
                        show_log=False,
                    )
                    self._engine_name = "paddleocr"
                    self._available = True
                    return True
                except ImportError:
                    continue

            elif backend == "easyocr":
                try:
                    import easyocr
                    self._engine = easyocr.Reader(["ch_sim", "en"])
                    self._engine_name = "easyocr"
                    self._available = True
                    return True
                except ImportError:
                    continue

            elif backend == "manga_ocr":
                try:
                    from manga_ocr import MangaOcr
                    self._engine = MangaOcr()
                    self._engine_name = "manga_ocr"
                    self._available = True
                    return True
                except ImportError:
                    continue

        self._available = False
        return False

    def get_install_hint(self) -> str:
        hints = {
            "paddleocr": "pip install paddleocr paddlepaddle",
            "manga_ocr": "pip install manga-ocr",
            "easyocr": "pip install easyocr",
        }
        return hints.get(self.backend, "pip install paddleocr paddlepaddle")

    def recognize(
        self,
        image_path: str = "",
        image_data: Optional[bytes] = None,
        is_base64: bool = False,
        lang: str = "ch",
    ) -> OCRResult:
        """识别图片文字

        Args:
            image_path: 图片文件路径
            image_data: 图片二进制数据（优先级高于 image_path）
            is_base64: 是否为 base64 编码
            lang: 语言

        Returns:
            OCRResult 对象
        """
        if not self._init():
            return OCRResult(
                engine="none",
                total=0,
                lines=[],
                average_confidence=0.0,
            )

        img = self._load_image(image_path, image_data, is_base64)
        if img is None:
            return OCRResult(
                engine=self._engine_name or "none",
                total=0,
                lines=[],
                average_confidence=0.0,
            )

        lines = []
        total_conf = 0.0

        if self._engine_name == "paddleocr":
            try:
                ocr_result = self._engine.ocr(img, cls=True)
                if ocr_result and ocr_result[0]:
                    for line in ocr_result[0]:
                        if line:
                            bbox = line[0]
                            text, conf = line[1]
                            lines.append(OCRLine(
                                text=text,
                                confidence=float(conf),
                                bbox=bbox,
                            ))
                            total_conf += float(conf)
            except Exception:
                pass

        elif self._engine_name == "manga_ocr":
            try:
                text = self._engine(img)
                lines.append(OCRLine(
                    text=text,
                    confidence=0.95,
                    bbox=None,
                ))
                total_conf = 0.95
            except Exception:
                pass

        elif self._engine_name == "easyocr":
            try:
                import numpy as np
                img_array = np.array(img)
                ocr_result = self._engine.readtext(img_array)
                for r in ocr_result:
                    bbox, text, conf = r
                    lines.append(OCRLine(
                        text=text,
                        confidence=float(conf),
                        bbox=bbox.tolist() if hasattr(bbox, "tolist") else bbox,
                    ))
                    total_conf += float(conf)
            except Exception:
                pass

        avg_conf = total_conf / len(lines) if lines else 0.0

        return OCRResult(
            engine=self._engine_name or "none",
            total=len(lines),
            lines=lines,
            average_confidence=round(avg_conf, 3),
        )

    def extract_text(
        self,
        image_path: str = "",
        image_data: Optional[bytes] = None,
        is_base64: bool = False,
        merge_lines: bool = True,
    ) -> Dict[str, Any]:
        """提取纯文本（更轻量的接口）"""
        result = self.recognize(image_path, image_data, is_base64)

        if not result.lines:
            return {
                "text": "",
                "line_count": 0,
                "engine": result.engine,
                "available": self._available,
                "install_hint": self.get_install_hint() if not self._available else "",
            }

        texts = [line.text for line in result.lines]
        merged = " ".join(texts) if merge_lines else "\n".join(texts)

        return {
            "text": merged,
            "line_count": len(texts),
            "average_confidence": result.average_confidence,
            "engine": result.engine,
            "available": True,
        }

    def _load_image(
        self,
        image_path: str,
        image_data: Optional[bytes],
        is_base64: bool,
    ):
        try:
            from PIL import Image
        except ImportError:
            return None

        try:
            if image_data is not None:
                if is_base64:
                    img_bytes = base64.b64decode(image_data)
                else:
                    img_bytes = image_data if isinstance(image_data, bytes) else image_data.encode()
                return Image.open(io.BytesIO(img_bytes))
            elif image_path:
                return Image.open(image_path)
            return None
        except Exception:
            return None


_ocr_singleton: Optional[OCREngine] = None


def ocr_engine(backend: str = "paddleocr") -> OCREngine:
    """获取 OCR 引擎单例"""
    global _ocr_singleton
    if _ocr_singleton is None:
        _ocr_singleton = OCREngine(backend=backend)
    return _ocr_singleton
