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
    FeedSource("Anthropic", "https://www.anthropic.com/news/rss.xml", "https://www.anthropic.com/news"),
    FeedSource("xAI", "https://x.ai/blog/rss.xml", "https://x.ai/blog"),
    FeedSource("Spotify", "https://newsroom.spotify.com/feed/", "https://newsroom.spotify.com"),
    FeedSource("Microsoft", "https://blogs.microsoft.com/feed/", "https://blogs.microsoft.com"),
    FeedSource("Google", "https://blog.google/rss/", "https://blog.google"),
    FeedSource("Minecraft", "https://www.minecraft.net/en-us/rss", "https://www.minecraft.net/en-us/articles"),
    FeedSource("Disney", "https://thewaltdisneycompany.com/feed/", "https://thewaltdisneycompany.com"),
    FeedSource("Netflix", "https://about.netflix.com/en/newsroom/rss", "https://about.netflix.com/en/newsroom"),
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


def _parse_feed(source: FeedSource, timeout: int = 10) -> list[dict[str, Any]]:
    headers = {
        "User-Agent": "RootAccessAggregator/1.0 (+https://example.local)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
    }

    response = requests.get(source.feed_url, headers=headers, timeout=timeout)
    response.raise_for_status()

    parsed = feedparser.parse(response.content)
    items: list[dict[str, Any]] = []

    for entry in parsed.entries:
        link = entry.get("link")
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


def aggregate_posts(limit: int = 150) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    posts: list[dict[str, Any]] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=min(8, len(SOURCES))) as executor:
        futures = {executor.submit(_parse_feed, source): source for source in SOURCES}
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
