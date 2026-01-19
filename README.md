# Controlador LED BLE (Python)

Um script simples e eficiente para controlar fitas de LED Bluetooth Low Energy (BLE) (compatível com controladores Magic Home / Flux LED) diretamente do seu Linux (testado no Fedora Silverblue).

## Funcionalidades

- **Controle via Terminal:** Interface interativa simples.
- **Atalhos Rápidos:** Salve e carregue até 9 predefinições de cor/brilho.
- **Integração Desktop:** Atalho no menu de aplicativos do GNOME/KDE.
- **Ambiente Isolado:** Roda em um virtualenv próprio, sem sujar o sistema (ideal para Silverblue/Atomic).

## Pré-requisitos

- Python 3.9+
- Adaptador Bluetooth funcional

## Instalação Rápida

1. Clone este repositório:
   ```bash
   git clone <URL_DO_SEU_REPO>
   cd controlador_led_ble
   ```

2. Execute o instalador:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

O instalador irá:
- Configurar o diretório em `~/.script` (padrão hardcoded no script, pode ser ajustado).
- Criar o ambiente virtual.
- Instalar as dependências (`bleak`, `led_ble`, etc).
- Criar o atalho no menu de aplicativos.

## Uso

### Via Interface Gráfica
Procure por **"Controlador LED"** no seu menu de aplicativos.

### Via Terminal
```bash
~/.script/run_led.sh
```

### Comandos
- **Setas Cima/Baixo:** Ajustar Brilho
- **Setas Esq/Dir:** Ajustar Cor (Hue)
- **1-9:** Carregar atalho salvo
- **s + [1-9]:** Salvar configuração atual no slot
- **q / Esc:** Sair

## Estrutura de Arquivos

- `controlador_led.py`: Script principal.
- `run_led.sh`: Wrapper para rodar com o venv correto.
- `install.sh`: Script de automação de setup.
- `atalhos_led.json`: Armazena seus presets (gerado automaticamente).
