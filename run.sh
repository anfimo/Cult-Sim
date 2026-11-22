#!/bin/sh
cd "$(dirname "$0")" && exec uv run main.py "$@"
