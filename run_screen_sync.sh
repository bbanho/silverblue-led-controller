#!/bin/bash
cd "$(dirname "$0")"
# Rodar dentro do toolbox fedora-toolbox-42
echo "📦 Entrando no Toolbox..."
toolbox run -c fedora-toolbox-42 python3 screen_sync.py
