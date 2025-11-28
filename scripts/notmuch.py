import sys
import subprocess
import json
import os
from pathlib import Path
from email.utils import getaddresses
import re
from datetime import datetime, timezone
import logging

def notmuch_show(query, sort, flag_error):
    try:
        command = [
            'notmuch',
            'show',
            '--format=json',
            '--body=false',
            f'--sort={sort}',
            query
        ]
        
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    except subprocess.CalledProcessError as e:
        flag_error(
            "Notmuch Query Failed",
            f"An error occurred while running notmuch:\n\n{e.stderr}"
        )
        os.exit(1)

    except json.JSONDecodeError as e:
        flag_error(
            "Notmuch Output Error",
            f"Failed to parse JSON output from notmuch:\n\n{e}"
        )
        os.exit(1)


# def flatten_message_tree(list_of_threads):
#     # todo: make this less recursive (never run into the stack limit)
#     message_list = []
#     def flatten_message_thread_pair(the_pair,depth):
#         # a pair is a message (dict) followed by a list of message pairs
#         msg = the_pair[0]
#         msg["depth"] = depth
#         message_list.append(msg)
#         for msg_t_pair in the_pair[1]:
#             flatten_message_thread_pair(msg_t_pair, depth+1)
#     for thread in list_of_threads:
#         for message_thread_pair in thread:
#             flatten_message_thread_pair(message_thread_pair,0)
#     return message_list

def flatten_message_tree(list_of_threads):
    message_list = []
    stack = []
    for thread in reversed(list_of_threads):
        for message_thread_pair in reversed(thread):
            stack.append((message_thread_pair, 0))
    while stack:
        the_pair, depth = stack.pop()
        msg = the_pair[0]
        msg["depth"] = depth
        message_list.append(msg)
        for reply_pair in reversed(the_pair[1]):
            stack.append((reply_pair, depth + 1))
    return message_list


def find_matching_messages(query, flag_error):
    list_of_messages = flatten_message_tree( notmuch_show(query, "newest-first", flag_error) )
    result = []
    for msg in list_of_messages:
        if msg["match"]:
            result.append( msg )
    return result


def notmuch_search(query, output, sort, flag_error):
    try:
        command = [
            'notmuch',
            'search',
            '--format=json',
            f'--output={output}',
            f'--sort={sort}',
            query
        ]
        
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    except subprocess.CalledProcessError as e:
        flag_error(
            "Notmuch Query Failed",
            f"An error occurred while running notmuch:\n\n{e.stderr}"
        )
        os.exit(1)

    except json.JSONDecodeError as e:
        flag_error(
            "Notmuch Output Error",
            f"Failed to parse JSON output from notmuch:\n\n{e}"
        )
        os.exit(1)


def find_matching_threads(query, flag_error):
    list_of_threads = notmuch_search(query, "summary", "newest-first", flag_error)
    return list_of_threads



def apply_tag_to_query(pm_tag, query, flag_error):
    # notmuch tag <pm_tag> <query>
    try:
        command = [
            'notmuch',
            'tag',
            f"{pm_tag}",
            '--',
            f"{query}"
        ]
        print(f"applying tag = {pm_tag} to query = {query}" )
        result = subprocess.run(command, check=True)

    except subprocess.CalledProcessError as e:
        flag_error(
            "Notmuch Query Failed",
            f"An error occurred while running notmuch:\n\n{e.stderr}"
        )
        os.exit(1)

    except Exception as e:
        flag_error(
            "Something happened.",
            f"Caught Exception: {e}"
        )
        os.exit(1)

def get_tags_from_query(query, flag_error):
    try:
        command = ['notmuch', 'search', '--output=tags', '--format=text', f'{query} and (tag:spam or not tag:spam)']
        result = subprocess.run(command, capture_output=True, text=True, check=True)            
        tags_list = [tag.strip() for tag in result.stdout.strip().split('\n') if tag.strip()]
        tags = sorted(tags_list)
    except subprocess.CalledProcessError as e:
        flag_error(
            "Notmuch Command Failed",
            f"An error occurred while running notmuch:\n\n{e.stderr}\n\nCommand was: {' '.join(command)}"
        )
        tags = []
    return tags

def update_unseen_from_query( query, flag_error ):
    tags = get_tags_from_query( query, flag_error )
    if '$unseen' in tags:
        logging.info("Found '$unseen' tag. Silently replacing with '$unused'.")
        apply_tag_to_query( '+$unused', query, flag_error )
        apply_tag_to_query( '-$unseen', query, flag_error )
