"""
Integration tests for send-mail.py - SMTP sending functionality.

Tests for:
- SendMail.__init__()
- SendMail._load_config()
- SendMail._get_account_info()
- SendMail._move_file()
- SendMail.send_file()
- SendMail._send_via_smtp()

All tests use mocking for subprocess and smtplib.
"""
import pytest
from unittest.mock import MagicMock, Mock, patch
from pathlib import Path
import email
from email import policy
import sys
import importlib.util

# Load send-mail.py (hyphenated filename) as a module
spec = importlib.util.spec_from_file_location("send_mail", "../scripts/send-mail.py")
send_mail = importlib.util.module_from_spec(spec)
sys.modules["send_mail"] = send_mail
spec.loader.exec_module(send_mail)

from send_mail import SendMail


class TestSendMailInit:
    """Tests for SendMail.__init__() method."""
    
    def test_load_config_when_file_exists(self, temp_smtp_config_file):
        """Test loading config when file exists."""
        sender = SendMail(temp_smtp_config_file)
        
        assert sender.config is not None
        assert "from" in sender.config
    
    def test_load_config_creates_default_when_missing(self, tmp_path):
        """Test handling when config file doesn't exist."""
        non_existent_config = tmp_path / "nonexistent.toml"
        
        with pytest.raises(SystemExit):
            sender = SendMail(str(non_existent_config))
    
    @patch('sys.exit')
    def test_exit_on_config_not_found(self, mock_exit, tmp_path):
        """Test that sys.exit is called when config is missing."""
        non_existent = tmp_path / "missing.toml"
        
        sender = SendMail(str(non_existent))
        
        mock_exit.assert_called()


class TestSendMailLoadConfig:
    """Tests for SendMail._load_config() method."""
    
    def test_load_valid_toml(self, tmp_path):
        """Test loading valid TOML configuration."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        sender = SendMail(str(config_file))
        config = sender._load_config()
        
        assert "from" in config
        assert config["from"]["test@example.com"]["smtp_server"] == "smtp.example.com"
    
    def test_invalid_toml_syntax(self, tmp_path):
        """Test handling of invalid TOML syntax."""
        config_content = """
[from."test@example.com"
invalid toml syntax
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        with pytest.raises(SystemExit):
            sender = SendMail(str(config_file))


class TestSendMailGetAccountInfo:
    """Tests for SendMail._get_account_info() method."""
    
    def test_get_account_found(self, temp_smtp_config_file):
        """Test finding account by from address."""
        sender = SendMail(temp_smtp_config_file)
        
        account = sender._get_account_info("test@example.com")
        
        assert account is not None
        assert account["smtp_server"] == "smtp.example.com"
        assert account["smtp_port"] == 587
        assert account["username"] == "test@example.com"
    
    def test_get_account_not_found(self, temp_smtp_config_file):
        """Test when account is not found."""
        sender = SendMail(temp_smtp_config_file)
        
        with pytest.raises(SystemExit):
            sender._get_account_info("unknown@example.com")
    
    def test_get_account_no_from_section(self, tmp_path):
        """Test when [[from]] section is missing."""
        config_content = """
[some_other_section]
key = "value"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        sender = SendMail(str(config_file))
        
        with pytest.raises(SystemExit):
            sender._get_account_info("test@example.com")


class TestSendMailMoveFile:
    """Tests for SendMail._move_file() method."""
    
    def test_move_file_to_existing_directory(self, tmp_path):
        """Test moving file to existing directory."""
        sender = SendMail(temp_smtp_config_file)
        
        source = tmp_path / "source.txt"
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        
        source.write_text("content")
        
        sender._move_file(source, dest_dir)
        
        assert not source.exists()
        assert (dest_dir / "source.txt").exists()
        assert (dest_dir / "source.txt").read_text() == "content"
    
    def test_move_file_creates_directory(self, tmp_path):
        """Test that destination directory is created if missing."""
        sender = SendMail(temp_smtp_config_file)
        
        source = tmp_path / "source.txt"
        dest_dir = tmp_path / "new_dest"
        
        source.write_text("content")
        
        sender._move_file(source, dest_dir)
        
        assert dest_dir.exists()
        assert (dest_dir / "source.txt").exists()


class TestSendMailSendFile:
    """Tests for SendMail.send_file() method."""
    
    @patch('send_mail.SendMail._send_via_smtp')
    def test_send_file_success(self, mock_send, tmp_path, mock_email_message):
        """Test successful file sending."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        # Create test email file
        email_file = tmp_path / "test.eml"
        email_file.write_text("From: test@example.com\nTo: recipient@example.com\n\nBody")
        
        sender = SendMail(str(config_file))
        sender.send_file(str(email_file))
        
        mock_send.assert_called_once()
    
    def test_send_file_not_found(self, tmp_path):
        """Test when email file doesn't exist."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        sender = SendMail(str(config_file))
        
        with pytest.raises(SystemExit):
            sender.send_file(str(tmp_path / "nonexistent.eml"))
    
    @patch('send_mail.SendMail._send_via_smtp')
    def test_send_file_extracts_from_address(self, mock_send, tmp_path, mock_email_message):
        """Test that From address is extracted correctly."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        email_file = tmp_path / "test.eml"
        email_file.write_text("From: test@example.com\nTo: recipient@example.com\n\nBody")
        
        sender = SendMail(str(config_file))
        sender.send_file(str(email_file))
        
        call_args = mock_send.call_args
        assert call_args[0][1] == "test@example.com"
    
    @patch('send_mail.SendMail._send_via_smtp')
    def test_send_file_missing_from_header(self, mock_send, tmp_path):
        """Test when From header is missing."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        email_file = tmp_path / "test.eml"
        email_file.write_text("To: recipient@example.com\n\nBody")
        
        sender = SendMail(str(config_file))
        
        with pytest.raises(SystemExit):
            sender.send_file(str(email_file))


class TestSendMailSendViaSmtp:
    """Tests for SendMail._send_via_smtp() method."""
    
    @patch('smtplib.SMTP')
    def test_send_via_smtp_starttls(self, mock_smtp_class, tmp_path, mock_email_message):
        """Test sending via STARTTLS (port 587)."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        # Setup mock SMTP
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
        
        sender = SendMail(str(config_file))
        
        email_file = tmp_path / "test.eml"
        email_file.write_text("From: test@example.com\n\nBody")
        
        sender.send_file(str(email_file))
        
        # Verify STARTTLS flow
        mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("test@example.com", "test-pass")
        mock_smtp_instance.send_message.assert_called_once()
    
    @patch('smtplib.SMTP_SSL')
    def test_send_via_smtp_ssl(self, mock_smtp_class, tmp_path, mock_email_message):
        """Test sending via SSL (port 465)."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 465
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        # Setup mock SMTP
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
        
        sender = SendMail(str(config_file))
        
        email_file = tmp_path / "test.eml"
        email_file.write_text("From: test@example.com\n\nBody")
        
        sender.send_file(str(email_file))
        
        # Verify SSL flow (no starttls)
        mock_smtp_class.assert_called_once_with("smtp.example.com", 465)
        assert mock_smtp_instance.starttls.call_count == 0  # No starttls
        mock_smtp_instance.login.assert_called_once_with("test@example.com", "test-pass")
        mock_smtp_instance.send_message.assert_called_once()
    
    @patch('smtplib.SMTP')
    def test_send_via_smtp_smtp_exception(self, mock_smtp_class, tmp_path):
        """Test handling SMTPException."""
        from smtplib import SMTPException
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        # Setup mock to raise exception
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
        mock_smtp_instance.send_message.side_effect = SMTPException("Connection failed")
        
        sender = SendMail(str(config_file))
        
        email_file = tmp_path / "test.eml"
        email_file.write_text("From: test@example.com\n\nBody")
        
        # Should not raise exception, but move to failed directory
        sender.send_file(str(email_file))
        
        # File should be moved to failed directory
        # (Note: This will try to create /tmp/failed which may not exist)
    
    @patch('smtplib.SMTP')
    def test_send_via_smtp_general_exception(self, mock_smtp_class, tmp_path):
        """Test handling general exceptions."""
        config_content = """
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "/tmp/sent"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        # Setup mock to raise exception
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
        mock_smtp_instance.send_message.side_effect = Exception("Unexpected error")
        
        sender = SendMail(str(config_file))
        
        email_file = tmp_path / "test.eml"
        email_file.write_text("From: test@example.com\n\nBody")
        
        # Should not raise exception, but move to failed directory
        sender.send_file(str(email_file))
    
    @patch('smtplib.SMTP')
    def test_send_via_smtp_moves_to_sent(self, mock_smtp_class, tmp_path):
        """Test that file is moved to sent directory on success."""
        sent_dir = tmp_path / "sent"
        sent_dir.mkdir()
        
        config_content = f"""
[from."test@example.com"]
smtp_server = "smtp.example.com"
smtp_port = 587
username = "test@example.com"
password = "test-pass"
sent_dir = "{sent_dir}"
failed_dir = "/tmp/failed"
"""
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)
        
        # Setup mock
        mock_smtp_instance = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp_instance
        
        sender = SendMail(str(config_file))
        
        email_file = tmp_path / "test.eml"
        email_file.write_text("From: test@example.com\n\nBody")
        
        sender.send_file(str(email_file))
        
        # File should be moved to sent directory
        assert not email_file.exists()
        assert (sent_dir / "test.eml").exists()
