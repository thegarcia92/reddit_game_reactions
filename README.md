A personal, non-commercial, open-source Python script for sports fans to receive real-time personal alerts when high-intensity plays or game-changing moments occur in live Reddit game threads (`r/nba`, `r/nfl`, `r/soccer`).

## Purpose & Scope
- This tool only reads public comments from official "Game Thread" submissions. It does not post, upvote, downvote, or modify Reddit content in any way.
- Calculates rolling comment velocity to detect viral plays (e.g., buzzer-beaters, controversial calls) and sends a private alert to the user's personal Telegram chat.
- Built strictly for personal hobbyist use. Adheres to Reddit API rate limits, uses exponential backoff, and respects all Reddit Developer Policies.

## How It Works
1. Identifies active "Game Thread" posts in designated sports subreddits.
2. Periodically polls the latest comments using Reddit's OAuth API.
3. Tracks comment velocity over a 120-second rolling window.
4. When comment velocity triples the baseline, a personal highlight notification is sent to the user.

## Setup
1. Clone the repository:
   ```bash
   git clone https://github.com/thegarcia92/reddit-sports-game-alert.git
   cd reddit-sports-game-alert
2. Install dependencies:
  pip install -r requirements.txt

3. Set your environment variables in .env:
  REDDIT_CLIENT_ID=your_client_id
  REDDIT_CLIENT_SECRET=your_client_secret
  REDDIT_USER_AGENT=script:game_thread_alert:v1.0 (by /u/thegarcia92)
  TELEGRAM_BOT_TOKEN=your_telegram_bot_token
  TELEGRAM_CHAT_ID=your_telegram_chat_id

5. Run the script:
  python monitor.py
