#!/bin/bash
set -e

# Diretório base
BASE_DIR=$(dirname "$(readlink -f "$0")")
cd "$BASE_DIR"

echo "=== Atualizador Controlador LED ==="

if [ ! -d ".git" ]; then
    echo "Erro: Não é um repositório git. A atualização automática não é possível."
    echo "Reinstale clonando o repositório novamente."
    exit 1
fi

echo "Buscando atualizações..."
git fetch origin

# Verificar se HEAD está detached ou se há upstream configurado
if ! git rev-parse @{u} >/dev/null 2>&1; then
    echo "Aviso: Nenhum upstream configurado. Tentando pull direto da origin/main..."
    git pull origin main || git pull origin master
else
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse @{u})

    if [ "$LOCAL" = "$REMOTE" ]; then
        echo "Já está atualizado."
        # Mesmo se o código estiver atualizado, verificar dependências pode ser útil, 
        # mas vamos sair para ser mais rápido, a menos que o usuário force.
        exit 0
    fi

    echo "Atualização encontrada. Aplicando..."
    git pull
fi

# Atualizar dependências se houver venv
if [ -d "bin" ]; then
    echo "Atualizando dependências Python..."
    source bin/activate
    pip install -r requirements.txt
fi

echo "Atualização concluída com sucesso!"
echo "Por favor, reinicie o controlador."
