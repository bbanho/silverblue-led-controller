#!/bin/bash
set -e

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

INSTALL_DIR="$HOME/.local/share/silverblue-led-controller"
DESKTOP_DIR="$HOME/.local/share/applications"

echo -e "${BLUE}🔧 Instalando Controlador LED (Vibe Engine)...${NC}"

# 1. Setup Venv
echo -e "${BLUE}📦 Configurando Python Venv...${NC}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# 2. Verificar Dependências de Sistema (PortAudio)
echo -e "${BLUE}🔍 Verificando dependências de sistema...${NC}"
if ! ldconfig -p | grep -q libportaudio; then
    echo -e "${YELLOW}⚠️  Aviso: 'libportaudio' não encontrado.${NC}"
    echo "O 'sounddevice' precisa dele. Se falhar, instale no host:"
    echo "  rpm-ostree install portaudio"
    echo "Ou use dentro de um toolbox."
fi

# 3. Criar Atalhos Desktop
echo -e "${BLUE}📝 Criando atalhos no Menu de Aplicativos...${NC}"
mkdir -p "$DESKTOP_DIR"

# Atalho Audio Sync
cat > "$DESKTOP_DIR/led-audio-sync.desktop" <<EOF
[Desktop Entry]
Name=LED Audio Sync (Vibe Engine)
Comment=Sincroniza luzes com a música (Chill/Party/Rage)
Exec=$(pwd)/run_audio_sync.sh
Icon=audio-speakers
Terminal=true
Type=Application
Categories=Utility;AudioVideo;
EOF

# Atalho Screen Sync
cat > "$DESKTOP_DIR/led-screen-sync.desktop" <<EOF
[Desktop Entry]
Name=LED Ambilight (Screen)
Comment=Sincroniza luzes com a tela (Requer Toolbox)
Exec=$(pwd)/run_screen_sync.sh
Icon=video-display
Terminal=true
Type=Application
Categories=Utility;Video;
EOF

# Atualizar banco de dados desktop
update-desktop-database "$DESKTOP_DIR" || true

echo -e "${GREEN}✅ Instalação Concluída!${NC}"
echo -e "Use os ícones 'LED Audio Sync' e 'LED Ambilight' no menu ou rode:"
echo -e "  ${GREEN}./run_audio_sync.sh${NC}"
