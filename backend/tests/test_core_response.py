"""
response.py 单元测试

覆盖 response 模块的 5 个构造函数：
- ok
- created
- paginated
- fail
- from_exception
"""

import pytest
from unittest.mock import patch


class TestOk:
    """ok 构造函数测试"""

    def test_ok_basic_structure(self):
        """验证 ok() 返回基本的成功响应结构"""
        from app.core.response import ok
        resp = ok()
        assert resp["success"] is True
        assert resp["code"] == "OK"
        assert resp["message"] == "success"
        assert resp["data"] is None
        assert "trace_id" in resp

    def test_ok_with_data(self):
        """验证 ok() 携带数据时正确填充 data 字段"""
        from app.core.response import ok
        data = {"id": 1, "name": "test"}
        resp = ok(data=data)
        assert resp["data"] == data

    def test_ok_with_custom_message(self):
        """验证 ok() 自定义消息"""
        from app.core.response import ok
        resp = ok(message="操作完成")
        assert resp["message"] == "操作完成"

    @patch("app.core.response.get_trace_id", return_value="trace-123")
    def test_ok_with_meta_and_trace_id(self, mock_trace):
        """验证 ok() 携带 meta 时正确包含"""
        from app.core.response import ok
        meta = {"version": "1.0"}
        resp = ok(meta=meta)
        assert resp["meta"] == meta
        assert resp["trace_id"] == "trace-123"


class TestCreated:
    """created 构造函数测试"""

    def test_created_basic_structure(self):
        """验证 created() 返回创建成功的响应结构"""
        from app.core.response import created
        resp = created()
        assert resp["success"] is True
        assert resp["code"] == "CREATED"
        assert resp["message"] == "创建成功"
        assert resp["data"] is None

    def test_created_with_data(self):
        """验证 created() 携带数据"""
        from app.core.response import created
        data = {"id": 42}
        resp = created(data=data)
        assert resp["data"] == data

    def test_created_custom_message(self):
        """验证 created() 自定义消息"""
        from app.core.response import created
        resp = created(message="书源创建完成")
        assert resp["message"] == "书源创建完成"


class TestPaginated:
    """paginated 构造函数测试"""

    def test_paginated_basic_structure(self):
        """验证 paginated() 返回分页响应结构"""
        from app.core.response import paginated
        resp = paginated(items=[1, 2, 3], total=100, page=1, page_size=10)
        assert resp["success"] is True
        assert resp["code"] == "OK"
        assert resp["data"] == [1, 2, 3]
        assert "meta" in resp

    def test_paginated_meta_fields(self):
        """验证 paginated() 的 meta 包含正确的分页字段"""
        from app.core.response import paginated
        resp = paginated(items=[], total=100, page=2, page_size=20)
        meta = resp["meta"]
        assert meta["page"] == 2
        assert meta["page_size"] == 20
        assert meta["total"] == 100
        assert meta["total_pages"] == 5  # ceil(100/20) = 5

    def test_paginated_total_pages_calculation(self):
        """验证 paginated() 的 total_pages 计算精度"""
        from app.core.response import paginated
        # 101 个项目，每页 20 -> 6 页
        resp = paginated(items=[], total=101, page=1, page_size=20)
        assert resp["meta"]["total_pages"] == 6

    def test_paginated_single_page(self):
        """验证 paginated() 当数据不足一页时 total_pages 为 1"""
        from app.core.response import paginated
        resp = paginated(items=[], total=5, page=1, page_size=20)
        assert resp["meta"]["total_pages"] == 1


class TestFail:
    """fail 构造函数测试"""

    def test_fail_basic_structure(self):
        """验证 fail() 返回失败响应结构"""
        from app.core.response import fail
        resp = fail()
        assert resp["success"] is False
        assert resp["code"] == "ERROR"
        assert resp["message"] == "操作失败"
        assert resp["data"] is None

    def test_fail_with_custom_message_and_code(self):
        """验证 fail() 自定义消息和错误码"""
        from app.core.response import fail
        resp = fail(message="参数错误", code="PARAM_ERROR")
        assert resp["message"] == "参数错误"
        assert resp["code"] == "PARAM_ERROR"

    def test_fail_with_details(self):
        """验证 fail() 携带详细错误信息"""
        from app.core.response import fail
        details = {"field": "name", "reason": "不能为空"}
        resp = fail(details=details)
        assert resp["details"] == details

    def test_fail_without_details_omits_key(self):
        """验证 fail() 不传 details 时响应中不包含 details 字段"""
        from app.core.response import fail
        resp = fail(message="失败")
        assert "details" not in resp


class TestFromException:
    """from_exception 构造函数测试"""

    def test_from_base_app_exception(self):
        """验证 from_exception() 从 BaseAppException 提取错误信息"""
        from app.core.response import from_exception
        from app.core.exceptions import NotFoundException
        exc = NotFoundException(message="书源不存在")
        resp = from_exception(exc)
        assert resp["success"] is False
        assert resp["code"] == "NOT_FOUND"
        assert resp["message"] == "书源不存在"
        assert resp["data"] is None

    def test_from_exception_with_custom_error_code(self):
        """验证 from_exception() 提取自定义 error_code"""
        from app.core.response import from_exception
        from app.core.exceptions import BaseAppException
        exc = BaseAppException(message="自定义错误", details={"key": "val"})
        exc.error_code = "CUSTOM_ERROR"
        resp = from_exception(exc)
        assert resp["code"] == "CUSTOM_ERROR"
        assert resp["message"] == "自定义错误"

    def test_from_exception_generic_exception(self):
        """验证 from_exception() 处理普通 Exception（无 error_code 属性）"""
        from app.core.response import from_exception
        exc = ValueError("普通错误")
        resp = from_exception(exc)
        assert resp["success"] is False
        assert resp["code"] == "INTERNAL_ERROR"
        assert resp["message"] == "普通错误"
