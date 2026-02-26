from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

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


def _parse_rss_source(source: FeedSource, timeout: int = 18) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RootAccessAggregator/2.0)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.7",
    }

    response = requests.get(source.feed_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)

    items: list[dict[str, Any]] = []
    for entry in parsed.entries:
        link = _normalize_url(entry.get("link"), source)
        if not link:
            continue

        published = _to_datetime(entry.get("published_parsed") or entry.get("updated_parsed"), entry.get("published") or entry.get("updated"))
        items.append(
            {
                "company": source.company,
                "title": entry.get("title", "Untitled"),
                "link": link,
                "published": published,
                "published_iso": published.isoformat(),
                "summary": BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True),
                "image": _extract_image(entry),
                "source_homepage": source.homepage,
            }
        )

    return items


def _parse_html_source(source: FeedSource, timeout: int = 18) -> list[dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RootAccessAggregator/2.0)"}
    response = requests.get(source.feed_url, headers=headers, timeout=timeout)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    items: list[dict[str, Any]] = []

    cards = soup.select("article, .article, .post, li")
    for card in cards[:80]:
        link_tag = card.select_one("a[href]")
        if not link_tag:
            continue

        title_tag = card.select_one("h1, h2, h3, h4") or link_tag
        title = title_tag.get_text(" ", strip=True)
        if not title or len(title) < 5:
            continue

        link = _normalize_url(link_tag.get("href"), source)
        if not link:
            continue

        summary_tag = card.select_one("p")
        summary = summary_tag.get_text(" ", strip=True) if summary_tag else ""

        dt_tag = card.select_one("time")
        published = _to_datetime(None, dt_tag.get("datetime") if dt_tag else dt_tag.get_text(" ", strip=True) if dt_tag else None)

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

    # de-dup links and keep top 20
    dedup: dict[str, dict[str, Any]] = {}
    for item in items:
        dedup.setdefault(item["link"], item)
    return list(dedup.values())[:20]


def _parse_source(source: FeedSource) -> list[dict[str, Any]]:
    if source.feed_url.endswith(".xml") or "/feed" in source.feed_url or "/rss" in source.feed_url:
        try:
            return _parse_rss_source(source)
        except Exception:  # noqa: BLE001
            return _parse_html_source(source)
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
