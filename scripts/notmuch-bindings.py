import os
import json
import logging
import notmuch2

def _get_db(mode=notmuch2.Database.MODE.READ_ONLY):
    return notmuch2.Database(mode=mode)

def notmuch_show(query_str, sort, flag_error):
    try:
        # We must manually build the list-of-lists-of-pairs structure 
        # to remain a drop-in for your JSON-based flattener.
        with _get_db() as db:
            sort_map = {
                "newest-first": notmuch2.Database.SORT.NEWEST_FIRST,
                "oldest-first": notmuch2.Database.SORT.OLDEST_FIRST,
            }
            query = db.create_query(query_str)
            query.sort = sort_map.get(sort, notmuch2.Database.SORT.NEWEST_FIRST)
            
            def build_tree(msg):
                # Returns the [msg_dict, [replies]] pair expected by your flattener
                msg_dict = {
                    "id": msg.messageid,
                    "match": msg.matched,
                    "tags": list(msg.tags),
                    "subject": msg.header("subject")
                }
                replies = [build_tree(r) for r in msg.replies()]
                return [msg_dict, replies]

            return [[build_tree(m) for m in thread.toplevel()] for thread in query.threads()]

    except Exception as e:
        flag_error("Notmuch Query Failed", f"An error occurred while running notmuch:\n\n{e}")
        os.exit(1)

def flatten_message_tree(list_of_threads):
    # Completely preserved from your original code
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
    list_of_messages = flatten_message_tree(notmuch_show(query, "newest-first", flag_error))
    return [msg for msg in list_of_messages if msg["match"]]

def notmuch_search(query_str, output, sort, flag_error):
    try:
        with _get_db() as db:
            sort_map = {
                "newest-first": notmuch2.Database.SORT.NEWEST_FIRST,
                "oldest-first": notmuch2.Database.SORT.OLDEST_FIRST,
            }
            query = db.create_query(query_str)
            query.sort = sort_map.get(sort, notmuch2.Database.SORT.NEWEST_FIRST)

            if output == "summary":
                return [{
                    "thread": thread.threadid,
                    "subject": thread.subject,
                    "matched": thread.matched,
                    "total": thread.total,
                    "authors": thread.authors,
                    "tags": list(thread.tags)
                } for thread in query.threads()]
            
            if output == "tags":
                return sorted(list(db.tags))
            
            return []

    except Exception as e:
        flag_error("Notmuch Query Failed", f"An error occurred while running notmuch:\n\n{e}")
        os.exit(1)

def find_matching_threads(query, flag_error):
    return notmuch_search(query, "summary", "newest-first", flag_error)

def apply_tag_to_query(pm_tag, query_str, flag_error):
    try:
        with _get_db(mode=notmuch2.Database.MODE.READ_WRITE) as db:
            query = db.create_query(query_str)
            tag = pm_tag[1:]
            adding = pm_tag.startswith('+')
            print(f"applying tag = {pm_tag} to query = {query_str}")
            for msg in query.messages():
                if adding:
                    msg.tags.add(tag)
                else:
                    msg.tags.discard(tag)
    except Exception as e:
        flag_error("Something happened.", f"Caught Exception: {e}")
        os.exit(1)

def get_tags_from_query(query_str, flag_error):
    # Your original added 'and (tag:spam or not tag:spam)' to ensure tag matching
    # notmuch2 handles this via the message iterator
    try:
        with _get_db() as db:
            query = db.create_query(f'{query_str} and (tag:spam or not tag:spam)')
            tags = set()
            for msg in query.messages():
                for tag in msg.tags:
                    tags.add(tag)
            return sorted(list(tags))
    except Exception as e:
        flag_error("Notmuch Command Failed", f"An error occurred while running notmuch:\n\n{e}")
        return []

def update_unseen_from_query(query, flag_error):
    tags = get_tags_from_query(query, flag_error)
    if '$unseen' in tags:
        logging.info("Found '$unseen' tag. Silently replacing with '$unused'.")
        apply_tag_to_query('+$unused', query, flag_error)
        apply_tag_to_query('-$unseen', query, flag_error)
