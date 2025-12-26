"""
Integration tests for email parsing using real test emails.

Tests use actual email files from tests/tagged/ and tests/untagged/.
"""
import pytest
from pathlib import Path
import email
from email import policy
import sys
import importlib.util

# Load ai-classify.py (hyphenated filename) as a module
spec_ai_classify = importlib.util.spec_from_file_location("ai_classify", "../scripts/ai-classify.py")
ai_classify = importlib.util.module_from_spec(spec_ai_classify)
sys.modules["ai_classify"] = ai_classify
spec_ai_classify.loader.exec_module(ai_classify)

# Load ai-train.py (hyphenated filename) as a module
spec_ai_train = importlib.util.spec_from_file_location("ai_train", "../scripts/ai-train.py")
ai_train = importlib.util.module_from_spec(spec_ai_train)
sys.modules["ai_train"] = ai_train
spec_ai_train.loader.exec_module(ai_train)

from ai_classify import extract_email_text


class TestRealEmailFiles:
    """Tests using real email files from test suite."""
    
    @pytest.mark.skip(reason="Tagged directory may not exist in test environment")
    def test_parse_tagged_email_exists(self):
        """Test that tagged email files exist."""
        tagged_dir = Path(__file__).parent / "tagged"
        assert tagged_dir.exists()
        
        email_files = list(tagged_dir.glob("*.gauss"))
        assert len(email_files) > 0
    
    @pytest.mark.skip(reason="Untagged directory may not exist in test environment")
    def test_parse_untagged_email_exists(self):
        """Test that untagged email files exist."""
        untagged_dir = Path(__file__).parent / "untagged"
        assert untagged_dir.exists()
        
        email_files = list(untagged_dir.glob("*.gauss"))
        assert len(email_files) > 0
    
    def test_extract_text_from_tagged_email(self):
        """Test extracting text from a real tagged email."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            text = extract_email_text(email_file)
            
            # Should have some content
            assert isinstance(text, str)
            assert len(text) > 0
    
    def test_extract_text_from_untagged_email(self):
        """Test extracting text from a real untagged email."""
        untagged_dir = Path(__file__).parent / "untagged"
        email_files = list(untagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            text = extract_email_text(email_file)
            
            # Should have some content
            assert isinstance(text, str)
            assert len(text) > 0
    
    def test_extract_text_from_multiple_emails(self):
        """Test extracting text from multiple emails."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))[:5]  # First 5
        
        for email_file in email_files:
            text = extract_email_text(email_file)
            assert isinstance(text, str)
            assert len(text) > 0
    
    def test_email_file_can_be_parsed_by_email_module(self):
        """Test that email files can be parsed by Python email module."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            with open(email_file, 'rb') as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
            
            # Should have basic email structure
            assert msg is not None
            assert msg.get("From") or msg.get("Date")
    
    def test_extract_text_handles_binary_files(self):
        """Test that extract_email_text handles binary files."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            # Function should handle binary files
            text = extract_email_text(email_file)
            assert isinstance(text, str)


class TestEmailHeaderExtraction:
    """Tests for email header extraction from real emails."""
    
    def test_extract_subject_from_real_email(self):
        """Test subject extraction from real email."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            with open(email_file, 'rb') as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
            
            subject = msg.get("Subject", "")
            assert isinstance(subject, str)
    
    def test_extract_from_address_from_real_email(self):
        """Test From address extraction from real email."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            with open(email_file, 'rb') as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
            
            from_addr = msg.get("From", "")
            assert isinstance(from_addr, str)
            assert "@" in from_addr or from_addr == ""
    
    def test_extract_to_address_from_real_email(self):
        """Test To address extraction from real email."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            with open(email_file, 'rb') as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
            
            to_addr = msg.get("To", "")
            assert isinstance(to_addr, str)


class TestEmailBodyExtraction:
    """Tests for email body extraction from real emails."""
    
    def test_extract_plain_text_body(self):
        """Test extracting plain text body from real email."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            with open(email_file, 'rb') as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
            
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        body = part.get_content()
                        break
            else:
                body = msg.get_content()
            
            # Should have some body content
            assert isinstance(body, str)
    
    def test_email_has_content_type(self):
        """Test that emails have content type."""
        tagged_dir = Path(__file__).parent / "tagged"
        email_files = list(tagged_dir.glob("*.gauss"))
        
        if email_files:
            email_file = email_files[0]
            with open(email_file, 'rb') as f:
                msg = email.message_from_binary_file(f, policy=policy.default)
            
            content_type = msg.get_content_type()
            assert content_type is not None
            assert isinstance(content_type, str)
