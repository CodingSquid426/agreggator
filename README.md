# Root Access

Root Access is a company blog aggregator that pulls the latest posts from major official company blogs and newsrooms, then displays them in one chronological feed with direct links to the original source.

## Included Sources
- OpenAI
- Anthropic
- xAI
- Spotify
- Microsoft
- Google
- Minecraft
- Disney
- Netflix

## Features
- Automatic aggregation from multiple RSS/Atom feeds.
- Chronological sorting across all sources.
- Card-based UI with preview images (when available).
- Direct outbound links to original posts.
- Search + source filters.
- Dark/light theme toggle.
- Refresh-on-demand.
- Feed error reporting for partial outages.
- JSON API endpoint at `/api/posts`.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Then open `http://localhost:8000`.
