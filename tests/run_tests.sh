#!/usr/bin/env bash
# Run all tests sequentially for kubux-mail-client

# Get the directory where this script is located
cd "$(dirname "$0")"

# Set Python path to include scripts directory
export PYTHONPATH="../scripts:$PYTHONPATH"

echo "========================================"
echo "Running kubux-mail-client test suite"
echo "========================================"
echo ""

# Run tests sequentially with coverage
pytest \
  --cov=../scripts \
  --cov-report=term-missing \
  --cov-report=html \
  --tb=short \
  -v

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "All tests passed! ✓"
    echo "========================================"
    echo ""
    echo "Coverage report generated in htmlcov/index.html"
    echo ""
    echo "View coverage with: xdg-open htmlcov/index.html"
else
    echo ""
    echo "========================================"
    echo "Tests failed! ✗"
    echo "========================================"
    exit 1
fi
