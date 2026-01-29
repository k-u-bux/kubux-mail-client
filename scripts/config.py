import toml
from pathlib import Path
import os
from PySide6.QtGui import QFont
from typing import Dict, Any, Optional
from email.utils import getaddresses
import subprocess

phys_dpi = float( subprocess.check_output(["python", "config-helper-get-dpi.py"]).decode("utf-8").strip() )

class Config:
    def __init__(self, config_file: str = "~/.config/kubux-mail-client/config.toml"):
        self.config_path = Path(config_file).expanduser()
        self.config_dir = self.config_path.parent
        self.data = self.load_config()

        # Visual settings
        self.interface_font = self.get_font('interface')
        self.menu_font = self.get_font('menu')
        self.text_font = self.get_font('text')
        
    def load_config(self):
        # Default configuration
        default_config = {
            "visual": {
                "interface_font": "monospace",
                "interface_font_size": 12,
                "menu_font": "monospace",
                "menu_font_size": 12,
                "text_font": "monospace",
                "text_font_size": 12
            },
            "searches": {
                "search": "tag:inbox and tag:unread",
                "tags": [
                    "todo", "done", "read"
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
        pixel_size = int( ( pt_size / 72 ) * phys_dpi )
        font = QFont(self.data["visual"][f"{font_type}_font"])
        font.setPixelSize(pixel_size)
        return font 

    def get_font(self, font_type: str):
        return self.get_font_physical_size(font_type)

    def get_interface_font(self):
        return self.get_font("interface")

    def get_menu_font(self):
        return self.get_font("menu")

    def get_text_font(self):
        return self.get_font("text")

    def get_visual_setting(self, key):
        return self.data["visual"].get(key)
        
    def get_setting(self, section: str, key: str, default=None):
        return self.data.get(section, {}).get(key, default)
        
    def get_keybinding(self, action_name: str) -> Optional[str]:
        return self.data.get("bindings", {}).get(action_name)

    def get_identities(self):
        return self.data.get("email_identities", {}).get("identities", [])

    def get_tags(self):
        return self.data.get("searches", {}).get("tags", [])

    def get_search(self):
        return self.data.get("searches", {}).get("search", "tag:inbox and tag:unread" )

    def get_model(self):
        path = self.data.get("predicting", {}).get("model", None)
        if path:
            path = Path( path ).expanduser()
        return path

    def get_autocompletions(self, category="headers"):
        return self.data.get("autocomplete", {}).get(category, "headers")

    def is_me(self, address_string_list) -> bool:
        from_addresses = getaddresses(address_string_list)
        from_addrs_only = {addr.casefold() for name, addr in from_addresses}
        my_addresses = getaddresses([me["email"] for me in self.get_identities()])
        my_addrs_only = {addr.casefold() for name, addr in my_addresses}
        # print(f"DEBUG:{from_addrs_only} vs {my_addrs_only}")
        return not from_addrs_only.isdisjoint(my_addrs_only)

# A global config object for easy access
config = Config()
