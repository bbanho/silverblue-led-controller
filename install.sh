#!/bin/bash
set -e

# Cores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔧 Instalando Dependências do Controlador LED (Audio Sync)...${NC}"

# Verificar se está em um venv
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo -e "${BLUE}Criando ambiente virtual...${NC}"
    python3 -m venv .venv
    source .venv/bin/activate
else
    echo -e "${GREEN}Ambiente virtual detectado.${NC}"
fi

# Instalar libs
echo -e "${BLUE}Instalando pacotes Python (bleak, textual, numpy, sounddevice)...${NC}"
pip install --upgrade pip
pip install -r requirements.txt
pip install numpy sounddevice

# Permissões Bluetooth (se necessário)
# echo -e "${BLUE}Verificando permissões...${NC}"
# sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))

echo -e "${GREEN}✅ Instalação Concluída!${NC}"
echo -e "Para rodar o sync de áudio, use: ${GREEN}./run_audio_sync.sh${NC}"
