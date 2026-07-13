"""
security.py 单元测试

覆盖 security 模块的 8 个公开函数：
- generate_api_key
- hash_api_key
- verify_api_key
- create_access_token
- decode_access_token
- mask_api_key
- hash_password
- verify_password
"""

import pytest
from datetime import timedelta


class TestGenerateApiKey:
    """generate_api_key 函数测试"""

    def test_generate_api_key_returns_string(self):
        """验证 generate_api_key 返回字符串类型"""
        from app.core.security import generate_api_key
        key = generate_api_key()
        assert isinstance(key, str)

    def test_generate_api_key_has_correct_prefix(self):
        """验证生成的 API Key 以 'lh_' 前缀开头"""
        from app.core.security import generate_api_key
        key = generate_api_key()
        assert key.startswith("lh_")

    def test_generate_api_key_has_correct_length(self):
        """验证生成的 API Key 长度为 35（3前缀 + 32随机字符）"""
        from app.core.security import generate_api_key
        key = generate_api_key()
        assert len(key) == 35  # "lh_" (3) + 32 random chars

    def test_generate_api_key_is_unique(self):
        """验证多次生成的 API Key 互不相同"""
        from app.core.security import generate_api_key
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100


class TestHashApiKey:
    """hash_api_key 函数测试"""

    def test_hash_api_key_returns_string(self):
        """验证 hash_api_key 返回字符串"""
        from app.core.security import hash_api_key
        hashed = hash_api_key("lh_test_key_12345678")
        assert isinstance(hashed, str)

    def test_hash_api_key_returns_sha256_length(self):
        """验证哈希结果为 64 字符的 SHA256 十六进制"""
        from app.core.security import hash_api_key
        hashed = hash_api_key("lh_test_key_12345678")
        assert len(hashed) == 64  # SHA256 hex digest 长度

    def test_hash_api_key_is_deterministic(self):
        """验证相同输入产生相同哈希"""
        from app.core.security import hash_api_key
        key = "lh_consistent_key_12345"
        assert hash_api_key(key) == hash_api_key(key)

    def test_hash_api_key_different_keys_different_hashes(self):
        """验证不同输入产生不同哈希"""
        from app.core.security import hash_api_key
        h1 = hash_api_key("lh_key_aaaa_12345678")
        h2 = hash_api_key("lh_key_bbbb_12345678")
        assert h1 != h2


class TestVerifyApiKey:
    """verify_api_key 函数测试"""

    def test_verify_api_key_with_correct_key(self):
        """验证正确 key 返回 True"""
        from app.core.security import hash_api_key, verify_api_key
        raw_key = "lh_correct_key_123456"
        hashed = hash_api_key(raw_key)
        assert verify_api_key(raw_key, hashed) is True

    def test_verify_api_key_with_wrong_key(self):
        """验证错误 key 返回 False"""
        from app.core.security import hash_api_key, verify_api_key
        hashed = hash_api_key("lh_correct_key_123456")
        assert verify_api_key("lh_wrong_key_abcdef01", hashed) is False


class TestCreateAccessToken:
    """create_access_token 函数测试"""

    def test_create_access_token_returns_jwt_string(self):
        """验证创建的 token 是字符串类型"""
        from app.core.security import create_access_token
        token = create_access_token({"sub": "test_user"})
        assert isinstance(token, str)

    def test_create_access_token_with_custom_expiry(self):
        """验证自定义过期时间的 token"""
        from app.core.security import create_access_token
        token = create_access_token(
            {"sub": "test_user"},
            expires_delta=timedelta(hours=1)
        )
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_different_data_different_token(self):
        """验证不同数据生成不同 token"""
        from app.core.security import create_access_token
        t1 = create_access_token({"sub": "user_1"})
        t2 = create_access_token({"sub": "user_2"})
        assert t1 != t2


class TestDecodeAccessToken:
    """decode_access_token 函数测试"""

    def test_decode_access_token_valid_token(self):
        """验证解码有效 token 返回正确 payload"""
        from app.core.security import create_access_token, decode_access_token
        token = create_access_token({"sub": "test_user", "role": "admin"})
        payload = decode_access_token(token)
        assert payload is not None
        assert payload["sub"] == "test_user"
        assert payload["role"] == "admin"

    def test_decode_access_token_invalid_token_returns_none(self):
        """验证解码无效 token 返回 None"""
        from app.core.security import decode_access_token
        result = decode_access_token("invalid.jwt.token")
        assert result is None

    def test_decode_access_token_expired_token_returns_none(self):
        """验证解码已过期 token 返回 None"""
        from app.core.security import create_access_token, decode_access_token
        # 使用已过期的时间（负数 timedelta）
        token = create_access_token(
            {"sub": "expired_user"},
            expires_delta=timedelta(seconds=-1)
        )
        result = decode_access_token(token)
        assert result is None


class TestMaskApiKey:
    """mask_api_key 函数测试"""

    def test_mask_api_key_normal_key(self):
        """验证正常长度 key 的脱敏显示：前4后4"""
        from app.core.security import mask_api_key
        key = "lh_abcdefghijklmnopqrstuvwxyz123456"
        masked = mask_api_key(key)
        assert masked == "lh_a****3456"

    def test_mask_api_key_short_key(self):
        """验证短 key（<=8字符）返回全星号"""
        from app.core.security import mask_api_key
        masked = mask_api_key("lh_ab")
        assert masked == "****"


class TestHashPassword:
    """hash_password 函数测试"""

    def test_hash_password_returns_string(self):
        """验证密码哈希返回字符串"""
        from app.core.security import hash_password
        hashed = hash_password("my_password")
        assert isinstance(hashed, str)

    def test_hash_password_returns_sha256_length(self):
        """验证密码哈希长度为 64（SHA256）"""
        from app.core.security import hash_password
        hashed = hash_password("my_password")
        assert len(hashed) == 64

    def test_hash_password_different_passwords_different_hashes(self):
        """验证不同密码产生不同哈希"""
        from app.core.security import hash_password
        h1 = hash_password("password_a")
        h2 = hash_password("password_b")
        assert h1 != h2


class TestVerifyPassword:
    """verify_password 函数测试"""

    def test_verify_password_correct_password(self):
        """验证正确密码返回 True"""
        from app.core.security import hash_password, verify_password
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_password_wrong_password(self):
        """验证错误密码返回 False"""
        from app.core.security import hash_password, verify_password
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False
