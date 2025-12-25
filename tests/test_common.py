"""
Unit tests for common.py - Pure functions without external dependencies.

Tests for:
- html_to_plain_text()
"""
import pytest
import sys
import importlib.util

# Load common.py as a module (no hyphen)
spec = importlib.util.spec_from_file_location("common", "../scripts/common.py")
common = importlib.util.module_from_spec(spec)
sys.modules["common"] = common
spec.loader.exec_module(common)

from common import html_to_plain_text


class TestHtmlToPlainText:
    """Tests for html_to_plain_text function."""
    
    def test_empty_string(self):
        """Test with empty string."""
        result = html_to_plain_text("")
        assert result == ""
    
    def test_none_input(self):
        """Test with None input."""
        result = html_to_plain_text(None)
        assert result == ""
    
    def test_simple_paragraph_tag(self):
        """Test removing <p> tags."""
        html = "<p>Hello world</p>"
        result = html_to_plain_text(html)
        assert result == "Hello world"
    
    def test_div_tag(self):
        """Test removing <div> tags."""
        html = "<div>Content</div>"
        result = html_to_plain_text(html)
        assert result == "Content"
    
    def test_span_tag(self):
        """Test removing <span> tags."""
        html = "<span>Text</span>"
        result = html_to_plain_text(html)
        assert result == "Text"
    
    def test_br_tag_to_newline(self):
        """Test <br> tag conversion to newline."""
        html = "Line1<br>Line2"
        result = html_to_plain_text(html)
        assert result == "Line1\nLine2"
    
    def test_br_self_closing(self):
        """Test self-closing <br /> tag."""
        html = "Line1<br />Line2"
        result = html_to_plain_text(html)
        assert result == "Line1\nLine2"
    
    def test_p_closing_to_newline(self):
        """Test </p> tag conversion to newline."""
        html = "<p>Line1</p><p>Line2</p>"
        result = html_to_plain_text(html)
        assert result == "Line1\n\nLine2"
    
    def test_script_removal(self):
        """Test removing script tags and content."""
        html = "<p>Hello</p><script>alert('test')</script><p>World</p>"
        result = html_to_plain_text(html)
        assert "alert" not in result
        assert result.strip() == "Hello\nWorld"
    
    def test_style_removal(self):
        """Test removing style tags and content."""
        html = "<p>Text</p><style>.class {{color: red;}}</style>"
        result = html_to_plain_text(html)
        assert "color: red" not in result
        assert result.strip() == "Text"
    
    def test_nested_tags(self):
        """Test removing nested HTML tags."""
        html = "<div><p><span>Nested</span> text</p></div>"
        result = html_to_plain_text(html)
        assert result == "Nested text"
    
    def test_html_entity_nbsp(self):
        """Test decoding &nbsp; entity."""
        html = "Hello&nbsp;World"
        result = html_to_plain_text(html)
        assert result == "Hello World"
    
    def test_html_entity_lt(self):
        """Test decoding < entity."""
        html = "1 < 2"
        result = html_to_plain_text(html)
        assert result == "1 < 2"
    
    def test_html_entity_gt(self):
        """Test decoding > entity."""
        html = "1 > 2"
        result = html_to_plain_text(html)
        assert result == "1 > 2"
    
    def test_html_entity_amp(self):
        """Test decoding & entity."""
        html = "Tom & Jerry"
        result = html_to_plain_text(html)
        assert result == "Tom & Jerry"
    
    def test_multiple_entities(self):
        """Test multiple HTML entities."""
        html = "<tag> & &nbsp;"
        result = html_to_plain_text(html)
        assert result == "<tag> & "
    
    def test_whitespace_consolidation(self):
        """Test consolidating multiple spaces."""
        html = "<p>Text    with    spaces</p>"
        result = html_to_plain_text(html)
        assert result == "Text with spaces"
    
    def test_tab_consolidation(self):
        """Test consolidating tabs."""
        html = "<p>Text\t\twith\ttabs</p>"
        result = html_to_plain_text(html)
        assert result == "Text with tabs"
    
    def test_multiple_newlines_consolidation(self):
        """Test consolidating multiple newlines to double newline."""
        html = "<p>Line1</p><p></p><p>Line2</p>"
        result = html_to_plain_text(html)
        assert result == "Line1\n\nLine2"
    
    def test_excessive_newlines(self):
        """Test reducing many newlines."""
        html = "<p>Line1</p><p></p><p></p><p></p><p>Line2</p>"
        result = html_to_plain_text(html)
        assert result == "Line1\n\nLine2"
    
    def test_preserves_single_newlines(self):
        """Test that single newlines are preserved."""
        html = "Line1<br>Line2<br>Line3"
        result = html_to_plain_text(html)
        assert result == "Line1\nLine2\nLine3"
    
    def test_complex_html_document(self):
        """Test with complex HTML structure."""
        html = """
        <html>
        <head><title>Test</title></head>
        <body>
        <h1>Header</h1>
        <p>Paragraph 1</p>
        <p>Paragraph 2</p>
        <br>
        <div>Div content</div>
        </body>
        </html>
        """
        result = html_to_plain_text(html)
        assert "Header" in result
        assert "Paragraph 1" in result
        assert "Paragraph 2" in result
        assert "Div content" in result
        assert "<html>" not in result
        assert "<head>" not in result
    
    def test_html_with_attributes(self):
        """Test removing tags with attributes."""
        html = '<p class="test" id="para1" style="color:red">Text</p>'
        result = html_to_plain_text(html)
        assert result == "Text"
        assert "class=" not in result
        assert "id=" not in result
        assert "style=" not in result
    
    def test_bold_and_italic_tags(self):
        """Test removing <b>, <strong>, <i>, <em> tags."""
        html = "<b>Bold</b> and <strong>strong</strong> and <i>italic</i> and <em>emphasis</em>"
        result = html_to_plain_text(html)
        assert result == "Bold and strong and italic and emphasis"
    
    def test_link_tag(self):
        """Test removing <a> tags."""
        html = '<a href="http://example.com">Link text</a>'
        result = html_to_plain_text(html)
        assert result == "Link text"
        assert "href=" not in result
    
    def test_list_tags(self):
        """Test removing <ul>, <ol>, <li> tags."""
        html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
        result = html_to_plain_text(html)
        assert "Item 1" in result
        assert "Item 2" in result
        assert "<ul>" not in result
        assert "<li>" not in result
    
    def test_table_tags(self):
        """Test removing <table>, <tr>, <td> tags."""
        html = "<table><tr><td>Cell 1</td><td>Cell 2</td></tr></table>"
        result = html_to_plain_text(html)
        assert "Cell 1" in result
        assert "Cell 2" in result
        assert "<table>" not in result
    
    def test_empty_html(self):
        """Test HTML with no text content."""
        html = "<div><p></p></div>"
        result = html_to_plain_text(html)
        assert result == ""
    
    def test_whitespace_only(self):
        """Test HTML with only whitespace."""
        html = "   \n\t   \n   "
        result = html_to_plain_text(html)
        assert result == ""
    
    def test_preserves_text_content_order(self):
        """Test that text content order is preserved."""
        html = "<p>First</p><div>Second</div><span>Third</span>"
        result = html_to_plain_text(html)
        assert result == "First\nSecond\nThird"
