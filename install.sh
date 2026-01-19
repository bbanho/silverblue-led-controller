#!/bin/bash
set -e

# Verificação de segurança: Não rodar como root
if [ "$EUID" -eq 0 ]; then
  echo "Erro: Este script não deve ser executado como root (sudo)."
  echo "Ele instala arquivos no diretório do usuário atual."
  exit 1
fi

INSTALL_DIR="$HOME/.script"
DESKTOP_FILE="controlador_led.desktop"
DESKTOP_PATH="$HOME/.local/share/applications/$DESKTOP_FILE"

echo "=== Instalador Controlador LED (Fedora Silverblue Friendly) ==="

# 1. Garantir que o diretório existe (se rodando de outro lugar)
if [ "$(pwd)" != "$INSTALL_DIR" ]; then
    echo "Movendo arquivos para $INSTALL_DIR..."
    mkdir -p "$INSTALL_DIR"
    # Usar cp -a . para copiar tudo, incluindo ocultos (.git) para permitir atualizações
    cp -a . "$INSTALL_DIR/"
    cd "$INSTALL_DIR"
fi

# 2. Configurar Python Virtual Environment
if [ ! -d "bin" ]; then
    echo "Criando ambiente virtual..."
    python3 -m venv .
fi

# 3. Instalar Dependências
echo "Instalando dependências..."
./bin/pip install --upgrade pip
./bin/pip install -r requirements.txt

# 4. Permissões
echo "Ajustando permissões..."
chmod +x controlador_led.py run_led.sh update.sh

# 5. Instalar Desktop Entry
echo "Instalando atalho no menu..."
mkdir -p "$HOME/.local/share/applications"

# Copiar e ajustar o caminho do executável no arquivo .desktop
cp "$DESKTOP_FILE" "$DESKTOP_PATH"
# Substituir a linha Exec=... pelo caminho correto dinâmico
sed -i "s|Exec=.*|Exec=$INSTALL_DIR/run_led.sh|" "$DESKTOP_PATH"

# Atualizar banco de dados de desktop entries
update-desktop-database "$HOME/.local/share/applications" || true

echo "=== Instalação Concluída! ==="
echo "Você pode rodar pelo terminal: $INSTALL_DIR/run_led.sh"
echo "Ou procurar por 'Controlador LED' no menu de aplicativos."
