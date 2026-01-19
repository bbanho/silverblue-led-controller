#!/bin/bash
set -e

APP_ID="io.github.silverblue_led_controller"
MANIFEST="io.github.silverblue_led_controller.yml"
BUILD_DIR="build-dir"
REPO_DIR="repo"

echo "=== Construindo Flatpak para $APP_ID ==="

# Verificar se flatpak-builder está instalado
if ! command -v flatpak-builder &> /dev/null; then
    echo "Erro: flatpak-builder não encontrado. Instale-o (ex: sudo dnf install flatpak-builder)."
    exit 1
fi

# Instalar Runtime e SDK se necessário
echo "Verificando Runtime e SDK..."
flatpak install --user -y org.freedesktop.Platform//23.08 org.freedesktop.Sdk//23.08 || true

# Construir
# --share=network é CRUCIAL aqui pois estamos usando pip install direto no manifesto
echo "Iniciando build..."
flatpak-builder --user --install --force-clean --share=network "$BUILD_DIR" "$MANIFEST"

echo "=== Concluído! ==="
echo "Para rodar: flatpak run $APP_ID"
