"""
Unit tests for config.py - Config class and its methods.

Tests for:
- Config.__init__()
- Config.get_font()
- Config.get_visual_setting()
- Config.get_setting()
- Config.get_keybinding()
- Config.get_identities()
- Config.get_tags()
- Config.get_search()
- Config.get_model()
- Config.get_autocompletions()
- Config.is_me()
"""
import pytest
from pathlib import Path
import tempfile
import sys
import importlib.util

# Load config.py as a module (hyphenated filename)
spec = importlib.util.spec_from_file_location("config", "../scripts/config.py")
config_module = importlib.util.module_from_spec(spec)
sys.modules["config"] = config_module
spec.loader.exec_module(config_module)

from config import Config
from PySide6.QtGui import QFont


class TestConfigInit:
    """Tests for Config.__init__() method."""
    
    def test_create_default_config_when_not_exists(self, tmp_path):
        """Test that default config is created when file doesn't exist."""
        config_file = tmp_path / "config.toml"
        
        config = Config(str(config_file))
        
        # Config file should be created
        assert config_file.exists()
        
        # Should have default structure
        assert config.data is not None
        assert "visual" in config.data
        assert "tags" in config.data
        assert "bindings" in config.data
        assert "email_identities" in config.data
    
    def test_load_existing_config_file(self, tmp_path):
        """Test loading an existing config file."""
        config_file = tmp_path / "config.toml"
        config_content = """
[visual]
interface_font = "monospace"
interface_font_size = 14

[bindings]
quit_action = "Ctrl+Q"
"""
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        
        # Should load existing config
        assert config.data["visual"]["interface_font_size"] == 14
        assert config.data["bindings"]["quit_action"] == "Ctrl+Q"
    
    def test_merge_user_config_with_defaults(self, tmp_path):
        """Test that user config is merged with defaults."""
        config_file = tmp_path / "config.toml"
        config_content = """
[visual]
interface_font = "custom_font"

[email_identities]
identities = [
    {name = "Custom", email = "custom@example.com"}
]
"""
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        
        # User config should override default
        assert config.data["visual"]["interface_font"] == "custom_font"
        
        # Default values should still exist for missing keys
        assert "interface_font_size" in config.data["visual"]
        
        # Entire sections should be merged
        assert len(config.data["email_identities"]["identities"]) == 1


class TestConfigGetFont:
    """Tests for Config.get_font() method."""
    
    def test_get_interface_font(self, temp_config_file):
        """Test getting interface font."""
        config = Config(temp_config_file)
        font = config.get_font("interface")
        
        assert isinstance(font, QFont)
        assert config.data["visual"]["interface_font_size"] == font.pointSize()
    
    def test_get_menu_font(self, temp_config_file):
        """Test getting menu font."""
        config = Config(temp_config_file)
        font = config.get_font("menu")
        
        assert isinstance(font, QFont)
        assert config.data["visual"]["menu_font_size"] == font.pointSize()
    
    def test_get_text_font(self, temp_config_file):
        """Test getting text font."""
        config = Config(temp_config_file)
        font = config.get_font("text")
        
        assert isinstance(font, QFont)
        assert config.data["visual"]["text_font_size"] == font.pointSize()
    
    def test_get_font_uses_correct_font_name(self, temp_config_file, tmp_path):
        """Test that font uses the correct font name from config."""
        custom_font_name = "CustomFont"
        config_content = f"""
[visual]
interface_font = "{custom_font_name}"
interface_font_size = 12
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        font = config.get_font("interface")
        
        assert font.family() == custom_font_name


class TestConfigGetVisualSetting:
    """Tests for Config.get_visual_setting() method."""
    
    def test_get_existing_visual_setting(self, temp_config_file):
        """Test retrieving an existing visual setting."""
        config = Config(temp_config_file)
        
        # Add a custom visual setting
        config.data["visual"]["custom_setting"] = "custom_value"
        
        result = config.get_visual_setting("custom_setting")
        assert result == "custom_value"
    
    def test_get_missing_visual_setting(self, temp_config_file):
        """Test that missing visual setting returns None."""
        config = Config(temp_config_file)
        
        result = config.get_visual_setting("nonexistent_setting")
        assert result is None


class TestConfigGetSetting:
    """Tests for Config.get_setting() method."""
    
    def test_get_nested_setting(self, temp_config_file):
        """Test retrieving nested config value."""
        config = Config(temp_config_file)
        
        result = config.get_setting("visual", "interface_font")
        assert result == "monospace"
    
    def test_get_missing_section(self, temp_config_file):
        """Test that missing section returns default."""
        config = Config(temp_config_file)
        
        result = config.get_setting("nonexistent_section", "key", default="default_value")
        assert result == "default_value"
    
    def test_get_missing_key(self, temp_config_file):
        """Test that missing key returns default."""
        config = Config(temp_config_file)
        
        result = config.get_setting("visual", "nonexistent_key", default="default_value")
        assert result == "default_value"


class TestConfigGetKeybinding:
    """Tests for Config.get_keybinding() method."""
    
    def test_get_existing_keybinding(self, temp_config_file):
        """Test retrieving an existing keybinding."""
        config = Config(temp_config_file)
        
        result = config.get_keybinding("quit_action")
        assert result == "Ctrl+Q"
    
    def test_get_zoom_in_keybinding(self, temp_config_file):
        """Test retrieving zoom_in keybinding."""
        config = Config(temp_config_file)
        
        result = config.get_keybinding("zoom_in")
        assert result == "Ctrl++"
    
    def test_get_missing_keybinding(self, temp_config_file):
        """Test that missing keybinding returns None."""
        config = Config(temp_config_file)
        
        result = config.get_keybinding("nonexistent_action")
        assert result is None


class TestConfigGetIdentities:
    """Tests for Config.get_identities() method."""
    
    def test_get_identities_list(self, temp_config_file):
        """Test retrieving identities list."""
        config = Config(temp_config_file)
        
        identities = config.get_identities()
        
        assert isinstance(identities, list)
        assert len(identities) == 2
        assert identities[0]["name"] == "Test User"
        assert identities[0]["email"] == "test@example.com"
    
    def test_get_identities_empty_list(self, tmp_path):
        """Test when identities list is empty."""
        config_content = """
[email_identities]
identities = []
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        identities = config.get_identities()
        
        assert identities == []


class TestConfigGetTags:
    """Tests for Config.get_tags() method."""
    
    def test_get_tags(self, temp_config_file):
        """Test retrieving tags."""
        config = Config(temp_config_file)
        
        tags = config.get_tags()
        
        assert isinstance(tags, list)
        assert "todo" in tags
        assert "done" in tags
        assert "read" in tags
    
    def test_get_tags_default_empty(self, tmp_path):
        """Test when tags section is missing."""
        config_content = """
[visual]
interface_font = "monospace"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        tags = config.get_tags()
        
        # Should return empty list if not found
        assert tags == []


class TestConfigGetSearch:
    """Tests for Config.get_search() method."""
    
    def test_get_search(self, temp_config_file):
        """Test retrieving search query."""
        config = Config(temp_config_file)
        
        search = config.get_search()
        
        assert search == "tag:inbox and tag:unread"
    
    def test_get_search_default(self, tmp_path):
        """Test default search query."""
        config_content = """
[visual]
interface_font = "monospace"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        search = config.get_search()
        
        # Default search query
        assert "tag:inbox" in search
        assert "tag:unread" in search


class TestConfigGetModel:
    """Tests for Config.get_model() method."""
    
    def test_get_model_path(self, temp_config_file):
        """Test retrieving model path."""
        config = Config(temp_config_file)
        
        model_path = config.get_model()
        
        assert model_path is not None
        assert isinstance(model_path, Path)
        assert model_path.name == "model.joblib"
    
    def test_get_model_expands_path(self, tmp_path):
        """Test that model path is expanded."""
        config_content = f"""
[predicting]
model = "~/model.joblib"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        model_path = config.get_model()
        
        # Path should be expanded (no ~)
        assert not str(model_path).startswith("~")
    
    def test_get_model_none_when_missing(self, tmp_path):
        """Test that None is returned when model is not configured."""
        config_content = """
[visual]
interface_font = "monospace"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        model_path = config.get_model()
        
        assert model_path is None


class TestConfigGetAutocompletions:
    """Tests for Config.get_autocompletions() method."""
    
    def test_get_autocompletions_headers(self, temp_config_file):
        """Test retrieving autocompletion setting for headers."""
        config = Config(temp_config_file)
        
        result = config.get_autocompletions("headers")
        assert result == "from,to,cc"
    
    def test_get_autocompletions_default(self, tmp_path):
        """Test default autocompletion setting."""
        config_content = """
[visual]
interface_font = "monospace"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        result = config.get_autocompletions()
        
        assert result == "headers"


class TestConfigIsMe:
    """Tests for Config.is_me() method."""
    
    def test_is_me_matching_own_email(self, temp_config_file):
        """Test that own email is recognized."""
        config = Config(temp_config_file)
        
        result = config.is_me(["test@example.com"])
        assert result is True
    
    def test_is_me_not_matching_other_email(self, temp_config_file):
        """Test that other email is not recognized."""
        config = Config(temp_config_file)
        
        result = config.is_me(["other@example.com"])
        assert result is False
    
    def test_is_me_multiple_addresses(self, temp_config_file):
        """Test with multiple addresses including own."""
        config = Config(temp_config_file)
        
        result = config.is_me(["other@example.com", "test@example.com"])
        assert result is True
    
    def test_is_me_multiple_addresses_none_match(self, temp_config_file):
        """Test with multiple addresses, none match."""
        config = Config(temp_config_file)
        
        result = config.is_me(["other1@example.com", "other2@example.com"])
        assert result is False
    
    def test_is_me_with_name_format(self, temp_config_file):
        """Test with name+email format."""
        config = Config(temp_config_file)
        
        result = config.is_me(["Test User <test@example.com>"])
        assert result is True
    
    def test_is_me_case_sensitive(self, tmp_path):
        """Test that email matching is case sensitive."""
        config_content = """
[email_identities]
identities = [
    {name = "Test", email = "test@example.com"}
]
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        result = config.is_me(["Test@Example.com"])
        assert result is False  # Actual behavior is case-sensitive
    
    def test_is_me_empty_list(self, temp_config_file):
        """Test with empty address list."""
        config = Config(temp_config_file)
        
        result = config.is_me([])
        assert result is False
    
    def test_is_me_multiple_identities(self, tmp_path):
        """Test with multiple configured identities."""
        config_content = """
[email_identities]
identities = [
    {name = "Test 1", email = "test1@example.com"},
    {name = "Test 2", email = "test2@example.com"}
]
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        config = Config(str(config_file))
        
        # Should match first identity
        assert config.is_me(["test1@example.com"]) is True
        # Should match second identity
        assert config.is_me(["test2@example.com"]) is True
        # Should not match unknown
        assert config.is_me(["test3@example.com"]) is False
