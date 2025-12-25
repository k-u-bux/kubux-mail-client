"""
Unit tests for ai-train.py - Pure function without external dependencies.

Tests for:
- filter(tag)
"""
import pytest
import importlib.util
import sys

# Load ai-train.py (hyphenated filename) as a module
spec = importlib.util.spec_from_file_location("ai_train", "../scripts/ai-train.py")
ai_train = importlib.util.module_from_spec(spec)
sys.modules["ai_train"] = ai_train
spec.loader.exec_module(ai_train)

from ai_train import filter


class TestFilterFunction:
    """Tests for filter() function."""
    
    # Tags starting with $ should return False
    
    def test_filter_dollar_prefix_tag(self):
        """Test that tags starting with $ return False."""
        assert filter("$unseen") is False
        assert filter("$unread") is False
        assert filter("$custom") is False
    
    # Specific excluded tags should return False
    
    def test_filter_inbox_tag(self):
        """Test that 'inbox' tag returns False."""
        assert filter("inbox") is False
    
    def test_filter_attachment_tag(self):
        """Test that 'attachment' tag returns False."""
        assert filter("attachment") is False
    
    def test_filter_unread_tag(self):
        """Test that 'unread' tag returns False."""
        assert filter("unread") is False
    
    def test_filter_todo_tag(self):
        """Test that 'todo' tag returns False."""
        assert filter("todo") is False
    
    def test_filter_open_tag(self):
        """Test that 'open' tag returns False."""
        assert filter("open") is False
    
    def test_filter_done_tag(self):
        """Test that 'done' tag returns False."""
        assert filter("done") is False
    
    def test_filter_read_tag(self):
        """Test that 'read' tag returns False."""
        assert filter("read") is False
    
    def test_filter_mark_for_training_tag(self):
        """Test that 'mark_for_training' tag returns False."""
        assert filter("mark_for_training") is False
    
    # Regular tags should return True
    
    def test_filter_regular_work_tag(self):
        """Test that regular 'work' tag returns True."""
        assert filter("work") is True
    
    def test_filter_regular_personal_tag(self):
        """Test that regular 'personal' tag returns True."""
        assert filter("personal") is True
    
    def test_filter_regular_spam_tag(self):
        """Test that regular 'spam' tag returns True."""
        assert filter("spam") is True
    
    def test_filter_regular_important_tag(self):
        """Test that regular 'important' tag returns True."""
        assert filter("important") is True
    
    def test_filter_custom_tag(self):
        """Test that custom tags return True."""
        assert filter("custom_tag") is True
        assert filter("project_alpha") is True
        assert filter("client_meeting") is True
    
    # Edge cases
    
    def test_filter_empty_tag(self):
        """Test that empty string tag returns True."""
        assert filter("") is True
    
    def test_filter_case_sensitive(self):
        """Test that filtering is case sensitive."""
        # Lowercase 'inbox' is excluded
        assert filter("inbox") is False
        # Uppercase 'INBOX' is included
        assert filter("INBOX") is True
        # Mixed case 'Inbox' is included
        assert filter("Inbox") is True
    
    def test_filter_dollar_with_regular_tag(self):
        """Test that $prefix takes precedence."""
        assert filter("$inbox") is False  # $ prefix, should be False
        # Regular 'inbox' is also False but for different reason
        assert filter("inbox") is False
    
    def test_filter_tag_with_numbers(self):
        """Test tags containing numbers."""
        assert filter("project2024") is True
        assert filter("task_123") is True
    
    def test_filter_tag_with_underscores(self):
        """Test tags with underscores."""
        assert filter("client_project") is True
        assert filter("important_task") is True
    
    def test_filter_tag_with_hyphens(self):
        """Test tags with hyphens."""
        assert filter("high-priority") is True
        assert filter("long-term") is True
    
    def test_filter_multiple_dollar_signs(self):
        """Test tags with multiple dollar signs."""
        # Only first char is checked for $
        assert filter("$$tag") is False
    
    def test_filter_partial_excluded_tag(self):
        """Test that partial matches are not excluded."""
        # 'inbox' is excluded, but 'inbox_backup' is not
        assert filter("inbox_backup") is True
        # 'todo' is excluded, but 'todo_item' is not
        assert filter("todo_item") is True
