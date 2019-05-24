#!/usr/bin/env python
# __author__ = "Ronie Martinez"
# __copyright__ = "Copyright 2019, Ronie Martinez"
# __credits__ = ["Ronie Martinez"]
# __license__ = "MIT"
# __maintainer__ = "Ronie Martinez"
# __email__ = "ronmarti18@gmail.com"
import logging
import os
import re
import sys
import time

from goose3 import Goose
from praw.models import Submission
from rfc3986 import is_valid_uri
from summarize import summarize

from client import get_redis_client

logging.basicConfig(stream=sys.stdout, level=logging.INFO)


retry_pattern = re.compile(r'again in (?P<number>[0-9]+) (?P<unit>\w+)s?\.$', re.IGNORECASE)

message_format = """
Title: {title}

Summary: {summary}

---------
I am a bot that summarizes content of a URL-only submission!
"""


def handle_rate_limit(exc):
    time_map = {
        'second': 1,
        'minute': 60,
        'hour': 60 * 60,
    }
    matches = retry_pattern.search(exc.message)
    delay = int(matches[0]) * time_map[matches[1]]
    time.sleep(delay + 1)


def main():
    import praw
    reddit = praw.Reddit(
        client_id=os.getenv('CLIENT_ID'),
        client_secret=os.getenv('CLIENT_SECRET'),
        username=os.getenv('BOT_USERNAME'),
        password=os.getenv('BOT_PASSWORD'),
        user_agent=os.getenv('BOT_USER_AGENT'),
    )
    redis_client = get_redis_client()
    for submission in reddit.subreddit('SiteSummarizerBot').stream.submissions(skip_existing=True):  # type: Submission
        text = submission.selftext.strip()
        url = None
        if is_valid_uri(text, require_scheme=True):
            url = text
        else:
            continue
        replied_key = f"replied:{submission.id}"
        if url and not redis_client.exists(replied_key):
            logging.info(f'URL found in submission {submission.id}, extracting summary: {url}')
            g = Goose({'strict': False})
            article = g.extract(url=url)

            summary = summarize(article.cleaned_text).strip()
            if len(summary):
                try:
                    message = message_format.format(title=article.title, summary=summary)
                    logging.info(message)
                    # submission.reply(message)
                except praw.exceptions.ApiException as e:
                    if e.error_type == 'RATELIMIT':
                        handle_rate_limit(e)
                    else:
                        logging.exception(e)
                        raise

                redis_client.set(replied_key, time.time())
                logging.info(f'Commented summary to submission {submission.id}')
            else:
                logging.info(f"Cannot find contents in URL: {url}")


if __name__ == '__main__':
    main()
