"""app.core.security 当前公开契约的回归测试。"""

import re


class TestGenerateApiKey:
    def test_generate_api_key_returns_prefixed_urlsafe_value(self):
        from app.core.security import generate_api_key

        key = generate_api_key()

        assert key.startswith("lh_")
        payload = key.removeprefix("lh_")
        assert len(payload) >= 32
        assert re.fullmatch(r"[A-Za-z0-9_-]+", payload)

    def test_generate_api_key_is_unique(self):
        from app.core.security import generate_api_key

        assert len({generate_api_key() for _ in range(100)}) == 100


class TestHashApiKey:
    def test_hash_api_key_is_sha256_hex_digest(self):
        from app.core.security import hash_api_key

        hashed = hash_api_key("lh_test_key_12345678")

        assert isinstance(hashed, str)
        assert len(hashed) == 64
        assert re.fullmatch(r"[0-9a-f]{64}", hashed)

    def test_hash_api_key_is_deterministic(self):
        from app.core.security import hash_api_key

        assert hash_api_key("lh_consistent_key_12345") == hash_api_key("lh_consistent_key_12345")

    def test_hash_api_key_distinguishes_different_keys(self):
        from app.core.security import hash_api_key

        assert hash_api_key("lh_key_aaaa_12345678") != hash_api_key("lh_key_bbbb_12345678")


class TestVerifyApiKey:
    def test_verify_api_key_accepts_matching_key_and_hash(self):
        from app.core.security import hash_api_key, verify_api_key

        raw_key = "lh_correct_key_123456"

        assert verify_api_key(raw_key, hash_api_key(raw_key)) is True

    def test_verify_api_key_rejects_mismatched_key(self):
        from app.core.security import hash_api_key, verify_api_key

        assert verify_api_key("lh_wrong_key_abcdef01", hash_api_key("lh_correct_key_123456")) is False


class TestAccessTokens:
    def test_create_access_token_adds_standard_access_claims(self):
        from app.core.security import create_access_token, decode_access_token

        payload = decode_access_token(create_access_token({"sub": "test_user", "role": "admin"}))

        assert payload["sub"] == "test_user"
        assert payload["role"] == "admin"
        assert payload["aud"] == "access"
        assert isinstance(payload["exp"], int)

    def test_create_access_token_normalizes_subject_to_string(self):
        from app.core.security import create_access_token, decode_access_token

        payload = decode_access_token(create_access_token({"sub": 42}))

        assert payload["sub"] == "42"

    def test_create_access_token_keeps_distinct_payloads_distinct(self):
        from app.core.security import create_access_token

        assert create_access_token({"sub": "user_1"}) != create_access_token({"sub": "user_2"})

    def test_decode_access_token_returns_empty_dict_for_invalid_token(self):
        from app.core.security import decode_access_token

        assert decode_access_token("invalid.jwt.token") == {}

    def test_decode_access_token_rejects_refresh_token_audience(self):
        from app.core.security import create_refresh_token, decode_access_token

        assert decode_access_token(create_refresh_token({"sub": "reader"})) == {}


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash_that_verifies(self):
        from app.core.security import hash_password, verify_password

        hashed = hash_password("my_password")

        assert isinstance(hashed, str)
        assert hashed.startswith("$2")
        assert hashed != "my_password"
        assert verify_password("my_password", hashed) is True

    def test_hash_password_uses_random_salt(self):
        from app.core.security import hash_password

        assert hash_password("same_password") != hash_password("same_password")

    def test_hash_password_distinguishes_different_passwords(self):
        from app.core.security import hash_password

        assert hash_password("password_a") != hash_password("password_b")

    def test_verify_password_rejects_wrong_password(self):
        from app.core.security import hash_password, verify_password

        assert verify_password("wrong_password", hash_password("correct_password")) is False
