from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock

from flask import Flask, jsonify, render_template, request

from root_access.feeds import aggregate_posts

app = Flask(__name__, template_folder="root_access/templates", static_folder="root_access/static")

_CACHE_LOCK = Lock()
_CACHE_TTL = timedelta(minutes=10)
_CACHE: dict[str, object] = {
    "posts": [],
    "companies": [],
    "errors": [],
    "fetched_at": datetime.fromtimestamp(0, tz=timezone.utc),
}


def get_posts(force_refresh: bool = False) -> tuple[list[dict], list[str], list[str], datetime]:
    now = datetime.now(timezone.utc)
    with _CACHE_LOCK:
        fetched_at = _CACHE["fetched_at"]
        stale = now - fetched_at > _CACHE_TTL
        if force_refresh or stale or not _CACHE["posts"]:
            posts, companies, errors = aggregate_posts()
            _CACHE.update({"posts": posts, "companies": companies, "errors": errors, "fetched_at": now})
        return _CACHE["posts"], _CACHE["companies"], _CACHE["errors"], _CACHE["fetched_at"]


@app.get("/")
def home():
    force_refresh = request.args.get("refresh") == "1"
    posts, companies, errors, fetched_at = get_posts(force_refresh=force_refresh)
    return render_template(
        "index.html",
        posts=posts,
        companies=companies,
        errors=errors,
        fetched_at=fetched_at.strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.get("/api/posts")
def posts_api():
    posts, companies, errors, fetched_at = get_posts(force_refresh=request.args.get("refresh") == "1")
    return jsonify(
        {
            "fetched_at": fetched_at.isoformat(),
            "count": len(posts),
            "companies": companies,
            "errors": errors,
            "posts": posts,
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
