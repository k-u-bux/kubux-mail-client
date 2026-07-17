import toml
from pathlib import Path
import os
from PySide6.QtGui import QFont
from typing import Dict, Any, Optional
from email.utils import getaddresses
import subprocess
import fcntl
from watcher import DirectoryEventHandler
import logging
import json

def get_dpi():
    helper_path = os.path.join(os.path.dirname(__file__), "config-helper-get-dpi")
    phys_dpi = float( subprocess.check_output([ helper_path ]).decode("utf-8").strip() )
    return phys_dpi

def get_pixel_ratio():
    helper_path = os.path.join(os.path.dirname(__file__), "config-helper-get-pixel-ratio")
    pixel_ratio = float( subprocess.check_output([ helper_path ]).decode("utf-8").strip() )
    return pixel_ratio

class Config:
    def __init__(self, config_file: str = "~/.config/kubux-mail-client/config.toml"):
        self.config_path = Path(config_file).expanduser()
        self.config_dir = self.config_path.parent
        self.data = self.load_config()

        # Visual settings
        self.interface_font = self.get_font('interface')
        self.menu_font = self.get_font('menu')
        self.text_font = self.get_font('text')

        self.dir_watcher = DirectoryEventHandler( self.reload_config )
        self.dir_watcher.watch( self.config_dir )
        
    def reload_config(self):
        self.data = self.load_config()

    def load_config(self):
        # Default configuration
        default_config = {
            "visual": {
                "interface_font": "monospace",
                "interface_font_size": 12,
                "menu_font": "monospace",
                "menu_font_size": 12,
                "text_font": "monospace",
                "text_font_size": 12,
                "popup_font": "monospace",
                "popup_font_size": 12,
                "attachment_font": "monospace",
                "attachment_font_size": 12
            },
            "searches": {
                "search": "tag:inbox and tag:unread",
                "max_named_searches": 20,
                "tags": [
                    "private", "professional"
                ],
                "status_tags": [
                    "todo", "done", "read"
                ],
                "suppressed": [
                    "open", "info", "postponed"
                ]
             },
            "bindings": {
                "quit_action": "Ctrl+Q",
                "zoom_in": "Ctrl++",
                "zoom_out": "Ctrl+-",
                "move_character_left": "Left",
                "move_character_right": "Right",
                "move_word_left": "Ctrl+Left",
                "move_word_right": "Ctrl+Right",
                "move_line_up": "Up",
                "move_line_down": "Down",
                "move_to_line_start": "Home",
                "move_to_line_end": "End",
                "move_to_document_start": "Ctrl+Home",
                "move_to_document_end": "Ctrl+End",
                "move_page_up": "PageUp",
                "move_page_down": "PageDown",
                "undo": "Ctrl+Z",
                "redo": "Ctrl+Y",
                "cut": "Ctrl+X",
                "copy": "Ctrl+C",
                "paste": "Ctrl+V",
                "select_all": "Ctrl+A",
                "delete_character_left": "Backspace",
                "delete_character_right": "Delete",
                "delete_word_left": "Ctrl+Backspace",
                "delete_word_right": "Ctrl+Delete",
                "delete_to_end_of_line": "Ctrl+K"
            },
            "email_identities": {
                "identities": [
                    {
                        "name": "Default User", 
                        "email": "user@example.com",
                        "drafts": "~/.local/share/kubux-mail-client/mail/drafts",
                        "template": "~/.config/kubux-mail-client/draft_template.eml"
                    },
                ]
            },
            "autocomplete": {
                "headers": []
            }
        }

        if not self.config_path.exists():
            # Create a default config file if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                toml.dump(default_config, f)
            print(f"Created default config file at {self.config_path}")
            return default_config
        else:
            with open(self.config_path, "r") as f:
                user_config = toml.load(f)
                
                # Merge user config with defaults
                merged_config = default_config.copy()
                for key, value in user_config.items():
                    if isinstance(value, dict) and key in merged_config and isinstance(merged_config[key], dict):
                        merged_config[key].update(value)
                    else:
                        merged_config[key] = value
                
                return merged_config

    def get_font_logical_size(self, font_type: str):
        font = QFont(self.data["visual"][f"{font_type}_font"])
        font.setPointSize(self.data["visual"][f"{font_type}_font_size"])
        return font

    def get_font_physical_size(self, font_type: str):
        pt_size = self.data["visual"][f"{font_type}_font_size"]
        pixel_size = pt_size * get_pixel_ratio()
        font = QFont(self.data["visual"][f"{font_type}_font"])
        font.setPointSize(pixel_size)
        return font 

    def get_font(self, font_type: str):
        return self.get_font_logical_size(font_type)

    def get_interface_font(self):
        return self.get_font("interface")

    def get_menu_font(self):
        return self.get_font("menu")

    def get_text_font(self):
        return self.get_font("text")

    def get_popup_font(self):
        return self.get_font("popup")

    def get_attachment_font(self):
        return self.get_font("attachment")

    def get_visual_setting(self, key):
        return self.data["visual"].get(key)
        
    def get_setting(self, section: str, key: str, default=None):
        return self.data.get(section, {}).get(key, default)
        
    def get_keybinding(self, action_name: str) -> Optional[str]:
        return self.data.get("bindings", {}).get(action_name)

    def get_identities(self):
        return self.data.get("email_identities", {}).get("identities", [])

    def get_max_named_searches(self):
        return self.data.get("searches", {}).get("max_named_searches", 20)

    def get_tags(self):
        return self.data.get("searches", {}).get("tags", [])

    def get_status_tags(self):
        return self.data.get("searches", {}).get("status_tags", [])

    def get_suppressed_tags(self):
        return self.data.get("searches", {}).get("suppressed", [])

    def get_search(self):
        search = most_recent_search( self.get_history_path() )
        if search:
            return search
        return self.data.get("searches", {}).get("search", "tag:inbox and tag:unread" )

    def get_model(self):
        path = self.data.get("predicting", {}).get("model", None)
        if path:
            path = Path( path ).expanduser()
        return path

    def get_max_search_history(self):
        return self.data.get("searches", {}).get("max_search_history", 20)

    def get_history_path(self):
        return self.config_dir / "query_history.json"

    def get_autocompletions(self, category="headers"):
        return self.data.get("autocomplete", {}).get(category, [])

    def is_me(self, address_string_list) -> bool:
        from_addresses = getaddresses(address_string_list)
        from_addrs_only = {addr.casefold() for name, addr in from_addresses}
        my_addresses = getaddresses([me["email"] for me in self.get_identities()])
        my_addrs_only = {addr.casefold() for name, addr in my_addresses}
        # print(f"DEBUG:{from_addrs_only} vs {my_addrs_only}")
        return not from_addrs_only.isdisjoint(my_addrs_only)

# A global config object for easy access
config = Config()


def load_history ( path ):
    """Load query history from JSON file under a shared lock."""
    path = Path(path)
    lockpath = path.with_suffix(".json.lock")
    try:
        lfd = os.open(str(lockpath), os.O_RDWR | os.O_CREAT)
    except Exception:
        return _load_history_unlocked(path)
    try:
        fcntl.flock(lfd, fcntl.LOCK_SH)
    except Exception:
        os.close(lfd)
        return _load_history_unlocked(path)

    try:
        result = _load_history_unlocked(path)
        logging.info(f"[dbg pid={os.getpid()}] load_history: {len(result)} entries")
        return result
    finally:
        os.close(lfd)


def _load_history_unlocked(path):
    """Read and parse the history file without locking."""
    if not path.exists():
        return []
    try:
        with open(str(path), "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        logging.error(f"[dbg pid={os.getpid()}] load_history FAILED: {e}")
        return []

def most_recent_search ( path ):
    history = load_history( path )
    if history:
        if len( history ) > 0:
            return history[ 0 ]
    return None

def save_history ( path, history ):
    """Save query history to JSON file."""
    try:
        path.parent.mkdir( parents=True, exist_ok=True )
        with open(path, "w") as f:
            json.dump(history, f)
    except Exception as e:
        logging.error(f"Failed to save query history: {e}")

def add_to_history(history, query):
    """Add a query to history, deduplicating and capping at max_size entries."""
    max_size = config.get_max_search_history()
    if not query or not query.strip():
        return history
    if query in history:
        history.remove(query)
    history.insert(0, query)
    return history[:max_size]

def _with_exclusive_lock(path, callback):
    """Acquire an exclusive lock on *path*, then call callback(history_list).
    
    The callback receives the current history list and must return the
    (possibly modified) list, which is written back atomically under the
    same lock.  This serialises access across *processes* (not just
    threads), preventing the TOCTOU race that destroyed the history when
    two instances of show-query-results ran concurrently.
    
    The write is done to a temp file which is then atomically renamed
    over the target, so readers that don't hold the lock never see a
    truncated or partially-written file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Lock a separate lock file so we never lock the data file itself
    # (which would interfere with atomic-rename readers).
    lockpath = path.with_suffix(".json.lock")
    lfd = os.open(str(lockpath), os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(lfd, fcntl.LOCK_EX)
    except Exception:
        os.close(lfd)
        raise

    try:
        # Read current state
        try:
            with open(str(path), "r") as f:
                history = json.load(f)
                before = list(history)
        except (FileNotFoundError, json.JSONDecodeError, EOFError):
            history = []
            before = []

        history = callback(history)

        # Write to a temp file next to the target, then atomically rename
        tmp = path.with_suffix(".json.tmp")
        with open(str(tmp), "w") as f:
            json.dump(history, f)
            f.flush()
            os.fsync(f.fileno())
        os.rename(str(tmp), str(path))

        logging.info(
            f"[dbg pid={os.getpid()}] _with_exclusive_lock: "
            f"before={len(before)} after={len(history)} "
            f"first_before={before[0] if before else 'None'} "
            f"first_after={history[0] if history else 'None'}"
        )
    finally:
        os.close(lfd)


def record_query_to_history(path, query):
    """Read current history from disk, add query, write back.

    This performs a full read-update-write cycle under an exclusive file
    lock so that multiple concurrently open windows don't clobber each
    other's history with a stale in-memory copy.
    """
    logging.info(f"[dbg pid={os.getpid()}] record_query_to_history: query='{query}'")
    _with_exclusive_lock(path, lambda history: add_to_history(history, query))


def remove_query_from_history(path, query):
    """Remove *query* from the history file under an exclusive lock."""
    logging.info(f"[dbg pid={os.getpid()}] remove_query_from_history: query='{query}'")
    def _remove(history):
        if query in history:
            history.remove(query)
        return history
    _with_exclusive_lock(path, _remove)

# end of file
