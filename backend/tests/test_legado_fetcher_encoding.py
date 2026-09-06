from app.infrastructure.legado.legado_fetcher import LegadoBookSourceFetcher


def test_post_body_uses_raw_keyword_while_url_variables_keep_encoded_keyword():
    variables = LegadoBookSourceFetcher._search_variables("天才俱乐部", 1)
    body_variables = LegadoBookSourceFetcher._body_variables(variables)

    assert variables["key"] != "天才俱乐部"
    assert body_variables["key"] == "天才俱乐部"
    assert body_variables["searchKey"] == "天才俱乐部"
    assert body_variables["page"] == 1


def test_form_body_is_encoded_as_form_fields():
    assert LegadoBookSourceFetcher._form_body("keyboard=天才俱乐部&show=title,writer") == {
        "keyboard": "天才俱乐部",
        "show": "title,writer",
    }
