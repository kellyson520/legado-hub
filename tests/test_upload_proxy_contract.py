from pathlib import Path


def test_nginx_upload_body_limit_covers_supplied_novels():
    config = Path("nginx/nginx.conf").read_text()
    assert "client_max_body_size 16m;" in config
