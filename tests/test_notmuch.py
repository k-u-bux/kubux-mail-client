"""
Integration tests for notmuch.py - Notmuch wrapper functions.

Tests for:
- notmuch_show()
- flatten_message_tree()
- find_matching_messages()
- notmuch_search()
- find_matching_threads()
- apply_tag_to_query()
- get_tags_from_query()
- update_unseen_from_query()

All tests use mocking for subprocess calls.
"""
import pytest
from unittest.mock import MagicMock, Mock, patch
import json
import sys
from pathlib import Path
import importlib.util

# Load notmuch.py as a module (no hyphen)
spec = importlib.util.spec_from_file_location("notmuch", "../scripts/notmuch.py")
notmuch = importlib.util.module_from_spec(spec)
sys.modules["notmuch"] = notmuch
spec.loader.exec_module(notmuch)

from notmuch import (
    notmuch_show,
    flatten_message_tree,
    find_matching_messages,
    notmuch_search,
    find_matching_threads,
    apply_tag_to_query,
    get_tags_from_query,
    update_unseen_from_query
)


class TestNotmuchShow:
    """Tests for notmuch_show() function."""
    
    @patch('subprocess.run')
    def test_notmuch_show_success(self, mock_run, flag_error_mock):
        """Test successful notmuch show execution."""
        mock_result = MagicMock()
        mock_result.stdout = '{"threads": []}'
        mock_run.return_value = mock_result
        
        result = notmuch_show("tag:inbox", "newest-first", flag_error_mock)
        
        assert result == {"threads": []}
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0][0] == 'notmuch'
        assert call_args[0][0][1] == 'show'
        assert '--format=json' in call_args[0][0]
        assert '--body=false' in call_args[0][0]
        assert '--sort=newest-first' in call_args[0][0]
        assert 'tag:inbox' in call_args[0][0]
    
    @patch('subprocess.run')
    def test_notmuch_show_json_parsing(self, mock_run, flag_error_mock):
        """Test JSON parsing of notmuch output."""
        test_data = {
            "threads": [
                [{"id": "msg1", "match": True}],
                [{"id": "msg2", "match": False}]
            ]
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(test_data)
        mock_run.return_value = mock_result
        
        result = notmuch_show("tag:inbox", "newest-first", flag_error_mock)
        
        assert result == test_data
    
    @patch('subprocess.run')
    def test_notmuch_show_error(self, mock_run, flag_error_mock):
        """Test error handling with CalledProcessError."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, 'notmuch', stderr='Error')
        
        notmuch_show("tag:inbox", "newest-first", flag_error_mock)
        
        flag_error_mock.assert_called_once()
        call_args = flag_error_mock.call_args[0]
        assert "Notmuch Query Failed" in call_args[0]
    
    @patch('subprocess.run')
    def test_notmuch_show_json_decode_error(self, mock_run, flag_error_mock):
        """Test JSON decode error handling."""
        mock_result = MagicMock()
        mock_result.stdout = "invalid json"
        mock_run.return_value = mock_result
        
        notmuch_show("tag:inbox", "newest-first", flag_error_mock)
        
        flag_error_mock.assert_called_once()
        call_args = flag_error_mock.call_args[0]
        assert "JSON" in call_args[0]


class TestFlattenMessageTree:
    """Tests for flatten_message_tree() function."""
    
    def test_flatten_empty_list(self):
        """Test flattening empty thread list."""
        result = flatten_message_tree([])
        assert result == []
    
    def test_flatten_single_message(self):
        """Test flattening single message."""
        threads = [
            [[{"id": "msg1"}]]
        ]
        result = flatten_message_tree(threads)
        assert len(result) == 1
        assert result[0]["id"] == "msg1"
        assert result[0]["depth"] == 0
    
    def test_flatten_thread_with_replies(self):
        """Test flattening thread with replies."""
        threads = [
            [
                [{"id": "msg1"}, [
                    [{"id": "msg2"}, []],
                    [{"id": "msg3"}, []]
                ]]
            ]
        ]
        result = flatten_message_tree(threads)
        assert len(result) == 3
        assert result[0]["id"] == "msg1"
        assert result[0]["depth"] == 0
        assert result[1]["id"] == "msg2"
        assert result[1]["depth"] == 1
        assert result[2]["id"] == "msg3"
        assert result[2]["depth"] == 1
    
    def test_flatten_deep_nesting(self):
        """Test flattening deeply nested threads."""
        threads = [
            [
                [{"id": "msg1"}, [
                    [{"id": "msg2"}, [
                        [{"id": "msg3"}, [
                            [{"id": "msg4"}, []]
                        ]]
                    ]]
                ]]
            ]
        ]
        result = flatten_message_tree(threads)
        assert len(result) == 4
        assert result[0]["depth"] == 0
        assert result[1]["depth"] == 1
        assert result[2]["depth"] == 2
        assert result[3]["depth"] == 3
    
    def test_flatten_preserves_order(self):
        """Test that message order is preserved."""
        threads = [
            [
                [{"id": "msg1"}, [
                    [{"id": "msg2"}, []],
                    [{"id": "msg3"}, []]
                ]]
            ]
        ]
        result = flatten_message_tree(threads)
        ids = [msg["id"] for msg in result]
        assert ids == ["msg1", "msg2", "msg3"]


class TestFindMatchingMessages:
    """Tests for find_matching_messages() function."""
    
    @patch('notmuch.flatten_message_tree')
    @patch('notmuch.notmuch_show')
    def test_find_matching_messages_filters_match_true(self, mock_show, mock_flatten, flag_error_mock):
        """Test that only messages with match=True are returned."""
        mock_show.return_value = [
            [
                [{"id": "msg1", "match": True}],
                [{"id": "msg2", "match": False}],
                [{"id": "msg3", "match": True}]
            ]
        ]
        mock_flatten.side_effect = lambda x: x
        
        result = find_matching_messages("tag:inbox", flag_error_mock)
        
        assert len(result) == 2
        assert result[0]["id"] == "msg1"
        assert result[1]["id"] == "msg3"
    
    @patch('notmuch.flatten_message_tree')
    @patch('notmuch.notmuch_show')
    def test_find_matching_messages_empty_result(self, mock_show, mock_flatten, flag_error_mock):
        """Test with no matching messages."""
        mock_show.return_value = []
        mock_flatten.return_value = []
        
        result = find_matching_messages("tag:inbox", flag_error_mock)
        
        assert result == []
    
    @patch('notmuch.flatten_message_tree')
    @patch('notmuch.notmuch_show')
    def test_find_matching_messages_calls_flatten(self, mock_show, mock_flatten, flag_error_mock):
        """Test that flatten_message_tree is called."""
        mock_show.return_value = [[{"id": "msg1", "match": True}]]
        mock_flatten.return_value = [{"id": "msg1", "match": True}]
        
        find_matching_messages("tag:inbox", flag_error_mock)
        
        mock_flatten.assert_called_once_with(mock_show.return_value)


class TestNotmuchSearch:
    """Tests for notmuch_search() function."""
    
    @patch('subprocess.run')
    def test_notmuch_search_success(self, mock_run, flag_error_mock):
        """Test successful notmuch search execution."""
        mock_result = MagicMock()
        mock_result.stdout = '[{"thread": "thread1"}, {"thread": "thread2"}]'
        mock_run.return_value = mock_result
        
        result = notmuch_search("tag:inbox", "summary", "newest-first", flag_error_mock)
        
        assert len(result) == 2
        assert result[0]["thread"] == "thread1"
        
        call_args = mock_run.call_args
        assert call_args[0][0][0] == 'notmuch'
        assert call_args[0][0][1] == 'search'
        assert '--format=json' in call_args[0][0]
        assert '--output=summary' in call_args[0][0]
        assert '--sort=newest-first' in call_args[0][0]
    
    @patch('subprocess.run')
    def test_notmuch_search_different_outputs(self, mock_run, flag_error_mock):
        """Test with different output formats."""
        mock_result = MagicMock()
        mock_result.stdout = '["tag1", "tag2"]'
        mock_run.return_value = mock_result
        
        result = notmuch_search("tag:inbox", "tags", "oldest-first", flag_error_mock)
        
        assert '--output=tags' in mock_run.call_args[0][0]
        assert '--sort=oldest-first' in mock_run.call_args[0][0]
        assert result == ["tag1", "tag2"]


class TestFindMatchingThreads:
    """Tests for find_matching_threads() function."""
    
    @patch('notmuch.notmuch_search')
    def test_find_matching_threads(self, mock_search, flag_error_mock):
        """Test thread retrieval."""
        mock_search.return_value = [
            {"thread": "thread1", "subject": "Subject 1"},
            {"thread": "thread2", "subject": "Subject 2"}
        ]
        
        result = find_matching_threads("tag:inbox", flag_error_mock)
        
        assert len(result) == 2
        assert result[0]["thread"] == "thread1"
        
        mock_search.assert_called_once_with("tag:inbox", "summary", "newest-first", flag_error_mock)


class TestApplyTagToQuery:
    """Tests for apply_tag_to_query() function."""
    
    @patch('subprocess.run')
    def test_apply_tag_addition(self, mock_run, flag_error_mock):
        """Test adding a tag with + prefix."""
        apply_tag_to_query("+work", "tag:inbox", flag_error_mock)
        
        call_args = mock_run.call_args
        assert call_args[0][0][0] == 'notmuch'
        assert call_args[0][0][1] == 'tag'
        assert call_args[0][0][2] == "+work"
        assert call_args[0][0][3] == '--'
        assert call_args[0][0][4] == "tag:inbox"
    
    @patch('subprocess.run')
    def test_apply_tag_removal(self, mock_run, flag_error_mock):
        """Test removing a tag with - prefix."""
        apply_tag_to_query("-spam", "tag:inbox", flag_error_mock)
        
        call_args = mock_run.call_args
        assert call_args[0][0][2] == "-spam"
    
    @patch('subprocess.run')
    def test_apply_tag_with_check_true(self, mock_run, flag_error_mock):
        """Test with check=True (default)."""
        apply_tag_to_query("+todo", "tag:inbox", flag_error_mock)
        
        mock_run.assert_called_once()
        assert mock_run.call_args[1]['check'] is True


class TestGetTagsFromQuery:
    """Tests for get_tags_from_query() function."""
    
    @patch('subprocess.run')
    def test_get_tags_from_query_success(self, mock_run, flag_error_mock):
        """Test successful tag retrieval."""
        mock_result = MagicMock()
        mock_result.stdout = "inbox\nunread\nwork\n"
        mock_result.return_value = mock_result
        
        result = get_tags_from_query("tag:inbox", flag_error_mock)
        
        assert result == ["inbox", "unread", "work"]
    
    @patch('subprocess.run')
    def test_get_tags_from_query_empty(self, mock_run, flag_error_mock):
        """Test with no tags."""
        mock_result = MagicMock()
        mock_result.stdout = "\n"
        mock_run.return_value = mock_result
        
        result = get_tags_from_query("tag:empty", flag_error_mock)
        
        assert result == []
    
    @patch('subprocess.run')
    def test_get_tags_from_query_sorting(self, mock_run, flag_error_mock):
        """Test that tags are sorted."""
        mock_result = MagicMock()
        mock_result.stdout = "zulu\nc\nalpha\nbeta\n"
        mock_run.return_value = mock_result
        
        result = get_tags_from_query("tag:inbox", flag_error_mock)
        
        assert result == ["alpha", "beta", "c", "zulu"]
    
    @patch('subprocess.run')
    def test_get_tags_from_query_whitespace(self, mock_run, flag_error_mock):
        """Test whitespace trimming."""
        mock_result = MagicMock()
        mock_result.stdout = "  inbox  \n  unread  \n  work  \n"
        mock_run.return_value = mock_result
        
        result = get_tags_from_query("tag:inbox", flag_error_mock)
        
        assert result == ["inbox", "unread", "work"]
    
    @patch('subprocess.run')
    def test_get_tags_from_query_command_construction(self, mock_run, flag_error_mock):
        """Test that command is constructed correctly."""
        mock_result = MagicMock()
        mock_result.stdout = "inbox\n"
        mock_run.return_value = mock_result
        
        get_tags_from_query("tag:inbox", flag_error_mock)
        
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == 'notmuch'
        assert call_args[1] == 'search'
        assert '--output=tags' in call_args
        assert '--format=text' in call_args
        # Should include spam filter
        assert "tag:spam or not tag:spam" in ' '.join(call_args)


class TestUpdateUnseenFromQuery:
    """Tests for update_unseen_from_query() function."""
    
    @patch('notmuch.apply_tag_to_query')
    @patch('notmuch.get_tags_from_query')
    def test_update_unseen_when_present(self, mock_get_tags, mock_apply, flag_error_mock):
        """Test conversion when $unseen tag is present."""
        mock_get_tags.return_value = ["$unseen", "inbox"]
        
        update_unseen_from_query("id:msg123", flag_error_mock)
        
        # Should call apply_tag_to_query to add $unused
        mock_apply.assert_any_call("+$unused", "id:msg123", flag_error_mock)
        # Should call apply_tag_to_query to remove $unseen
        mock_apply.assert_any_call("-$unseen", "id:msg123", flag_error_mock)
    
    @patch('notmuch.apply_tag_to_query')
    @patch('notmuch.get_tags_from_query')
    def test_update_unseen_when_absent(self, mock_get_tags, mock_apply, flag_error_mock):
        """Test no action when $unseen tag is absent."""
        mock_get_tags.return_value = ["inbox", "unread"]
        
        update_unseen_from_query("id:msg123", flag_error_mock)
        
        # Should not call apply_tag_to_query
        mock_apply.assert_not_called()
