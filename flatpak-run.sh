#!/bin/bash
# Script de entrada para o Flatpak
# No Flatpak, as libs estão no path padrão do python (/app/lib/...)

# Executar a aplicação
exec python3 /app/bin/controlador_led.py "$@"
