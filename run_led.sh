#!/bin/bash
set -e

# Obter o diretório onde o script está localizado
BASE_DIR=$(dirname "$(readlink -f "$0")")

# Ativar virtual environment
if [ -f "$BASE_DIR/bin/activate" ]; then
    source "$BASE_DIR/bin/activate"
else
    echo "Erro: Virtual environment não encontrado em $BASE_DIR/bin"
    exit 1
fi

# Selecionar o script com base no primeiro argumento
if [ "$1" == "fusion" ]; then
    exec python3 "$BASE_DIR/audio_sync_fusion.py"
    
elif [ "$1" == "ping" ]; then
    # Usa o cliente leve para falar com o socket
    shift
    exec python3 "$BASE_DIR/led_ping_client.py" "$@"

elif [ "$1" == "strobe" ]; then
    exec python3 "$BASE_DIR/audio_sync_strobe.py" "$@"
    
elif [ "$1" == "screen" ]; then
    exec python3 "$BASE_DIR/screen_sync.py" "$@"
    
elif [ "$1" == "audio" ]; then
    exec python3 "$BASE_DIR/audio_sync.py" "$@"
    
else
    exec python3 "$BASE_DIR/controlador_led.py" "$@"
fi
