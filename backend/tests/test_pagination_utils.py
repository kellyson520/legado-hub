import pytest


def test_pagination_meta_uses_common_contract_and_keeps_extra_filters():
    from app.core.pagination import pagination_meta

    assert pagination_meta(2, 20, 41, search='book', status='candidate') == {
        'page': 2,
        'page_size': 20,
        'total': 41,
        'total_pages': 3,
        'search': 'book',
        'status': 'candidate',
    }


@pytest.mark.parametrize(
    ('total', 'page_size', 'expected'),
    [(0, 20, 0), (1, 20, 1), (40, 20, 2), (41, 20, 3)],
)
def test_pagination_meta_calculates_empty_and_partial_pages(total, page_size, expected):
    from app.core.pagination import pagination_meta

    assert pagination_meta(1, page_size, total)['total_pages'] == expected


def test_like_pattern_escapes_sql_wildcards():
    from app.core.pagination import like_pattern

    assert like_pattern(r'100%_ready\\') == r'%100\%\_ready\\\\%'


def test_paginated_result_composes_items_and_canonical_metadata():
    from app.core.pagination import paginated_result

    assert paginated_result(
        [{'id': 'row-1'}],
        page=2,
        page_size=20,
        total=21,
        search='book',
        status='candidate',
    ) == {
        'items': [{'id': 'row-1'}],
        'meta': {
            'page': 2,
            'page_size': 20,
            'total': 21,
            'total_pages': 2,
            'search': 'book',
            'status': 'candidate',
        },
    }
