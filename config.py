# config.py
import os
import toml
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

# Constants
APP_NAME = "kubux-notmuch-mail-client"
CONFIG_FILE_NAME = "config.toml"
DEFAULT_CONFIG = {
    "paths": {
        "base_dir": "~/.local/share/notmuch-client/",
        "mail_dir": "mail/",
        "notmuch_config_file": "notmuch-config",
        "tag_sync_dir": "sync/",
        "ai_feedback_log": "ai_feedback.jsonl",
        "ai_model": "ai_model.joblib",
    },
    "visual_settings": {
        "font_family": "monospace",
        "ui_font_size": 10,
        "text_font_size": 12,
        "widget_scale": 1.0,
    },
    "keybindings": {
        "mail_list": {
            "quit": "Ctrl+Q",
            "reply": "R",
            "reply_all": "Shift+R",
            "forward": "F",
            "new_email": "N",
            "toggle_read": "M",
            "open_viewer": "Enter",
            "edit_tags": "T",
        },
        "mail_viewer": {
            "quit": "Q",
            "reply": "R",
            "reply_all": "Shift+R",
            "forward": "F",
            "edit_tags": "T",
            "close_viewer": "Escape",
        },
        "tag_editor": {
            "save_tags": "Enter",
            "cancel": "Escape",
        }
    }
}

class AppConfig:
    """
    Manages the application's configuration.
    """
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir:
            self.config_dir = config_dir
        else:
            self.config_dir = Path(os.environ.get('XDG_CONFIG_HOME', '~/.config')).expanduser() / APP_NAME

        self.config_file_path = self.config_dir / CONFIG_FILE_NAME
        self.settings: Dict[str, Any] = {}
        self.paths: Dict[str, Path] = {}
        self.load_config()

    def load_config(self):
        """Loads configuration from the TOML file, creating a default if none exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.config_file_path.exists():
            self._write_default_config()

        with open(self.config_file_path, 'r') as f:
            self.settings = toml.load(f)

        # Resolve and store all paths
        self._resolve_paths()

    def _write_default_config(self):
        """Writes the default configuration to the file."""
        with open(self.config_file_path, 'w') as f:
            toml.dump(DEFAULT_CONFIG, f)

    def _resolve_paths(self):
        """Resolves all path strings to absolute Path objects."""
        base_dir = Path(self.settings["paths"]["base_dir"]).expanduser()
        self.paths["base_dir"] = base_dir
        self.paths["mail_dir"] = base_dir / self.settings["paths"]["mail_dir"]
        self.paths["notmuch_config_file"] = self.config_dir / self.settings["paths"]["notmuch_config_file"]
        self.paths["tag_sync_dir"] = base_dir / self.settings["paths"]["tag_sync_dir"]
        self.paths["ai_feedback_log"] = base_dir / self.settings["paths"]["ai_feedback_log"]
        self.paths["ai_model"] = base_dir / self.settings["paths"]["ai_model"]

        # Ensure the directories exist
        for key in ["base_dir", "mail_dir", "tag_sync_dir"]:
            self.paths[key].mkdir(parents=True, exist_ok=True)

    def get(self, section: str, key: str, default=None):
        """Safely get a value from the configuration."""
        return self.settings.get(section, {}).get(key, default)

    def get_path(self, key: str):
        """Get a resolved Path object from the configuration."""
        return self.paths.get(key)

    def edit_config(self):
        """Opens the config file in the user's preferred editor."""
        editor = os.environ.get('EDITOR')
        if not editor:
            print("EDITOR environment variable is not set. Please set it to your preferred editor.")
            return

        subprocess.run([editor, str(self.config_file_path)])

# Global instance for easy access
config = AppConfig()
