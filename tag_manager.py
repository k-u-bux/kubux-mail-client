# tag_manager.py
import notmuch
import json
import time
import os
from pathlib import Path
from typing import List, Dict, Any, Union
from .config import config

class TagManager:
    """
    Manages tag operations, logging them for multi-device synchronization.
    This component ensures all tag changes are recorded before being applied.
    """
    def __init__(self, device_id: Optional[str] = None):
        # A unique ID for this device, generated on first run.
        self.device_id = device_id if device_id else self._get_device_id()
        self.sync_dir = config.get_path("tag_sync_dir")
        self.log_file = self.sync_dir / f"tag_ops_{self.device_id}.jsonl"

    def _get_device_id(self) -> str:
        # For a real implementation, this would be a persistent, unique ID.
        # A simple placeholder for now.
        return os.uname().nodename

    def _log_operation(self, operation: str, message_id: str, tags: List[str]):
        """Logs a tag operation to the append-only log file."""
        log_entry = {
            "timestamp": time.time(),
            "device_id": self.device_id,
            "message_id": message_id,
            "operation": operation,
            "tags": tags
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def _get_database(self) -> notmuch.Database:
        """Opens the isolated Notmuch database."""
        return notmuch.Database(
            config=str(config.get_path("notmuch_config_file")),
            mode=notmuch.Database.MODE.READ_WRITE
        )

    def add_tags(self, message_id: str, tags: List[str]):
        """Adds tags to a message, logging the operation first."""
        self._log_operation("add_tags", message_id, tags)
        with self._get_database() as db:
            message = db.find_message(message_id)
            if message:
                message.add_tags(tags)
            else:
                print(f"Warning: Message with ID {message_id} not found.")

    def remove_tags(self, message_id: str, tags: List[str]):
        """Removes tags from a message, logging the operation first."""
        self._log_operation("remove_tags", message_id, tags)
        with self._get_database() as db:
            message = db.find_message(message_id)
            if message:
                message.remove_tags(tags)
            else:
                print(f"Warning: Message with ID {message_id} not found.")

    def set_tags(self, message_id: str, tags_to_add: List[str], tags_to_remove: List[str]):
        """
        Sets tags by adding and removing. Logs both operations atomically.
        This is used for the AI feedback loop.
        """
        self._log_operation("set_tags_add", message_id, tags_to_add)
        self._log_operation("set_tags_remove", message_id, tags_to_remove)
        with self._get_database() as db:
            message = db.find_message(message_id)
            if message:
                message.add_tags(tags_to_add)
                message.remove_tags(tags_to_remove)
            else:
                print(f"Warning: Message with ID {message_id} not found.")
