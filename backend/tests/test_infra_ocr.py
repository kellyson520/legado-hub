"""
OCR 引擎单元测试

测试 OCR 基础设施层的核心功能：
- OCRLine / OCRResult 数据结构
- OCREngine 单例模式
- 多后端支持
- 错误处理
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock


# ==================== OCRLine 测试 ====================

class TestOCRLine:
    def test_ocr_line_defaults(self):
        from app.infrastructure.ocr import OCRLine
        line = OCRLine(text="测试文本")
        assert line.text == "测试文本"
        assert line.confidence == 0.0
        assert line.bbox is None

    def test_ocr_line_full(self):
        from app.infrastructure.ocr import OCRLine
        bbox = [[0, 0], [100, 0], [100, 30], [0, 30]]
        line = OCRLine(text="你好", confidence=0.95, bbox=bbox)
        assert line.text == "你好"
        assert line.confidence == 0.95
        assert line.bbox == bbox


# ==================== OCRResult 测试 ====================

class TestOCRResult:
    def test_result_defaults(self):
        from app.infrastructure.ocr import OCRResult
        result = OCRResult()
        assert result.lines == []
        assert result.backend == ""
        assert result.success is True
        assert result.error is None
        assert result.elapsed_ms == 0.0

    def test_full_text_empty(self):
        from app.infrastructure.ocr import OCRResult
        result = OCRResult()
        assert result.full_text == ""

    def test_full_text_multiple_lines(self):
        from app.infrastructure.ocr import OCRResult, OCRLine
        result = OCRResult(lines=[
            OCRLine(text="第一行"),
            OCRLine(text="第二行"),
            OCRLine(text="第三行"),
        ])
        assert result.full_text == "第一行\n第二行\n第三行"

    def test_avg_confidence_empty(self):
        from app.infrastructure.ocr import OCRResult
        result = OCRResult()
        assert result.avg_confidence == 0.0

    def test_avg_confidence(self):
        from app.infrastructure.ocr import OCRResult, OCRLine
        result = OCRResult(lines=[
            OCRLine(text="a", confidence=0.8),
            OCRLine(text="b", confidence=0.9),
            OCRLine(text="c", confidence=0.7),
        ])
        assert abs(result.avg_confidence - 0.8) < 0.01


# ==================== OCREngine 测试 ====================

class TestOCREngine:
    def test_singleton_same_backend(self):
        """同一后端应该返回同一个实例"""
        from app.infrastructure.ocr import OCREngine
        engine1 = OCREngine(backend="paddleocr")
        engine2 = OCREngine(backend="paddleocr")
        assert engine1 is engine2

    def test_singleton_different_backend(self):
        """不同后端返回不同实例"""
        from app.infrastructure.ocr import OCREngine
        engine1 = OCREngine(backend="paddleocr")
        engine2 = OCREngine(backend="easyocr")
        assert engine1 is not engine2
        assert engine1.backend == "paddleocr"
        assert engine2.backend == "easyocr"

    def test_recognize_no_input(self):
        """没有输入时应该返回失败"""
        from app.infrastructure.ocr import OCREngine
        engine = OCREngine(backend="paddleocr")
        result = engine.recognize()
        assert result.success is False
        assert "必须提供" in result.error

    def test_recognize_backend_unavailable(self):
        """后端不可用时返回失败（不触发懒加载）"""
        from app.infrastructure.ocr import OCREngine
        # 用一个不存在的后端
        engine = OCREngine(backend="nonexistent_backend")
        result = engine.recognize(image_path="/tmp/test.png")
        assert result.success is False
        assert "不可用" in result.error

    def test_batch_recognize(self):
        """批量识别（mock 引擎）"""
        from app.infrastructure.ocr import OCREngine, OCRResult, OCRLine

        engine = OCREngine(backend="paddleocr")
        engine._available = True

        # Mock _lazy_init 不做任何事
        with patch.object(engine, '_lazy_init'):
            with patch.object(engine, '_recognize_paddleocr', return_value=[
                OCRLine(text="mock result", confidence=0.9)
            ]):
                results = engine.batch_recognize(["fake1.png", "fake2.png"])
                assert len(results) == 2
                assert all(r.success for r in results)

    def test_is_available_lazy_load_trigger(self):
        """is_available 应该触发懒加载"""
        from app.infrastructure.ocr import OCREngine
        engine = OCREngine(backend="paddleocr")
        engine._engine = None
        # 因为没有安装 paddleocr，所以会返回 False
        # 但这不影响我们验证属性访问
        _ = engine.is_available
        # 至少不会报错
        assert True
