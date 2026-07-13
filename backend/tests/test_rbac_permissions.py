from app.core.permissions import Permission, build_permission_matrix


def test_permission_constants_cover_core_and_extended_domains():
    values = {permission.value for permission in Permission}
    assert "users.read" in values
    assert "book_sources.write" in values
    assert "engine.generate" in values
    assert "translation.run" in values
    assert "novel.manage" in values
    assert "ai.run" in values


def test_permission_matrix_is_unique():
    matrix = build_permission_matrix()
    assert len(matrix) == len(set(matrix))
