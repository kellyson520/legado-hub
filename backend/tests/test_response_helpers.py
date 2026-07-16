from unittest.mock import patch


def test_from_paginated_result_adapts_service_contract_without_losing_metadata():
    from app.core.response import from_paginated_result

    assert from_paginated_result(
        {
            'items': [{'id': 'row-1'}],
            'meta': {'page': 2, 'page_size': 20, 'total': 21, 'total_pages': 2, 'search': 'book'},
        },
        message='rows listed',
    ) == {
        'success': True,
        'code': 'OK',
        'message': 'rows listed',
        'data': [{'id': 'row-1'}],
        'meta': {'page': 2, 'page_size': 20, 'total': 21, 'total_pages': 2, 'search': 'book'},
        'trace_id': None,
    }


def test_from_paginated_result_propagates_current_trace_id():
    from app.core.response import from_paginated_result

    with patch('app.core.response.get_trace_id', return_value='trace-123'):
        response = from_paginated_result({'items': [], 'meta': {'page': 1}})

    assert response['trace_id'] == 'trace-123'
