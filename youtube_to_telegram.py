import json
import os
import re
from pathlib import Path

import feedparser
import requests

CHANNEL_HANDLE = os.getenv("YOUTUBE_HANDLE", "@aung3d")
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"].strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@happydayfor").strip()
STATE_FILE = Path("sent_videos.json")


def get_channel_id(handle: str) -> str:
    url = f"https://www.youtube.com/{handle}"
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    patterns = [
        r'"channelId":"(UC[a-zA-Z0-9_-]+)"',
        r'"externalId":"(UC[a-zA-Z0-9_-]+)"',
        r'channel/(UC[a-zA-Z0-9_-]+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, r.text)
        if m:
            return m.group(1)
    raise RuntimeError("Could not find YouTube channel ID")


def load_sent() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data if isinstance(data, list) else [])
    except Exception:
        return set()


def save_sent(sent: set[str]) -> None:
    # Keep the state small while retaining enough history to prevent duplicates.
    STATE_FILE.write_text(
        json.dumps(sorted(sent)[-5000:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(
        url,
        data={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": False},
        timeout=30,
    )
    r.raise_for_status()
    result = r.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")


def main() -> None:
    channel_id = get_channel_id(CHANNEL_HANDLE)
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)
    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(f"Could not read YouTube RSS feed: {feed.bozo_exception}")

    sent = load_sent()
    new_entries = []
    for entry in feed.entries:
        video_id = entry.get("yt_videoid") or entry.get("id", "").split(":")[-1]
        if video_id and video_id not in sent:
            new_entries.append((entry, video_id))

    # RSS is newest-first. Send oldest first if several videos appeared between runs.
    for entry, video_id in reversed(new_entries):
        title = entry.get("title", "New YouTube video")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        message = f"🎬 New video from Aung3D\n\n{title}\n\n{video_url}"
        send_telegram(message)
        sent.add(video_id)

    save_sent(sent)
    print(f"Checked {CHANNEL_HANDLE}: {len(new_entries)} new video(s) sent.")


if __name__ == "__main__":
    main()
