from __future__ import annotations

import html
import html.parser
import math
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Dict, List, Tuple

from .models import IndexEntry


class TextExtractor(html.parser.HTMLParser):
    """Lightweight HTML to title/body text extractor using only stdlib."""

    SKIP_TAGS = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.skip_depth = 0
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = True
        if tag_lower in self.SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag: str):  # type: ignore[override]
        tag_lower = tag.lower()
        if tag_lower == "title":
            self.in_title = False
        if tag_lower in self.SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if self.skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts)

    @property
    def body_text(self) -> str:
        return " ".join(self.text_parts)


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


@dataclass
class IndexedPage:
    url: str
    origin_url: str
    depth: int
    title: str
    token_count: int


class IndexService:
    """In-memory inverted index with TF-IDF-style ranking.

    The index is rebuilt from persisted page snapshots at startup so it can
    serve search queries even after a restart and concurrently with crawl jobs.
    """

    def __init__(self) -> None:
        self.inverted: DefaultDict[str, Dict[str, IndexEntry]] = defaultdict(dict)
        self.pages: Dict[str, IndexedPage] = {}
        self._lock = threading.RLock()

    def _ingest(self, url: str, origin_url: str, depth: int, title: str, tokens: List[str]) -> None:
        if not tokens:
            return
        term_counts: DefaultDict[str, int] = defaultdict(int)
        for token in tokens:
            term_counts[token] += 1

        with self._lock:
            existing = self.pages.get(url)
            # If the page was previously indexed, drop the old postings first
            # so re-indexing the same URL never inflates its score.
            if existing is not None:
                for token in list(self.inverted.keys()):
                    self.inverted[token].pop(url, None)

            self.pages[url] = IndexedPage(
                url=url,
                origin_url=origin_url,
                depth=depth,
                title=title,
                token_count=len(tokens),
            )
            for token, count in term_counts.items():
                # Term frequency normalized by document length; IDF applied at query time.
                tf = count / float(len(tokens))
                self.inverted[token][url] = (url, origin_url, depth, tf)

    def add_page(self, url: str, origin_url: str, depth: int, html_text: str) -> None:
        parser = TextExtractor()
        try:
            parser.feed(html_text)
        except Exception:
            return
        title = html.unescape(parser.title)
        body = html.unescape(parser.body_text)
        tokens = tokenize(f"{title} {body}")
        if not tokens:
            return

        self._ingest(url, origin_url, depth, title, tokens)

        # Persist a lightweight snapshot so we can rebuild the index on restart.
        body_snippet = " ".join(tokens)[:2000]
        try:
            from . import storage
            storage.save_page(url=url, origin_url=origin_url, depth=depth, title=title, body_snippet=body_snippet)
        except Exception:
            pass

    def add_snapshot_page(self, url: str, origin_url: str, depth: int, title: str, body_snippet: str) -> None:
        tokens = tokenize(f"{title} {body_snippet}")
        if not tokens:
            return
        self._ingest(url, origin_url, depth, title, tokens)

    def search(self, query: str, limit: int | None = None) -> List[Tuple[str, str, int, float, str]]:
        """Return ranked search results.

        Each tuple is (relevant_url, origin_url, depth, score, title), where
        the first three values match the assignment-required triple.
        """
        tokens = tokenize(query)
        if not tokens:
            return []
        unique_tokens = list(dict.fromkeys(tokens))

        with self._lock:
            total_docs = len(self.pages)
            if total_docs == 0:
                return []

            scores: DefaultDict[str, float] = defaultdict(float)
            meta: Dict[str, Tuple[str, int, str]] = {}

            for token in unique_tokens:
                postings = self.inverted.get(token)
                if not postings:
                    continue
                df = len(postings)
                idf = math.log((1 + total_docs) / (1 + df)) + 1.0
                for url, posting in postings.items():
                    _, origin_url, depth, tf = posting
                    scores[url] += tf * idf
                    if url not in meta:
                        page = self.pages.get(url)
                        title = page.title if page else ""
                        meta[url] = (origin_url, depth, title)

            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            if limit is not None:
                ranked = ranked[:limit]
            results: List[Tuple[str, str, int, float, str]] = []
            for url, score in ranked:
                origin_url, depth, title = meta.get(url, ("", 0, ""))
                results.append((url, origin_url, depth, score, title))
            return results


index_service = IndexService()
