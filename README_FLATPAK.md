# Versão Flatpak - Controlador LED

Esta branch contém o suporte experimental para empacotamento Flatpak, permitindo rodar o controlador em qualquer distribuição Linux de forma isolada.

## Estrutura

- `io.github.silverblue_led_controller.yml`: Manifesto do Flatpak.
- `flatpak-run.sh`: Script de entrada do container.
- `build_flatpak.sh`: Script auxiliar para construir e instalar localmente.

## Como Construir e Instalar

1. Certifique-se de ter o `flatpak` e `flatpak-builder` instalados.
   - Fedora/Silverblue: `sudo rpm-ostree install flatpak-builder` (necessário reboot) ou via toolbox.

2. Execute o script de build:
   ```bash
   ./build_flatpak.sh
   ```
   Este script irá:
   - Baixar o Runtime/SDK (org.freedesktop.Platform 23.08) se necessário.
   - Compilar o app e instalar as dependências Python (usando rede).
   - Instalar o Flatpak no seu usuário (`--user`).

## Como Rodar

Após a instalação, execute:
```bash
flatpak run io.github.silverblue_led_controller
```

## Permissões Bluetooth

O Flatpak está configurado para acessar o DBus do sistema (`--socket=system-bus`), o que é necessário para o `bleak` se comunicar com o BlueZ. Certifique-se de que seu adaptador Bluetooth está ativo.

## Configuração

Os atalhos salvos ficarão persistentes em:
`~/.var/app/io.github.silverblue_led_controller/config/controlador-led/atalhos_led.json`
