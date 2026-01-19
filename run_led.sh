#!/bin/bash
set -e

# Diretório base onde o script e o venv estão
BASE_DIR="/var/home/bruno/.script"

# Ativar virtual environment
source "$BASE_DIR/bin/activate"

# Executar o script python passando todos os argumentos
python3 "$BASE_DIR/controlador_led.py" "$@"
