"""
OCR 基础设施服务

多后端 OCR 引擎封装，支持 PaddleOCR / manga-ocr / EasyOCR。
作为基础设施层的可复用组件，供各模块调用。

设计原则：
- 懒加载：后端引擎在首次使用时才加载，减少启动时间
- 多后端支持：可根据场景选择最合适的 OCR 引擎
- 统一接口：所有后端返回统一的 OCRResult 结构
- 错误隔离：单个后端失败不影响整体可用性
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import os

from app.core.logging import get_logger

logger = get_logger("infra.ocr")


@dataclass
class OCRLine:
    """OCR 单行结果"""
    text: str
    confidence: float = 0.0
    bbox: Optional[List[List[float]]] = None  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]


@dataclass
class OCRResult:
    """OCR 识别结果"""
    lines: List[OCRLine] = field(default_factory=list)
    backend: str = ""
    success: bool = True
    error: Optional[str] = None
    elapsed_ms: float = 0.0

    @property
    def full_text(self) -> str:
        """合并所有行的文本"""
        return "\n".join(line.text for line in self.lines)

    @property
    def avg_confidence(self) -> float:
        """平均置信度"""
        if not self.lines:
            return 0.0
        return sum(line.confidence for line in self.lines) / len(self.lines)


class OCREngine:
    """
    OCR 引擎（多后端支持）

    支持的后端:
    - paddleocr: 通用中英文 OCR（默认）
    - manga-ocr: 漫画气泡专用 OCR
    - easyocr: 多语言 OCR

    使用示例:
        engine = OCREngine(backend="paddleocr")
        result = engine.recognize("path/to/image.jpg")
        print(result.full_text)
    """

    _instances: Dict[str, "OCREngine"] = {}

    def __new__(cls, backend: str = "paddleocr", **kwargs):
        """单例模式：每个后端只初始化一次"""
        if backend not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[backend] = instance
        return cls._instances[backend]

    def __init__(self, backend: str = "paddleocr", **kwargs):
        if getattr(self, "_initialized", False):
            return
        self.backend = backend
        self._engine = None
        self._engine_name = None
        self._available = False
        self._init_kwargs = kwargs
        self._initialized = True

    def _lazy_init(self):
        """懒加载后端引擎"""
        if self._engine is not None:
            return

        import importlib

        backends = {
            "paddleocr": self._init_paddleocr,
            "manga-ocr": self._init_manga_ocr,
            "manga_ocr": self._init_manga_ocr,
            "easyocr": self._init_easyocr,
        }

        init_func = backends.get(self.backend)
        if init_func:
            try:
                init_func()
                self._available = True
                logger.info(f"[OCR] 后端 {self.backend} 初始化成功")
            except Exception as e:
                self._available = False
                logger.warning(f"[OCR] 后端 {self.backend} 初始化失败: {e}")
        else:
            self._available = False
            logger.warning(f"[OCR] 未知后端: {self.backend}")

    def _init_paddleocr(self):
        """初始化 PaddleOCR"""
        try:
            from paddleocr import PaddleOCR
            lang = self._init_kwargs.get("lang", "ch")
            use_angle_cls = self._init_kwargs.get("use_angle_cls", True)
            show_log = self._init_kwargs.get("show_log", False)
            self._engine = PaddleOCR(
                use_angle_cls=use_angle_cls,
                lang=lang,
                show_log=show_log,
            )
            self._engine_name = "PaddleOCR"
        except ImportError:
            raise ImportError("PaddleOCR 未安装，请运行: pip install paddleocr paddlepaddle")

    def _init_manga_ocr(self):
        """初始化 manga-ocr"""
        try:
            from manga_ocr import MangaOcr
            self._engine = MangaOcr()
            self._engine_name = "MangaOCR"
        except ImportError:
            raise ImportError("manga-ocr 未安装，请运行: pip install manga-ocr")

    def _init_easyocr(self):
        """初始化 EasyOCR"""
        try:
            import easyocr
            lang_list = self._init_kwargs.get("lang_list", ["ch_sim", "en"])
            gpu = self._init_kwargs.get("gpu", False)
            self._engine = easyocr.Reader(lang_list, gpu=gpu)
            self._engine_name = "EasyOCR"
        except ImportError:
            raise ImportError("EasyOCR 未安装，请运行: pip install easyocr")

    @property
    def is_available(self) -> bool:
        """引擎是否可用"""
        if self._engine is None:
            self._lazy_init()
        return self._available

    def recognize(
        self,
        image_path: str = "",
        image_data: Optional[bytes] = None,
        is_base64: bool = False,
        lang: str = "ch",
    ) -> OCRResult:
        """
        执行 OCR 识别

        Args:
            image_path: 图片文件路径
            image_data: 图片二进制数据
            is_base64: image_data 是否为 base64 编码
            lang: 语言（仅部分后端支持）

        Returns:
            OCRResult 识别结果
        """
        import time
        start = time.time()

        if not image_path and image_data is None:
            return OCRResult(
                success=False,
                error="必须提供 image_path 或 image_data",
                backend=self.backend,
            )

        self._lazy_init()
        if not self._available:
            return OCRResult(
                success=False,
                error=f"OCR 后端 {self.backend} 不可用",
                backend=self.backend,
            )

        try:
            lines: List[OCRLine] = []

            if self.backend == "paddleocr":
                lines = self._recognize_paddleocr(image_path, image_data, is_base64)
            elif self.backend in ("manga-ocr", "manga_ocr"):
                lines = self._recognize_manga_ocr(image_path, image_data)
            elif self.backend == "easyocr":
                lines = self._recognize_easyocr(image_path, image_data, is_base64)

            elapsed = (time.time() - start) * 1000
            return OCRResult(
                lines=lines,
                backend=self.backend,
                success=True,
                elapsed_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.time() - start) * 1000
            logger.error(f"[OCR] 识别失败: {e}")
            return OCRResult(
                success=False,
                error=str(e),
                backend=self.backend,
                elapsed_ms=elapsed,
            )

    def _recognize_paddleocr(
        self, image_path: str, image_data: Optional[bytes], is_base64: bool
    ) -> List[OCRLine]:
        """PaddleOCR 识别"""
        import numpy as np
        from PIL import Image
        import io

        if image_data is not None:
            if is_base64:
                import base64
                image_data = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(image_data))
            img_array = np.array(img)
            result = self._engine.ocr(img_array, cls=True)
        else:
            result = self._engine.ocr(image_path, cls=True)

        lines = []
        if result and result[0]:
            for item in result[0]:
                bbox = item[0]
                text = item[1][0]
                confidence = item[1][1]
                lines.append(OCRLine(text=text, confidence=confidence, bbox=bbox))
        return lines

    def _recognize_manga_ocr(
        self, image_path: str, image_data: Optional[bytes]
    ) -> List[OCRLine]:
        """manga-ocr 识别（单气泡图，返回单行）"""
        from PIL import Image
        import io

        if image_data is not None:
            img = Image.open(io.BytesIO(image_data))
        else:
            img = Image.open(image_path)

        text = self._engine(img)
        return [OCRLine(text=text, confidence=0.9)]

    def _recognize_easyocr(
        self, image_path: str, image_data: Optional[bytes], is_base64: bool
    ) -> List[OCRLine]:
        """EasyOCR 识别"""
        import numpy as np
        from PIL import Image
        import io

        if image_data is not None:
            if is_base64:
                import base64
                image_data = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(image_data))
            img_array = np.array(img)
            result = self._engine.readtext(img_array)
        else:
            result = self._engine.readtext(image_path)

        lines = []
        for item in result:
            bbox, text, confidence = item
            lines.append(OCRLine(text=text, confidence=confidence, bbox=bbox))
        return lines

    def batch_recognize(self, image_paths: List[str]) -> List[OCRResult]:
        """批量识别多张图片"""
        return [self.recognize(path) for path in image_paths]
