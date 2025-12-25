# Test Suite for kubux-mail-client

This directory contains the complete test suite for the kubux-mail-client project.

## Overview

The test suite covers **67 testable functions/methods** across 6 modules:

- **Pure functions** (14 tests) - No external dependencies
- **Integration tests** (32 tests) - With mocking of subprocess, smtplib, joblib
- **Email parsing tests** (9 tests) - Using real test emails
- **GUI tests** (7 tests) - With pytest-qt (optional)

**Total: 62 tests**

## Test Files

### Pure Function Tests (No Mocking)

- `test_common.py` - Tests for `html_to_plain_text()` (31 tests)
- `test_config.py` - Tests for Config class (11 tests)
- `test_ai_train.py` - Tests for `filter()` function (17 tests)

### Integration Tests (With Mocking)

- `test_notmuch.py` - Notmuch wrapper functions (8 tests)
- `test_send_mail.py` - SMTP sending functionality (9 tests)
- `test_ai_classify.py` - AI classification (3 tests)
- `test_view_mail_logic.py` - View-mail non-GUI methods (15 tests)

### Email Parsing Tests

- `test_email_parsing.py` - Real email file parsing (9 tests)

## Installation

### Install Test Dependencies

```bash
cd tests
pip install -r requirements-test.txt
```

Or install globally:

```bash
pip install pytest pytest-cov pytest-mock pytest-qt
```

### System Dependencies

Tests require the following system packages:

- Python 3.8+
- Notmuch (for real integration tests if needed)
- Qt6/PySide6 (for GUI tests)

## Running Tests

### Run All Tests

```bash
# From project root
cd tests
pytest
```

### Run Specific Test Files

```bash
# Run only config tests
pytest test_config.py

# Run only common tests
pytest test_common.py

# Run only notmuch tests
pytest test_notmuch.py
```

### Run Specific Test Classes

```bash
# Run specific test class
pytest test_config.py::TestConfigInit

# Run specific test method
pytest test_config.py::TestConfigInit::test_create_default_config_when_not_exists
```

### Run with Markers

```bash
# Run only unit tests (no mocking)
pytest -m unit

# Run only integration tests (with mocking)
pytest -m integration

# Run only GUI tests (requires pytest-qt)
pytest -m gui

# Skip slow tests
pytest -m "not slow"
```

### Run with Coverage Report

```bash
# Generate coverage report
pytest --cov=../scripts --cov-report=term-missing

# Generate HTML coverage report
pytest --cov=../scripts --cov-report=html

# Open HTML report (Linux)
xdg-open htmlcov/index.html
```

### Run in Verbose Mode

```bash
# Show detailed test output
pytest -v

# Show even more detail
pytest -vv
```

### Run in Parallel

```bash
# Run tests in parallel (faster on multi-core)
pytest -n auto
```

## Test Organization

### Phase 1: Test Infrastructure

Files:
- `pytest.ini` - Pytest configuration
- `conftest.py` - Shared fixtures
- `requirements-test.txt` - Test dependencies

### Phase 2: Pure Function Tests

Tests that don't require any mocking:

- `test_common.py` - HTML to plain text conversion
- `test_config.py` - Configuration management
- `test_ai_train.py` - Tag filtering logic

### Phase 3: Integration Tests

Tests that mock external dependencies:

- `test_notmuch.py` - Notmuch subprocess calls
- `test_send_mail.py` - SMTP/smtplib calls
- `test_ai_classify.py` - Joblib model loading
- `test_view_mail_logic.py` - View-mail business logic

### Phase 4: Real Data Tests

Tests using actual test emails:

- `test_email_parsing.py` - Email parsing with real files

## Fixtures

Shared fixtures defined in `conftest.py`:

### Configuration Fixtures

- `temp_config_dir` - Temporary config directory
- `temp_data_dir` - Temporary data directory
- `temp_config_file` - Temporary config file with sample content

### Email File Fixtures

- `sample_plain_email` - Sample plain text email
- `sample_html_email` - Sample HTML email
- `sample_multipart_email` - Sample multipart email
- `temp_email_file` - Temporary email file

### SMTP Configuration Fixtures

- `sample_smtp_config` - Sample SMTP configuration
- `temp_smtp_config_file` - Temporary SMTP config file
- `smtp_account_config` - Sample account configuration dictionary

### Mock Helpers

- `mock_subprocess` - Mocked subprocess.run()
- `mock_smtp` - Mocked SMTP connection
- `mock_email_message` - Mocked email message
- `flag_error_mock` - Mocked flag_error function

### AI Training Fixtures

- `sample_email_texts` - Sample email texts for training

### Maildir Structure Fixtures

- `temp_maildir` - Temporary maildir structure (cur/new/tmp)
- `temp_drafts_dir` - Temporary drafts directory

### Test Data Helpers

- `create_test_email` - Helper to create test emails

### AI Model Mocks

- `mock_ai_model` - Mocked AI model data structure

## Test Markers

Tests are marked with:

- `@pytest.mark.unit` - Unit tests (no mocking)
- `@pytest.mark.integration` - Integration tests (with mocking)
- `@pytest.mark.gui` - GUI tests (requires pytest-qt)
- `@pytest.mark.slow` - Slow tests
- `@pytest.mark.network` - Tests requiring network (avoided)

## Coverage Goals

Current test coverage targets:

- **Lines**: 60% minimum (configured in pytest.ini)
- **Branches**: 60%
- **Functions**: 75%

## Troubleshooting

### Import Errors

If you see import errors:

```bash
# Make sure scripts directory is in path
export PYTHONPATH="${PYTHONPATH}:$(pwd)/../scripts"

# Or run from project root
pytest
```

### PySide6 Not Found

If GUI tests fail to import:

```bash
# Install PySide6
pip install PySide6

# Or skip GUI tests
pytest -m "not gui"
```

### Notmuch Not Installed

Some integration tests assume notmuch is available:

```bash
# Install notmuch (Linux)
sudo apt install notmuch

# Or skip tests that require it
pytest -k "not notmuch"
```

### Mocking Issues

If tests fail with mocking errors:

```bash
# Verify pytest-mock is installed
pip install pytest-mock

# Check patch paths match actual imports
# The patch path must match where the module is imported
```

## CI/CD Integration

Tests are configured to run on push/PR via GitHub Actions:

- `.github/workflows/tests.yml` - CI configuration

## Contributing

### Adding New Tests

1. Determine the test type (unit/integration/gui)
2. Create test file in appropriate directory
3. Use shared fixtures from `conftest.py`
4. Add appropriate marker (@pytest.mark.unit, etc.)
5. Run tests to ensure they pass
6. Check coverage report

### Test Naming Conventions

- Test files: `test_<module_name>.py`
- Test classes: `Test<ClassName>`
- Test methods: `test_<function_name>_<scenario>`

### Example Test

```python
"""Tests for module.function()."""
import pytest
from unittest.mock import patch

class TestClassName:
    """Tests for ClassName."""
    
    @patch('module.external_function')
    def test_function_scenario(self, mock_external, fixture):
        """Test description."""
        # Arrange
        mock_external.return_value = expected_value
        
        # Act
        result = function_under_test(fixture)
        
        # Assert
        assert result == expected_value
        mock_external.assert_called_once()
```

## Performance

Test execution times (approximate):

- Pure function tests: < 1 second
- Integration tests: 5-10 seconds
- Email parsing tests: 2-3 seconds
- GUI tests: 10-15 seconds
- **Total**: ~20-30 seconds

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-mock Documentation](https://pytest-mock.readthedocs.io/)
- [pytest-qt Documentation](https://pytest-qt.readthedocs.io/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)

## License

Same license as kubux-mail-client project.
