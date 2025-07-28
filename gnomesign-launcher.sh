#!/bin/sh
# sets path for application modules in Python
export PYTHONPATH=/app/share/gnomesign

# runs the application main script
cd /app/share/gnomesign
exec python3 main.py "$@"

