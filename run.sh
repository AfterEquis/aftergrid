#!/bin/bash
# AfterGrid startup script
# Crea e instala el entorno virtual automáticamente si no existe, y arranca la aplicación de chat.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Si no existe el venv, crearlo e instalar dependencias automáticamente
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Inicializando entorno virtual de Python por primera vez..."
    python3 -m venv "$SCRIPT_DIR/venv"
    echo "Instalando dependencias de AfterGrid..."
    "$SCRIPT_DIR/venv/bin/pip" install --upgrade pip
    "$SCRIPT_DIR/venv/bin/pip" install cryptography websockets prompt-toolkit rich
    echo -e "¡Entorno virtual configurado con éxito!\n"
fi

# Arrancar la aplicación
"$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/chat.py" "$@"
