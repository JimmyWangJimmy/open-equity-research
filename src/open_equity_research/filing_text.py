from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Iterable


class FilingHTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "p",
        "div",
        "br",
        "tr",
        "li",
        "table",
        "section",
        "article",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth += 1
            return
        if not self._ignored_depth and lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if not self._ignored_depth and lowered in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        joined = html.unescape("".join(self.parts))
        joined = joined.replace("\xa0", " ")
        joined = re.sub(r"[ \t]+", " ", joined)
        joined = re.sub(r"\n[ \t]+", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


def html_to_text(document: str) -> str:
    parser = FilingHTMLTextExtractor()
    parser.feed(document)
    parser.close()
    return parser.text()


def _candidate_sections(text: str, start_pattern: str, end_patterns: Iterable[str]) -> list[str]:
    start_regex = re.compile(start_pattern, re.IGNORECASE | re.MULTILINE)
    end_regexes = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in end_patterns]
    starts = list(start_regex.finditer(text))
    candidates: list[str] = []
    for match in starts:
        start = match.start()
        ends: list[int] = []
        for regex in end_regexes:
            following = regex.search(text, match.end())
            if following:
                ends.append(following.start())
        end = min(ends) if ends else min(len(text), start + 250_000)
        section = text[start:end].strip()
        if 500 <= len(section) <= 300_000:
            candidates.append(section)
    return candidates


def _longest(candidates: list[str], max_chars: int = 200_000) -> str:
    if not candidates:
        return ""
    return max(candidates, key=len)[:max_chars]


def extract_10k_sections(text: str) -> dict[str, str]:
    """Best-effort extraction; headings vary and results require human verification."""
    patterns = {
        "item_1_business": (
            r"^\s*item\s+1[\s.:-]+business\b.*$",
            (r"^\s*item\s+1a[\s.:-]+risk\s+factors\b.*$",),
        ),
        "item_1a_risk_factors": (
            r"^\s*item\s+1a[\s.:-]+risk\s+factors\b.*$",
            (
                r"^\s*item\s+1b[\s.:-]+.*$",
                r"^\s*item\s+1c[\s.:-]+.*$",
                r"^\s*item\s+2[\s.:-]+properties\b.*$",
            ),
        ),
        "item_7_mdna": (
            r"^\s*item\s+7[\s.:-]+management['’]?s\s+discussion.*$",
            (
                r"^\s*item\s+7a[\s.:-]+.*$",
                r"^\s*item\s+8[\s.:-]+financial\s+statements.*$",
            ),
        ),
    }
    return {
        name: _longest(_candidate_sections(text, start_pattern, end_patterns))
        for name, (start_pattern, end_patterns) in patterns.items()
    }
