import json
import os
import re
from pathlib import Path

import feedparser
import requests

CHANNEL_HANDLE = os.getenv("YOUTUBE_HANDLE", "@aung3d").strip()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@happydayfor").strip()
STATE_FILE = Path("sent_videos.json")
MAX_SAVED_VIDEOS = 5000


def get_channel_id(handle: str) -> str:
    url = f"https://www.youtube.com/{handle}"
    response = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    response.raise_for_status()

    patterns = (
        r'"channelId":"(UC[a-zA-Z0-9_-]+)"',
        r'"externalId":"(UC[a-zA-Z0-9_-]+)"',
        r'channel/(UC[a-zA-Z0-9_-]+)',
    )
    for pattern in patterns:
        match = re.search(pattern, response.text)
        if match:
            return match.group(1)

    raise RuntimeError(f"Could not find YouTube channel ID for {handle}")


def load_sent() -> set[str]:
    if not STATE_FILE.exists():
        return set()

    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data) if isinstance(data, list) else set()
    except (OSError, json.JSONDecodeError):
        print("Warning: sent_videos.json is invalid; starting with an empty state.")
        return set()


def save_sent(sent: set[str]) -> None:
    STATE_FILE.write_text(
        json.dumps(sorted(sent)[-MAX_SAVED_VIDEOS:], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def telegram_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]

    return payload.get("description") or json.dumps(payload, ensure_ascii=False)


def validate_telegram() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing. Add it in GitHub Actions Secrets."
        )
    if not CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID is missing. Use @channelusername or a numeric chat ID."
        )

    # This gives a clear error before trying to send messages.
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"
    response = requests.post(url, json={"chat_id": CHAT_ID}, timeout=30)
    if not response.ok:
        raise RuntimeError(
            f"Telegram getChat failed for {CHAT_ID!r}: "
            f"{telegram_error_message(response)}"
        )


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            f"Telegram sendMessage failed for {CHAT_ID!r}: "
            f"{telegram_error_message(response)}"
        )


def main() -> None:
    print(f"Checking YouTube channel {CHANNEL_HANDLE}...")
    validate_telegram()

    channel_id = get_channel_id(CHANNEL_HANDLE)
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)

    if getattr(feed, "bozo", False) and not feed.entries:
        raise RuntimeError(
            f"Could not read YouTube RSS feed: {feed.bozo_exception}"
        )

    sent = load_sent()
    new_entries = []

    for entry in feed.entries:
        video_id = entry.get("yt_videoid") or entry.get("id", "").split(":")[-1]
        if video_id and video_id not in sent:
            new_entries.append((entry, video_id))

    # RSS is newest-first. Send oldest unseen video first.
    for entry, video_id in reversed(new_entries):
        title = entry.get("title", "New YouTube video")
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        message = f"🎬 New video from Aung3D\n\n{title}\n\n{video_url}"

        send_telegram(message)
        sent.add(video_id)
        print(f"Sent: {title} ({video_id})")

    save_sent(sent)
    print(
        f"Done. Checked {CHANNEL_HANDLE}: "
        f"{len(new_entries)} new video(s) sent to {CHAT_ID}."
    )


if __name__ == "__main__":
    main()
