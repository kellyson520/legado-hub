from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin
from bs4 import BeautifulSoup, Tag


class SourceInductionService:
    """Heuristic, deterministic DOM pattern induction engine for Legado book sources."""

    _CHAPTER_REGEX = re.compile(
        r"(第\s*[0-9一二两三四五六七八九十百千]+\s*[章回节卷集话幕]|Chapter\s*\d+|\b\d+\s*[\.、-])",
        re.IGNORECASE,
    )
    _SEARCH_INPUT_NAMES = ("kw", "keyword", "key", "searchkey", "search", "q", "wd", "name")

    def infer_source_from_html(
        self,
        base_url: str,
        toc_html: str,
        content_html: str | None = None,
        search_html: str | None = None,
        source_name: str | None = None,
    ) -> dict[str, Any]:
        toc_soup = BeautifulSoup(toc_html, "lxml")
        name = source_name or self._extract_title(toc_soup)

        toc_rule = self.infer_toc_rule(toc_soup)

        content_rule = {"content": ""}
        if content_html:
            content_soup = BeautifulSoup(content_html, "lxml")
            content_rule = self.infer_content_rule(content_soup)

        search_rule: dict[str, Any] = {"searchUrl": "", "ruleSearch": {"bookList": "", "name": "", "author": "", "bookUrl": ""}}
        if search_html:
            search_soup = BeautifulSoup(search_html, "lxml")
            search_rule = self.infer_search_rule(search_soup, base_url)
        elif toc_soup.find("form"):
            search_rule = self.infer_search_rule(toc_soup, base_url)

        return {
            "bookSourceUrl": base_url,
            "bookSourceName": name,
            "bookSourceGroup": "自动推导",
            "bookSourceComment": f"由 LegadoHub 模式归纳引擎自动生成\n基准地址: {base_url}",
            "enabled": True,
            "searchUrl": search_rule.get("searchUrl", ""),
            "ruleSearch": search_rule.get("ruleSearch", {}),
            "ruleBookInfo": {"name": "", "author": "", "intro": "", "coverUrl": "", "tocUrl": ""},
            "ruleToc": toc_rule,
            "ruleContent": content_rule,
        }

    def infer_toc_rule(self, soup: BeautifulSoup) -> dict[str, str]:
        """Induces chapter list and item selectors from a table of contents DOM."""
        links = soup.find_all("a", href=True)
        if not links:
            return {"chapterList": "", "chapterName": "text", "chapterUrl": "href"}

        # Score candidate parent containers by link density & chapter title matches
        container_scores: dict[str, float] = {}
        container_samples: dict[str, list[Tag]] = {}

        for a in links:
            text = a.get_text(strip=True)
            has_chapter_signal = bool(self._CHAPTER_REGEX.search(text))
            bonus = 10.0 if has_chapter_signal else 1.0

            # Trace up to 3 parent layers
            curr: Tag | None = a.parent
            depth = 0
            while curr and depth < 3 and curr.name not in ("body", "html"):
                sel = self._compute_selector(curr)
                if sel:
                    container_scores[sel] = container_scores.get(sel, 0.0) + bonus
                    container_samples.setdefault(sel, []).append(a)
                curr = curr.parent
                depth += 1

        if not container_scores:
            return {"chapterList": "a", "chapterName": "text", "chapterUrl": "href"}

        # Pick the container with the highest score that contains at least 3 links
        ranked = sorted(container_scores.items(), key=lambda x: x[1], reverse=True)
        best_selector = "a"
        for sel, score in ranked:
            items = container_samples.get(sel, [])
            if len(items) >= 3:
                best_selector = sel
                break

        # Determine relative item selector
        # If best_selector is e.g. "ul.chapters", relative is "li a" or "a"
        full_list_selector = f"{best_selector} a" if not best_selector.endswith("a") else best_selector
        return {
            "chapterList": full_list_selector,
            "chapterName": "text",
            "chapterUrl": "href",
        }

    def infer_content_rule(self, soup: BeautifulSoup) -> dict[str, str]:
        """Detects the main reading text block by analyzing text density and structure."""
        cleaned_soup = BeautifulSoup(str(soup), "lxml")
        for noise in cleaned_soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            noise.decompose()

        candidates: list[tuple[Tag, float]] = []
        for tag in cleaned_soup.find_all(["div", "article", "section", "main"]):
            text = tag.get_text(separator="\n", strip=True)
            chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
            paragraphs = len(tag.find_all("p")) + text.count("\n")
            links = len(tag.find_all("a"))

            # Calculate content score: rewards chinese characters and paragraphs, heavily penalizes high link counts
            if links > 0 and chinese_chars > 0 and (links / max(chinese_chars, 1)) > 0.1:
                continue

            score = chinese_chars + (paragraphs * 50.0) - (links * 200.0)
            if score > 100:
                candidates.append((tag, score))

        if not candidates:
            return {"content": "#content, .content, article"}

        candidates.sort(key=lambda x: x[1], reverse=True)
        best_tag = candidates[0][0]
        selector = self._compute_selector(best_tag)
        return {
            "content": selector or "#content",
        }

    def infer_search_rule(self, soup: BeautifulSoup, base_url: str) -> dict[str, Any]:
        """Infers search URL pattern and parameter schema from HTML form."""
        form = soup.find("form")
        if not form:
            return {
                "searchUrl": f"{base_url.rstrip('/')}/search?key={{{{key}}}}",
                "ruleSearch": {"bookList": "", "name": "", "author": "", "bookUrl": ""},
            }

        action = form.get("action", "/search")
        full_action = urljoin(base_url, action)
        method = (form.get("method") or "get").lower()

        # Find best search input parameter
        param_name = "key"
        for inp in form.find_all("input"):
            name = inp.get("name")
            if not name:
                continue
            name_lower = name.lower()
            if any(k in name_lower for k in self._SEARCH_INPUT_NAMES):
                param_name = name
                break

        if method == "post":
            search_url = f'{full_action},{{"method": "POST", "body": "{param_name}={{{{key}}}}"}}'
        else:
            search_url = f"{full_action}?{param_name}={{{{key}}}}"

        return {
            "searchUrl": search_url,
            "ruleSearch": {"bookList": "", "name": "", "author": "", "bookUrl": ""},
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            # Clean common suffixes like "- 顶点小说", "_笔趣阁"
            title = re.split(r"[-_|—]", title)[0].strip()
            if title:
                return title
        h1 = soup.find("h1")
        if h1:
            return h1.get_text(strip=True)
        return "自动推导书源"

    @staticmethod
    def _compute_selector(tag: Tag) -> str:
        tag_id = tag.get("id")
        if tag_id and isinstance(tag_id, str) and not tag_id.isdigit():
            return f"#{tag_id}"

        classes = tag.get("class", [])
        if isinstance(classes, list) and classes:
            valid_classes = [c for c in classes if not re.search(r"\d{3,}", c)]
            if valid_classes:
                return f"{tag.name}.{valid_classes[0]}"

        parent = tag.parent
        if parent and parent.name not in ("body", "html"):
            parent_id = parent.get("id")
            if parent_id and isinstance(parent_id, str):
                return f"#{parent_id} {tag.name}"
            parent_class = parent.get("class", [])
            if isinstance(parent_class, list) and parent_class:
                return f".{parent_class[0]} {tag.name}"

        return tag.name
