"""
Shared fixtures and utilities for kubux-mail-client tests.

This module provides common test fixtures used across multiple test files.
"""
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock
import pytest

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory for config files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create a temporary directory for data files."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def sample_config_content(temp_config_dir, temp_data_dir):
    """Generate sample TOML config content."""
    return f"""[visual]
interface_font = "monospace"
interface_font_size = 12
menu_font = "monospace"
menu_font_size = 12
text_font = "monospace"
text_font_size = 12

[tags]
tags = ["todo", "done", "read", "important"]

[bindings]
quit_action = "Ctrl+Q"
zoom_in = "Ctrl++"
zoom_out = "Ctrl+-"

[email_identities]
identities = [
    {{name = "Test User", email = "test@example.com", drafts = "{temp_data_dir}/drafts", template = "{temp_data_dir}/template.eml"}},
    {{name = "Another User", email = "another@example.com", drafts = "{temp_data_dir}/drafts2"}}
]

[searches]
tags = ["inbox", "unread"]
search = "tag:inbox and tag:unread"

[predicting]
model = "{temp_data_dir}/model.joblib"

[autocomplete]
headers = "from,to,cc"
"""


@pytest.fixture
def temp_config_file(temp_config_dir, sample_config_content):
    """Create a temporary config file with sample content."""
    config_file = temp_config_dir / "config.toml"
    config_file.write_text(sample_config_content)
    return str(config_file)


# ============================================================================
# Email File Fixtures
# ============================================================================

@pytest.fixture
def sample_plain_email():
    """Create a sample plain text email."""
    return """From: sender@example.com
To: recipient@example.com
Subject: Test Subject
Date: Wed, 25 Dec 2025 22:00:00 +0000
Message-ID: <test123@example.com>

This is a plain text email body.
It has multiple lines.
"""


@pytest.fixture
def sample_html_email():
    """Create a sample HTML email."""
    return """From: sender@example.com
To: recipient@example.com
Subject: HTML Email
Date: Wed, 25 Dec 2025 22:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/alternative; boundary="boundary123"

--boundary123
Content-Type: text/plain; charset=utf-8

Plain text version

--boundary123
Content-Type: text/html; charset=utf-8

<html><body><p><b>Bold HTML</b> text</p></body></html>
--boundary123--
"""


@pytest.fixture
def sample_multipart_email():
    """Create a sample multipart email with attachments."""
    return """From: sender@example.com
To: recipient@example.com
Subject: Multipart Email
Date: Wed, 25 Dec 2025 22:00:00 +0000
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed123"

--mixed123
Content-Type: text/plain; charset=utf-8

Email body text

--mixed123
Content-Type: text/plain; name="attachment.txt"
Content-Disposition: attachment; filename="attachment.txt"
Content-Transfer-Encoding: base64

SGVsbG8gYXR0YWNobWVudA==

--mixed123--
"""


@pytest.fixture
def temp_email_file(tmp_path, sample_plain_email):
    """Create a temporary email file."""
    email_file = tmp_path / "test_email.eml"
    email_file.write_text(sample_plain_email)
    return email_file


# ============================================================================
# SMTP Configuration Fixtures
# ============================================================================

@pytest.fixture
def sample_smtp_config():
    """Generate sample SMTP configuration."""
    return """[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-password"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""


@pytest.fixture
def temp_smtp_config_file(tmp_path, sample_smtp_config):
    """Create a temporary SMTP config file."""
    config_file = tmp_path / "smtp-config.toml"
    config_file.write_text(sample_smtp_config)
    return str(config_file)


@pytest.fixture
def smtp_account_config():
    """Sample SMTP account configuration dictionary."""
    return {
        'smtp_server': 'smtp.example.com',
        'smtp_port': 587,
        'username': 'test@example.com',
        'password': 'test-password',
        'sent_dir': '/tmp/sent',
        'failed_dir': '/tmp/failed'
    }


# ============================================================================
# Mock Helpers
# ============================================================================

@pytest.fixture
def mock_subprocess():
    """Create a mock subprocess helper."""
    mock = MagicMock()
    mock.run.return_value = MagicMock(
        stdout='',
        stderr='',
        returncode=0
    )
    return mock


@pytest.fixture
def mock_smtp():
    """Create a mock SMTP connection."""
    mock_smtp_class = MagicMock()
    mock_smtp_instance = MagicMock()
    
    # Make it work as a context manager
    mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
    
    return mock_smtp_class, mock_smtp_instance


@pytest.fixture
def mock_email_message():
    """Create a mock email message."""
    msg = MagicMock()
    msg.get.side_effect = lambda key, default='': {
        'From': 'sender@example.com',
        'To': 'recipient@example.com',
        'Cc': 'cc@example.com',
        'Subject': 'Test Subject',
        'Date': 'Wed, 25 Dec 2025 22:00:00 +0000',
        'Message-ID': '<test@example.com>'
    }.get(key, default)
    msg.get_all.side_effect = lambda key, default=[]: {
        'To': ['recipient@example.com'],
        'Cc': ['cc@example.com'],
        'Bcc': ['bcc@example.com']
    }.get(key, default)
    return msg


# ============================================================================
# Flag Error Mock
# ============================================================================

@pytest.fixture
def flag_error_mock():
    """Create a mock flag_error function."""
    return MagicMock()


# ============================================================================
# AI Training Fixtures
# ============================================================================

@pytest.fixture
def sample_email_texts():
    """Sample email texts for AI training."""
    return [
        "Subject: Important meeting\nFrom: boss@example.com\n\nPlease attend the meeting tomorrow at 10am.",
        "Subject: Project update\nFrom: team@example.com\n\nHere's the latest status on our project.",
        "Subject: Lunch invitation\nFrom: friend@example.com\n\nWant to grab lunch today?"
    ]


# ============================================================================
# Maildir Structure Fixtures
# ============================================================================

@pytest.fixture
def temp_maildir(tmp_path):
    """Create a temporary maildir structure."""
    maildir = tmp_path / "maildir"
    maildir.mkdir()
    (maildir / "cur").mkdir()
    (maildir / "new").mkdir()
    (maildir / "tmp").mkdir()
    return maildir


@pytest.fixture
def temp_drafts_dir(tmp_path):
    """Create a temporary drafts directory."""
    drafts = tmp_path / "drafts"
    drafts.mkdir()
    return drafts


# ============================================================================
# Test Data Helpers
# ============================================================================

@pytest.fixture
def create_test_email(tmp_path):
    """Helper to create test email files."""
    def _create(filename, content):
        email_file = tmp_path / filename
        email_file.write_text(content)
        return email_file
    return _create


# ============================================================================
# AI Model Mocks
# ============================================================================

@pytest.fixture
def mock_ai_model():
    """Create a mock AI model data structure."""
    return {
        'vectorizer': MagicMock(),
        'classifier': MagicMock(),
        'tags': ['work', 'personal', 'spam']
    }
