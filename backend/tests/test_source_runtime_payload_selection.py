from app.application.services.source_runtime_service import SourceRuntimeService


def test_runtime_registration_prefers_richer_imported_rule_over_generic_source_rule():
    original = {
        "bookSourceName": "久久小说网",
        "bookSourceUrl": "https://www.aijjxs.com",
        "searchUrl": "https://www.aijjxs.com/e/search/index.php::POST\nkeyboard={{key}}&show=title,writer",
        "ruleSearch": {"bookList": "div.searchTopic", "name": "a.searchtitle@text", "bookUrl": "a@href"},
        "ruleToc": {"chapterList": ".read li", "chapterName": "a@text", "chapterUrl": "a@href"},
        "ruleContent": {"content": "#view_content@text"},
        "ruleBookInfo": {"name": "h1@text"},
    }
    generic = {
        "bookSourceName": "www.aijjxs.com",
        "bookSourceUrl": "https://www.aijjxs.com",
        "searchUrl": "https://www.aijjxs.com/search?keyword={key}",
        "ruleSearch": {"bookList": "tag.article || tag.li", "name": "tag.a@text", "bookUrl": "tag.a@href"},
        "ruleToc": {"chapterList": "class.chapter-list@tag.a", "chapterName": "tag.a@text", "chapterUrl": "tag.a@href"},
        "ruleContent": {"content": "class.content@html"},
    }
    selected = SourceRuntimeService._legacy_book_source_payload({"source_rule": generic, **original})
    assert selected["bookSourceName"] == "久久小说网"
    assert selected["searchUrl"].endswith("show=title,writer")
