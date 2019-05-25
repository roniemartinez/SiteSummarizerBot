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
import threading
import time

import praw
from goose3 import Goose
from praw.models import Submission, Comment, Redditor
from praw.models.util import stream_generator
from rfc3986 import is_valid_uri
from summarize import summarize

from client import get_redis_client

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

retry_pattern = re.compile(r'again in ([0-9]+) (\w+)\.$', re.IGNORECASE)

message_format = """
#### {title}

#### Summary:

{summary}

------------------------------------------------------------
I am a bot that summarizes content of a URL-only submission!
"""


def handle_rate_limit(message):
    multiplier = {
        'second': 1,
        'seconds': 1,
        'minute': 60,
        'minutes': 60,
        'hour': 60 * 60,
        'hours': 60 * 60,
    }
    matches = retry_pattern.search(message)
    delay = (int(matches[1]) * multiplier[matches[2]]) + 1
    logging.info(f'Sleeping for {delay} seconds')
    time.sleep(delay)


def get_url(submission: Submission):
    url = None
    if submission.is_self:
        text = submission.selftext.strip()
        if len(text) and is_valid_uri(text, require_scheme=True):
            url = text
            logging.info(f'URL found in submission {submission.id}: {url}')
        else:
            logging.info(f'URL not found in submission {submission.id}')
    else:
        url = submission.url
        logging.info(f'URL found in submission {submission.id}: {url}')
    return url


def submissions():
    reddit = get_reddit()
    redis_client = get_redis_client()
    logging.info('Listening to submission stream')
    for submission in reddit.subreddit('SiteSummarizerBot').stream.submissions(skip_existing=True):  # type: Submission

        replied_key = f"replied:submission:{submission.id}"
        if redis_client.exists(replied_key):
            logging.info(f'Already replied to submission {submission.id}')
            continue

        url = get_url(submission)
        title, summary = extract_summary(url)

        if len(summary):
            while True:
                try:
                    message = message_format.format(title=title, summary=summary)
                    submission.reply(message)
                    redis_client.set(replied_key, time.time())
                    logging.info(f'Commented summary to submission {submission.id}')
                    break
                except praw.exceptions.APIException as e:
                    if e.error_type == 'RATELIMIT':
                        logging.info('RATELIMIT detected')
                        handle_rate_limit(e.message)
                    else:
                        logging.exception(e)
                        break
        else:
            logging.info(f'Cannot find contents in URL: {url}')


def extract_summary(url):
    g = Goose({'strict': False})
    article = g.extract(url=url)
    summary = summarize(article.cleaned_text).strip()
    return article.title, summary


def get_reddit():
    return praw.Reddit(
        client_id=os.getenv('CLIENT_ID'),
        client_secret=os.getenv('CLIENT_SECRET'),
        username=os.getenv('BOT_USERNAME'),
        password=os.getenv('BOT_PASSWORD'),
        user_agent=os.getenv('BOT_USER_AGENT'),
    )


def mentions():
    reddit = get_reddit()
    redis_client = get_redis_client()
    logging.info('Listening to mentions')
    for mention in stream_generator(reddit.inbox.mentions, skip_existing=True):  # type: Comment
        mention.mark_read()
        submission = mention.submission  # type: Submission

        replied_key = f"replied:comment:{mention.id}"
        if redis_client.exists(replied_key):
            logging.info(f'Already replied to mention {mention.id}')
            continue

        url = get_url(submission)
        title, summary = extract_summary(url)

        if len(summary):
            while True:
                try:
                    message = message_format.format(title=title, summary=summary)
                    mention.reply(message)
                    redis_client.set(replied_key, time.time())
                    logging.info(f'Replied summary to mention {mention.id}')
                    break
                except praw.exceptions.APIException as e:
                    if e.error_type == 'RATELIMIT':
                        logging.info('RATELIMIT detected')
                        handle_rate_limit(e.message)
                    else:
                        logging.exception(e)
                        break
        else:
            logging.info(f'Cannot find contents in URL: {url}')
    time.sleep(60)


def downvote_deleter():
    reddit = get_reddit()
    logging.info('Listening to downvotes')
    user = Redditor(reddit, 'SiteSummarizerBot')
    for comment in stream_generator(user.comments.new):  # type: Comment
        if comment.score < 1:
            comment.delete()
            logging.info(f'Removed downvoted comment {comment.id}')


def main():
    threads = [
        threading.Thread(target=submissions),
        threading.Thread(target=mentions),
        threading.Thread(target=downvote_deleter)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == '__main__':
    main()
