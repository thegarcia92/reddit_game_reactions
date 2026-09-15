"""
Reddit Sports Game Thread Notifier
A personal, read-only Python utility that tracks comment velocity in sports
game threads and sends personal highlight notifications.
"""

import asyncio
import collections
import logging
import os
import time
from typing import Deque, Dict, List, Set, Tuple
import aiohttp
from dotenv import load_dotenv

load_dotenv()

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "script:game_thread_alert:v1.0 (by /u/username)")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TARGET_SUBREDDITS = ["nba", "nfl", "soccer"]
POLL_INTERVAL = 5.0
COOLDOWN_SECONDS = 90

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("GameNotifier")


class GameThreadNotifier:
    def __init__(self):
        self.access_token = None
        self.token_expiry = 0
        self.seen_comment_ids: Set[str] = set()
        self.recent_ids_queue: Deque[str] = collections.deque(maxlen=2000)
        self.windows: Dict[str, Deque[float]] = collections.defaultdict(collections.deque)
        self.last_alert_time: Dict[str, float] = {}

    async def get_token(self, session: aiohttp.ClientSession) -> str:
        now = time.time()
        if self.access_token and now < self.token_expiry - 60:
            return self.access_token

        auth = aiohttp.BasicAuth(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)
        data = {"grant_type": "client_credentials"}
        headers = {"User-Agent": REDDIT_USER_AGENT}

        async with session.post("https://www.reddit.com/api/v1/access_token", auth=auth, data=data, headers=headers) as resp:
            if resp.status == 200:
                result = await resp.json()
                self.access_token = result["access_token"]
                self.token_expiry = now + result.get("expires_in", 3600)
                return self.access_token
            raise RuntimeError(f"Reddit OAuth failed: {resp.status}")

    async def send_personal_alert(self, session: aiohttp.ClientSession, title: str, subreddit: str, ratio: float):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            logger.info(f"[ALERT] Highlight on r/{subreddit}: {title} (Velocity: {ratio:.1f}x)")
            return

        text = (
            f"🏀 *Live Sports Highlight Alert!*\n\n"
            f"📌 *Thread*: {title} (r/{subreddit})\n"
            f"⚡ *Spike Ratio*: `{ratio:.1f}x` normal baseline\n"
            f"Check the game thread for highlights!"
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                logger.info("Personal alert delivered to Telegram successfully.")

    async def discover_threads(self, session: aiohttp.ClientSession) -> List[Tuple[str, str, str]]:
        token = await self.get_token(session)
        headers = {"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT}
        threads = []

        for sub in TARGET_SUBREDDITS:
            url = f"https://oauth.reddit.com/r/{sub}/hot?limit=25"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("data", {}).get("children", []):
                        post = item.get("data", {})
                        title = post.get("title", "")
                        sub_id = post.get("id", "")
                        if "game thread:" in title.lower() or (post.get("stickied") and "game thread" in title.lower()):
                            threads.append((sub_id, title, sub))
        return threads

    def check_velocity_spike(self, sub_id: str, now: float) -> Tuple[bool, float]:
        win = self.windows[sub_id]
        while win and win[0] < now - 120.0:
            win.popleft()

        if len(win) < 15:
            return False, 0.0

        recent_count = sum(1 for t in win if t >= now - 30.0)
        trailing_count = len(win) - recent_count

        recent_rate = recent_count / 30.0
        trailing_rate = max(trailing_count / 90.0, 0.5)
        ratio = recent_rate / trailing_rate
        return (recent_rate > 3.0 * trailing_rate), ratio

    async def poll_comments(self, session: aiohttp.ClientSession, sub_id: str, title: str, sub: str):
        token = await self.get_token(session)
        headers = {"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT}
        url = f"https://oauth.reddit.com/comments/{sub_id}?sort=new&limit=50"

        async with session.get(url, headers=headers) as resp:
            if resp.status == 429:
                retry_after = int(resp.headers.get("Retry-After", 15))
                await asyncio.sleep(retry_after)
                return

            if resp.status != 200:
                return

            data = await resp.json()
            if not isinstance(data, list) or len(data) < 2:
                return

            comments = data[1].get("data", {}).get("children", [])
            now = time.time()

            for item in comments:
                cid = item.get("data", {}).get("id")
                if not cid or cid in self.seen_comment_ids:
                    break

                if len(self.recent_ids_queue) >= 2000:
                    old_id = self.recent_ids_queue.popleft()
                    self.seen_comment_ids.discard(old_id)

                self.recent_ids_queue.append(cid)
                self.seen_comment_ids.add(cid)
                self.windows[sub_id].append(item.get("data", {}).get("created_utc", now))

            is_spike, ratio = self.check_velocity_spike(sub_id, now)
            last_alert = self.last_alert_time.get(sub_id, 0.0)

            if is_spike and (now - last_alert > COOLDOWN_SECONDS):
                self.last_alert_time[sub_id] = now
                await self.send_personal_alert(session, title, sub, ratio)

    async def run(self):
        logger.info("Starting personal sports game thread monitor...")
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    threads = await self.discover_threads(session)
                    for sub_id, title, sub in threads:
                        await self.poll_comments(session, sub_id, title, sub)
                        await asyncio.sleep(1.0)
                    await asyncio.sleep(POLL_INTERVAL)
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    await asyncio.sleep(10.0)


if __name__ == "__main__":
    notifier = GameThreadNotifier()
    asyncio.run(notifier.run())
