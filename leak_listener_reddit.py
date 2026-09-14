import os
import logging
import re
from fuzzywuzzy import process
import praw
from datetime import datetime

logger = logging.getLogger(__name__)

class RedditListener:
    def __init__(self, client_id, client_secret, user_agent, subreddits, keywords=None):
        self.reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
        self.subreddits = subreddits
        self.keywords = keywords or ['TOTW','IF','inform','TOTS','SBC','promo','team of the week']

    def poll_new_posts(self, limit=50):
        """
        Polls configured subreddits and yields (title, selftext, url) tuples
        """
        for sub in self.subreddits:
            try:
                subreddit = self.reddit.subreddit(sub)
                for post in subreddit.new(limit=limit):
                    text = f"{post.title}\n{post.selftext or ''}"
                    # quick keyword filter
                    if any(k.lower() in text.lower() for k in self.keywords):
                        yield {'text': text, 'url': post.url, 'created_utc': datetime.fromtimestamp(post.created_utc)}
            except Exception:
                logger.exception("Failed to poll subreddit %s", sub)

    def extract_player_mentions(self, text, candidate_player_names, limit=3):
        cleaned = re.sub(r"[^A-Za-z0-9\s]", " ", text)
        results = process.extract(cleaned, candidate_player_names, limit=limit)
        return results
