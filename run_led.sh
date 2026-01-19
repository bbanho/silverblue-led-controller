#!/bin/bash
set -e

# Obter o diretório onde o script está localizado
BASE_DIR=$(dirname "$(readlink -f "$0")")

# Ativar virtual environment (assumindo que está no mesmo diretório)
if [ -f "$BASE_DIR/bin/activate" ]; then
    source "$BASE_DIR/bin/activate"
else
    echo "Erro: Virtual environment não encontrado em $BASE_DIR/bin"
    echo "Execute ./install.sh primeiro."
    exit 1
fi

# Executar o script python passando todos os argumentos
python3 "$BASE_DIR/controlador_led.py" "$@"
