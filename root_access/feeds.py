from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlparse

import feedparser
import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class FeedSource:
    company: str
    feed_url: str
    homepage: str


SOURCES: list[FeedSource] = [
    FeedSource("OpenAI", "https://openai.com/news/rss.xml", "https://openai.com/news"),
    FeedSource("Anthropic", "https://www.anthropic.com/news", "https://www.anthropic.com/news"),
    FeedSource("xAI", "https://x.ai/news", "https://x.ai/news"),
    FeedSource("Spotify", "https://newsroom.spotify.com/feed/", "https://newsroom.spotify.com"),
    FeedSource("Microsoft", "https://blogs.microsoft.com/feed/", "https://blogs.microsoft.com"),
    FeedSource("Google", "https://blog.google/rss/", "https://blog.google"),
    FeedSource("Minecraft", "https://www.minecraft.net/en-us/articles", "https://www.minecraft.net/en-us/articles"),
    FeedSource("Disney", "https://thewaltdisneycompany.com/feed/", "https://thewaltdisneycompany.com"),
    FeedSource("Netflix", "https://about.netflix.com/en/newsroom", "https://about.netflix.com/en/newsroom"),
    FeedSource("Amazon", "https://www.aboutamazon.com/news", "https://www.aboutamazon.com/news"),
    FeedSource("Paramount", "https://www.paramount.com/news", "https://www.paramount.com/news"),
    FeedSource("Warner Bros", "https://www.warnerbrosdiscovery.com/news-and-insights", "https://www.warnerbrosdiscovery.com/news-and-insights"),
]

_SKIP_TITLE_PATTERNS = {
    "news",
    "newsroom",
    "about",
    "company",
    "careers",
    "investors",
    "contact",
    "subscribe",
    "locations",
    "brands",
    "board of directors",
    "leadership",
    "events & webcasts",
    "press releases",
    "sec filings",
    "quarterly results",
}
_SKIP_URL_SEGMENTS = {
    "about",
    "careers",
    "contact",
    "investors",
    "privacy",
    "terms",
    "support",
    "locations",
    "brands",
    "leadership",
    "board",
    "events",
    "webcasts",
    "jobs",
    "login",
}


def _to_datetime(struct_time: Any, fallback: str | None = None) -> datetime:
    if struct_time is not None:
        return datetime(*struct_time[:6], tzinfo=timezone.utc)
    if fallback:
        try:
            parsed = parsedate_to_datetime(fallback)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError):
            pass
    return datetime.now(timezone.utc)


def _extract_date_from_text(text: str) -> datetime | None:
    text = text.strip()
    if not text:
        return None
    patterns = [
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            return _to_datetime(None, match.group(0))
        except Exception:  # noqa: BLE001
            continue
    return None


def _extract_image(entry: Any) -> str | None:
    if entry.get("media_content"):
        media_item = entry.media_content[0]
        if isinstance(media_item, dict) and media_item.get("url"):
            return media_item["url"]

    if entry.get("media_thumbnail"):
        thumb = entry.media_thumbnail[0]
        if isinstance(thumb, dict) and thumb.get("url"):
            return thumb["url"]

    for enclosure in entry.get("enclosures", []):
        href = enclosure.get("href") if isinstance(enclosure, dict) else None
        media_type = enclosure.get("type", "") if isinstance(enclosure, dict) else ""
        if href and media_type.startswith("image/"):
            return href

    html_candidates = [entry.get("summary"), entry.get("content", [{}])[0].get("value") if entry.get("content") else None]
    for html in html_candidates:
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img["src"]
    return None


def _normalize_url(link: str | None, source: FeedSource) -> str | None:
    if not link:
        return None
    if link.startswith("http://") or link.startswith("https://"):
        return link
    return f"{source.homepage.rstrip('/')}/{link.lstrip('/')}"


def _is_likely_article_link(link: str, source: FeedSource) -> bool:
    parsed = urlparse(link)
    if not parsed.netloc:
        return False

    home = urlparse(source.homepage)
    if parsed.netloc != home.netloc:
        return False

    path = parsed.path.lower().strip("/")
    if not path:
        return False
    if path in {"news", "newsroom", "blog", "articles"}:
        return False

    segments = [seg for seg in path.split("/") if seg]
    if len(segments) < 2:
        return False
    if any(seg in _SKIP_URL_SEGMENTS for seg in segments):
        return False

    article_hint = any(token in path for token in ["news", "blog", "article", "press", "stories", "post"])
    has_date_hint = bool(re.search(r"\b20\d{2}\b", path))
    return article_hint or has_date_hint


def _clean_summary(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_likely_article_title(title: str) -> bool:
    clean = _clean_summary(title).lower()
    if not clean or clean in _SKIP_TITLE_PATTERNS:
        return False
    if len(clean) < 12:
        return False
    if len(clean.split()) < 3:
        return False
    return True


def _parse_rss_source(source: FeedSource, timeout: int = 18) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RootAccessAggregator/2.1)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.7",
    }

    response = requests.get(source.feed_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)

    items: list[dict[str, Any]] = []
    for entry in parsed.entries:
        link = _normalize_url(entry.get("link"), source)
        if not link or not _is_likely_article_link(link, source):
            continue

        title = entry.get("title", "Untitled")
        if not _is_likely_article_title(title):
            continue

        published = _to_datetime(entry.get("published_parsed") or entry.get("updated_parsed"), entry.get("published") or entry.get("updated"))
        items.append(
            {
                "company": source.company,
                "title": title,
                "link": link,
                "published": published,
                "published_iso": published.isoformat(),
                "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True),
                "image": _extract_image(entry),
                "source_homepage": source.homepage,
            }
        )

    return items


def _extract_from_json_ld(soup: BeautifulSoup, source: FeedSource) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        if not script.string:
            continue
        try:
            payload = json.loads(script.string)
        except json.JSONDecodeError:
            continue

        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                nodes.extend(graph)

            ntype = str(node.get("@type", "")).lower()
            if not any(t in ntype for t in ["article", "newsarticle", "blogposting"]):
                continue

            title = node.get("headline") or node.get("name") or ""
            link = _normalize_url(node.get("url"), source)
            if not title or not link:
                continue
            if not _is_likely_article_title(title) or not _is_likely_article_link(link, source):
                continue

            date_value = node.get("datePublished") or node.get("dateCreated")
            published = _to_datetime(None, date_value) if date_value else datetime.now(timezone.utc)

            image = None
            image_node = node.get("image")
            if isinstance(image_node, str):
                image = _normalize_url(image_node, source)
            elif isinstance(image_node, list) and image_node:
                image = _normalize_url(str(image_node[0]), source)
            elif isinstance(image_node, dict) and image_node.get("url"):
                image = _normalize_url(image_node["url"], source)

            summary = node.get("description", "")
            items.append(
                {
                    "company": source.company,
                    "title": _clean_summary(title),
                    "link": link,
                    "published": published,
                    "published_iso": published.isoformat(),
                    "summary": _clean_summary(summary),
                    "image": image,
                    "source_homepage": source.homepage,
                }
            )
    return items


def _parse_html_source(source: FeedSource, timeout: int = 18) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RootAccessAggregator/2.1)"}
    response = requests.get(source.feed_url, headers=headers, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    items = _extract_from_json_ld(soup, source)

    for card in soup.select("article, [class*='article'], [class*='post'], [class*='news']")[:120]:
        link_tag = card.select_one("a[href]")
        if not link_tag:
            continue

        title_tag = card.select_one("h1, h2, h3, h4") or link_tag
        title = _clean_summary(title_tag.get_text(" ", strip=True))
        if not _is_likely_article_title(title):
            continue

        link = _normalize_url(link_tag.get("href"), source)
        if not link or not _is_likely_article_link(link, source):
            continue

        summary_tag = card.select_one("p")
        summary = _clean_summary(summary_tag.get_text(" ", strip=True)) if summary_tag else ""

        dt_tag = card.select_one("time")
        dt_value = dt_tag.get("datetime") if dt_tag else dt_tag.get_text(" ", strip=True) if dt_tag else None
        published = _to_datetime(None, dt_value) if dt_value else None
        if published is None:
            published = _extract_date_from_text(title) or _extract_date_from_text(summary) or _extract_date_from_text(link)
        if published is None:
            # Skip unknown-timestamp items; these are usually nav links in scraped pages.
            continue

        image = None
        img_tag = card.select_one("img[src]")
        if img_tag:
            image = _normalize_url(img_tag.get("src"), source)

        items.append(
            {
                "company": source.company,
                "title": title,
                "link": link,
                "published": published,
                "published_iso": published.isoformat(),
                "summary": summary,
                "image": image,
                "source_homepage": source.homepage,
            }
        )

    dedup: dict[str, dict[str, Any]] = {}
    for item in items:
        dedup.setdefault(item["link"], item)

    return list(dedup.values())[:30]


def _parse_source(source: FeedSource) -> list[dict[str, Any]]:
    if source.feed_url.endswith(".xml") or "/feed" in source.feed_url or "/rss" in source.feed_url:
        try:
            items = _parse_rss_source(source)
            if items:
                return items
        except Exception:  # noqa: BLE001
            pass
    return _parse_html_source(source)


def aggregate_posts(limit: int = 150) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    posts: list[dict[str, Any]] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=min(10, len(SOURCES))) as executor:
        futures = {executor.submit(_parse_source, source): source for source in SOURCES}
        for future in as_completed(futures):
            source = futures[future]
            try:
                posts.extend(future.result())
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{source.company}: {exc}")

    posts.sort(key=lambda p: p["published"], reverse=True)
    for post in posts:
        post["published_display"] = post["published"].strftime("%b %d, %Y %H:%M UTC")

    companies = sorted({p["company"] for p in posts})
    return posts[:limit], companies, errors
