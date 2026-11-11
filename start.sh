#!/bin/bash
# Запуск KinoBudka на Linux / macOS: ./start.sh

# Exit early on errors
set -eu

cd "$(dirname "$0")"

# Python buffers stdout. Without this, you won't see what you "print" in the Activity Logs
export PYTHONUNBUFFERED=true

# Install Python 3 virtual env
VIRTUALENV=./venv

if [ ! -d $VIRTUALENV ]; then
  python3 -m venv $VIRTUALENV
fi

# Install the requirements
$VIRTUALENV/bin/pip install --disable-pip-version-check -q -r requirements.txt

# Run your glorious application
exec $VIRTUALENV/bin/python3 main.py
