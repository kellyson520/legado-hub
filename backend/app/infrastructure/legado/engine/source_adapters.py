from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.infrastructure.legado.engine.models import RuntimeExecutionSummary


def _extract_value(node: Tag, rule: str) -> str:
    if not rule:
        return ""
    if rule.startswith("@"):
        return node.get(rule[1:], "") or ""
    if "@" in rule:
        selector, attr = rule.split("@", 1)
        target = node.select_one(selector) if selector else node
        if target is None:
            return ""
        if attr == "text":
            return target.get_text(strip=True)
        return target.get(attr, "") or ""
    target = node.select_one(rule)
    if target is None:
        return ""
    return target.get_text(strip=True)


class BookSourceAdapter:
    def __init__(self, http_client):
        self._http_client = http_client

    async def run(self, source: dict, keyword: str) -> RuntimeExecutionSummary:
        step_results: dict[str, dict] = {}

        search_url = (source.get("searchUrl") or "").replace("{{keyword}}", keyword)
        search_response = await self._http_client.get(search_url)
        search_step = {
            "passed": bool(search_response.success),
            "elapsed_ms": getattr(search_response, "elapsed_ms", 0),
            "url": getattr(search_response, "url", search_url),
            "result_count": 0,
        }
        step_results["search"] = search_step

        first_book_url = ""
        if search_response.success:
            soup = BeautifulSoup(search_response.text, "lxml")
            search_rule = source.get("ruleSearch") or {}
            books = soup.select(search_rule.get("bookList", ""))
            search_step["result_count"] = len(books)
            search_step["passed"] = len(books) > 0
            if books:
                first_book_url = _extract_value(books[0], search_rule.get("bookUrl", "")) or ""

        toc_step = {"passed": False, "elapsed_ms": 0, "chapter_count": 0}
        step_results["toc"] = toc_step
        chapter_url = ""
        if first_book_url:
            toc_response = await self._http_client.get(first_book_url)
            toc_step["elapsed_ms"] = getattr(toc_response, "elapsed_ms", 0)
            if toc_response.success:
                toc_rule = source.get("ruleToc") or {}
                soup = BeautifulSoup(toc_response.text, "lxml")
                chapters = soup.select(toc_rule.get("chapterList", ""))
                toc_step["chapter_count"] = len(chapters)
                toc_step["passed"] = len(chapters) > 0
                if chapters:
                    chapter_url = _extract_value(chapters[0], toc_rule.get("chapterUrl", "")) or ""
                    chapter_url = urljoin(first_book_url, chapter_url)

        content_step = {"passed": False, "elapsed_ms": 0, "content_length": 0}
        step_results["content"] = content_step
        if chapter_url:
            content_response = await self._http_client.get(chapter_url)
            content_step["elapsed_ms"] = getattr(content_response, "elapsed_ms", 0)
            if content_response.success:
                content_rule = (source.get("ruleContent") or {}).get("content", "")
                soup = BeautifulSoup(content_response.text, "lxml")
                target = soup.select_one(content_rule)
                content = target.get_text(strip=True) if target else ""
                content_step["content_length"] = len(content)
                content_step["passed"] = bool(content)

        return RuntimeExecutionSummary(step_results=step_results, diagnostics=[])


class RssSourceAdapter:
    def __init__(self, http_client):
        self._http_client = http_client

    async def run(self, source: dict) -> RuntimeExecutionSummary:
        step_results: dict[str, dict] = {}

        response = await self._http_client.get(source["sourceUrl"])
        feed_step = {
            "passed": bool(response.success),
            "elapsed_ms": getattr(response, "elapsed_ms", 0),
            "url": getattr(response, "url", source["sourceUrl"]),
        }
        step_results["feed_fetch"] = feed_step

        item_step = {"passed": False, "item_count": 0}
        if response.success:
            soup = BeautifulSoup(response.text, "xml")
            items = soup.select(source.get("ruleArticles", "item"))
            item_step["item_count"] = len(items)
            item_step["passed"] = len(items) > 0
        step_results["item_parse"] = item_step

        return RuntimeExecutionSummary(step_results=step_results, diagnostics=[])
