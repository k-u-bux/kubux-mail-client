import notmuch2
import os
import logging
from datetime import datetime, timezone


def _get_exclude_tags(db):
    """
    Get the list of tags to exclude from queries based on notmuch config.
    Returns a list of tag names to exclude.
    """
    try:
        # Get the exclude_tags config value (semicolon-separated)
        exclude_tags_str = db.config.get('search.exclude_tags', '')
        if exclude_tags_str:
            # Split by semicolon and filter out empty strings
            tags = [tag.strip() for tag in exclude_tags_str.split(';') if tag.strip()]
            return tags
        return None
    except Exception:
        # If we can't read config, don't exclude anything
        return None


def notmuch_show(query, sort, flag_error):
    """
    Query notmuch and return results in the nested structure expected by flatten_message_tree.
    Returns: list of threads, where each thread is a list of [message_dict, replies] pairs.
    """
    try:
        with notmuch2.Database() as db:
            # Map sort parameter to notmuch2 constant
            sort_map = {
                "newest-first": notmuch2.Database.SORT.NEWEST_FIRST,
                "oldest-first": notmuch2.Database.SORT.OLDEST_FIRST,
            }
            sort_value = sort_map.get(sort, notmuch2.Database.SORT.NEWEST_FIRST)
            
            # Get tags to exclude from config
            exclude_tags = _get_exclude_tags(db)
            
            # First, get set of message IDs that actually matched the query
            matched_ids = {str(msg.messageid) for msg in db.messages(query, exclude_tags=exclude_tags)}
            
            # Now get threads with proper sorting and exclusions
            threads = db.threads(query, sort=sort_value, exclude_tags=exclude_tags)
            
            result = []
            for thread in threads:
                thread_data = []
                for msg in thread.toplevel():
                    thread_data.append(_build_message_tree(msg, matched_ids))
                result.append(thread_data)
            
            return result

    except Exception as e:
        _call_error_callback(flag_error, "Notmuch Query Failed",
                            f"An error occurred while running notmuch:\n\n{e}")
        os._exit(1)


def _build_message_tree(msg, matched_ids):
    """
    Recursively build the [message_dict, replies] structure for a message.
    """
    # Convert BinString to str for consistency
    msgid = str(msg.messageid)
    
    # Build message dictionary with all relevant fields
    msg_dict = {
        "id": msgid,
        "match": msgid in matched_ids,
        "tags": [str(tag) for tag in msg.tags],
        "timestamp": msg.date,
        "date_relative": _format_relative_date(datetime.fromtimestamp(msg.date, tz=timezone.utc)),
        "filename": [str(msg.path)],  # Wrapped in list to match original behavior
        "headers": {
            "Subject": _safe_header(msg, "Subject"),
            "From": _safe_header(msg, "From"),
            "To": _safe_header(msg, "To"),
            "Cc": _safe_header(msg, "Cc"),
            "Date": _safe_header(msg, "Date"),
            "Message-Id": _safe_header(msg, "Message-Id"),
        }
    }
    
    # Recursively process replies
    replies = [_build_message_tree(reply, matched_ids) for reply in msg.replies()]
    
    return [msg_dict, replies]


def _safe_header(msg, header_name):
    """Safely get a header value, returning empty string if not found."""
    try:
        return msg.header(header_name)
    except (LookupError, Exception):
        return ""


def _format_relative_date(date):
    """Format date in relative terms (e.g., '2 days ago')."""
    now = datetime.now(timezone.utc)
    delta = now - date
    
    seconds = delta.total_seconds()
    if seconds < 60:
        return "now"
    elif seconds < 3600:
        mins = int(seconds / 60)
        return f"{mins} min{'s' if mins != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    elif seconds < 2592000:
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"
    elif seconds < 31536000:
        months = int(seconds / 2592000)
        return f"{months} month{'s' if months != 1 else ''} ago"
    else:
        years = int(seconds / 31536000)
        return f"{years} year{'s' if years != 1 else ''} ago"


def flatten_message_tree(list_of_threads):
    """
    Flatten nested thread structure into a linear list of messages with depth information.
    This function is preserved from the original implementation.
    """
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
    """
    Find all messages matching the query.
    Returns only messages where match=True.
    """
    list_of_messages = flatten_message_tree(notmuch_show(query, "newest-first", flag_error))
    result = []
    for msg in list_of_messages:
        if msg["match"]:
            result.append(msg)
    return result


def notmuch_search(query, output, sort, flag_error):
    """
    Search notmuch database with specified output format.
    """
    try:
        with notmuch2.Database() as db:
            # Map sort parameter to notmuch2 constant
            sort_map = {
                "newest-first": notmuch2.Database.SORT.NEWEST_FIRST,
                "oldest-first": notmuch2.Database.SORT.OLDEST_FIRST,
            }
            sort_value = sort_map.get(sort, notmuch2.Database.SORT.NEWEST_FIRST)
            
            # Get tags to exclude from config
            exclude_tags = _get_exclude_tags(db)
            
            if output == "summary":
                threads = db.threads(query, sort=sort_value, exclude_tags=exclude_tags)
                
                result = []
                for thread in threads:
                    thread_dict = {
                        "thread": str(thread.threadid),
                        "timestamp": int(thread.first),  # oldest date
                        "date_relative": _format_relative_date(
                            datetime.fromtimestamp(thread.first, tz=timezone.utc)
                        ),
                        "matched": thread.matched,
                        "total": len(thread),
                        "authors": str(thread.authors),
                        "subject": str(thread.subject),
                        "tags": [str(tag) for tag in thread.tags]
                    }
                    result.append(thread_dict)
                
                return result
            
            elif output == "tags":
                # Get all tags from the database
                return sorted([str(tag) for tag in db.tags])
            
            else:
                # Unsupported output format
                return []

    except Exception as e:
        _call_error_callback(flag_error, "Notmuch Query Failed",
                            f"An error occurred while running notmuch:\n\n{e}")
        os._exit(1)


def find_matching_threads(query, flag_error):
    """
    Find all threads matching the query.
    """
    list_of_threads = notmuch_search(query, "summary", "newest-first", flag_error)
    return list_of_threads


def apply_tag_to_query(pm_tag, query, flag_error):
    """
    Apply tag operation (add or remove) to all messages matching query.
    pm_tag format: '+tag' to add, '-tag' to remove
    """
    try:
        with notmuch2.Database(mode=notmuch2.Database.MODE.READ_WRITE) as db:
            # Parse the tag operation
            if not pm_tag or len(pm_tag) < 2:
                raise ValueError(f"Invalid tag format: {pm_tag}")
            
            operation = pm_tag[0]
            tag_name = pm_tag[1:]
            
            print(f"applying tag = {pm_tag} to query = {query}")
            
            messages = db.messages(query)
            for msg in messages:
                if operation == '+':
                    msg.tags.add(tag_name)
                elif operation == '-':
                    msg.tags.discard(tag_name)
                else:
                    raise ValueError(f"Invalid tag operation: {operation}")

    except Exception as e:
        _call_error_callback(flag_error, "Notmuch Query Failed",
                            f"An error occurred while running notmuch:\n\n{e}")
        os._exit(1)


def get_tags_from_query(query, flag_error):
    """
    Get all unique tags from messages matching the query.
    """
    try:
        with notmuch2.Database() as db:
            # Append the same filter as the original to ensure we're querying properly
            query_str = f'{query} and (tag:spam or not tag:spam)'
            messages = db.messages(query_str)
            
            tags_set = set()
            for msg in messages:
                for tag in msg.tags:
                    tags_set.add(str(tag))
            
            tags = sorted(list(tags_set))
            return tags
            
    except Exception as e:
        _call_error_callback(flag_error, "Notmuch Command Failed",
                            f"An error occurred while running notmuch:\n\n{e}")
        return []


def update_unseen_from_query(query, flag_error):
    """
    Replace '$unseen' tag with '$unused' for messages matching the query.
    """
    tags = get_tags_from_query(query, flag_error)
    if '$unseen' in tags:
        logging.info("Found '$unseen' tag. Silently replacing with '$unused'.")
        apply_tag_to_query('+$unused', query, flag_error)
        apply_tag_to_query('-$unseen', query, flag_error)


def _call_error_callback(flag_error, title, message):
    """
    Call the error callback with flexible signature handling.
    Supports both 2-arg and 3-arg (parent, title, message) signatures.
    """
    import inspect
    sig = inspect.signature(flag_error)
    if len(sig.parameters) == 3:
        # 3-arg version like display_error(parent, title, message)
        flag_error(None, title, message)
    else:
        # 2-arg version
        flag_error(title, message)
