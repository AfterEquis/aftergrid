#!/bin/bash
# TermLink startup script
# Activa el entorno virtual y arranca la aplicación de chat con cualquier argumento opcional

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
"$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/chat.py" "$@"
