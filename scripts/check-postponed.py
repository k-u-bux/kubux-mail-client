#!/usr/bin/env python3
"""
Hourly cron script: lists all postponed messages, revives those whose
$until date has been reached by removing postpone + $until and adding unread.

Run via: python3 scripts/check-postponed.py
"""

import subprocess
import json
import re
import sys
import logging
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def run():
    result = subprocess.run(
        ['notmuch', 'search', '--output=summary', '--format=json', '--sort=oldest-first', 'tag:postpone'],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logging.error(f"notmuch search failed: {result.stderr}")
        sys.exit(1)

    try:
        threads = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        logging.error(f"Failed to parse notmuch output: {e}")
        sys.exit(1)

    if not threads:
        logging.info("No postponed messages found.")
        return

    until_pattern = re.compile(r'\$until:(\d{4}-\d{2}-\d{2})')
    today = date.today()

    revived = 0
    still_pending = 0

    for thread in threads:
        subject = thread.get('subject', '(no subject)')
        authors = thread.get('authors', 'unknown')
        tags = thread.get('tags', [])

        until_str = None
        for tag in tags:
            match = until_pattern.match(tag)
            if match:
                until_str = match.group(1)
                break

        if until_str is None:
            print(f"SKIP  {subject} — {authors} (no $until tag)")
            continue

        try:
            until_date = date.fromisoformat(until_str)
        except ValueError:
            print(f"SKIP  {subject} — {authors} ($until:{until_str} invalid)")
            continue

        if today >= until_date:
            thread_id = thread.get('thread')
            query = f'thread:{thread_id} and tag:postpone'
            try:
                subprocess.run(
                    ['notmuch', 'tag', '-postpone', f'-$until:{until_str}', '+unread', query],
                    check=True, capture_output=True, text=True
                )
                print(f"REVIVE {subject} — {authors} ($until:{until_str})")
                revived += 1
            except subprocess.CalledProcessError as e:
                print(f"ERROR {subject} — {authors} ($until:{until_str}): {e.stderr.strip()}")
        else:
            print(f"KEEP   {subject} — {authors} ($until:{until_str})")
            still_pending += 1

    print()
    print(f"Revived: {revived}  Still postponed: {still_pending}")


if __name__ == '__main__':
    run()