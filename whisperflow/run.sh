#!/bin/bash
# Verbal App Runner
cd "$(dirname "$0")"
export PYTHONPATH="$(pwd):$PYTHONPATH"

# Find working Python
if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif [ -f ".venv/bin/python3" ]; then
    PYTHON=".venv/bin/python3"
elif command -v python3.14 &> /dev/null; then
    PYTHON="python3.14"
elif command -v python3.13 &> /dev/null; then
    PYTHON="python3.13"
else
    PYTHON="python3"
fi

echo "Starting Verbal with: $PYTHON"
echo "Working directory: $(pwd)"
echo ""

$PYTHON -m app.main
