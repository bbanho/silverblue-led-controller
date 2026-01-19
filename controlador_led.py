#!/usr/bin/env python3
import asyncio
import sys
import tty
import termios
import json
import colorsys
import os
import subprocess
import threading
from bleak import BleakScanner
from led_ble import LEDBLE

# Determinar o diretório onde o script está localizado
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuração para salvar em diretório de usuário (XDG_CONFIG_HOME ou ~/.config)
CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
APP_CONFIG_DIR = os.path.join(CONFIG_DIR, "controlador-led")
os.makedirs(APP_CONFIG_DIR, exist_ok=True)
SHORTCUTS_FILE = os.path.join(APP_CONFIG_DIR, "atalhos_led.json")

class Getch:
    """Captura uma tecla por vez (Linux/Mac)."""
    def __call__(self):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
            if ch == '\x1b':  # Sequência de escape (setas)
                ch += sys.stdin.read(2)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

class LEDController:
    def __init__(self, address):
        self.address = address
        self.led = None
        self.shortcuts = self.load_shortcuts()
        self.hue = 0.0
        self.saturation = 1.0
        self.brightness = 1.0  # 0.0 a 1.0 (para cálculo local)

    def load_shortcuts(self):
        if os.path.exists(SHORTCUTS_FILE):
            try:
                with open(SHORTCUTS_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_shortcuts(self):
        with open(SHORTCUTS_FILE, 'w') as f:
            json.dump(self.shortcuts, f)
        print(f"\rAtalhos salvos em {SHORTCUTS_FILE}    ")

    async def connect(self):
        print(f"Conectando a {self.address}...")
        # LEDBLE requer um BLEDevice, então escaneamos para obtê-lo
        device = await BleakScanner.find_device_by_address(self.address)
        if not device:
            raise Exception(f"Dispositivo {self.address} não encontrado.")
        
        self.led = LEDBLE(device)
        
        # Tratamento de erro robusto para dispositivos fora do padrão (IndexError)
        try:
            await self.led.update()
            await self.led.turn_on()
        except IndexError:
             print("\rAviso: Resposta incompleta do LED (IndexError). Tentando continuar...")
        except Exception as e:
             print(f"\rAviso ao conectar: {e}")

        # Sincronizar estado local se possível
        if self.led.rgb:
            r, g, b = self.led.rgb
            h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            self.hue = h
            self.saturation = s
            # A biblioteca retorna brilho separado às vezes, mas vamos usar V do HSV
            self.brightness = max(v, 0.1) # Evitar 0 absoluto para não perder a cor ao aumentar
        
        print("Conectado! Ligando LED...")
        
        print("\n=== CONTROLE ASCII ===")
        print("A/D: Mudar Cor (Hue)")
        print("W/S: Mudar Brilho")
        print("Teclas 1-9: Carregar atalho")
        print("x depois numero: Salvar atalho no slot")
        print("Q ou ESC: Sair")
        print("======================")

    async def set_color(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.saturation, self.brightness)
        rgb = (int(r * 255), int(g * 255), int(b * 255))
        print(f"\rH:{self.hue:.2f} S:{self.saturation:.2f} V:{self.brightness:.2f} (RGB: {rgb})   ", end="", flush=True)
        try:
            await self.led.set_rgb(rgb)
        except Exception as e:
            pass # Ignorar erros de envio rápido

    async def run(self):
        await self.connect()
        getch = Getch()
        loop = asyncio.get_running_loop()

        running = True
        while running:
            # Executar getch em thread separada para não bloquear o loop asyncio
            key = await loop.run_in_executor(None, getch)

            if key == '\x03' or key == 'q' or key == '\x1b': # Ctrl+C, q, Esc (sozinho)
                if key == '\x1b': 
                    # Verificar se é escape sequence ou tecla ESC mesmo
                    # Como getch lê 3 chars para setas, se vier só 1 é ESC
                    running = False 
                else:
                    running = False

            elif key == 'w': # Cima
                self.brightness = min(1.0, self.brightness + 0.05)
                await self.set_color()

            elif key == 's': # Baixo
                self.brightness = max(0.0, self.brightness - 0.05)
                await self.set_color()

            elif key == 'd': # Direita
                self.hue = (self.hue + 0.05) % 1.0
                await self.set_color()

            elif key == 'a': # Esquerda
                self.hue = (self.hue - 0.05) % 1.0
                await self.set_color()
            
            # Atalhos (1-9)
            elif key.isdigit() and key != '0':
                slot = key
                if slot in self.shortcuts:
                    data = self.shortcuts[slot]
                    self.hue = data['h']
                    self.saturation = data['s']
                    self.brightness = data['v']
                    print(f"\rCarregado slot {slot}      ", end="")
                    await self.set_color()
                else:
                    print(f"\rSlot {slot} vazio          ", end="")

            # Salvar
            elif key == 'x':
                print("\rPressione 1-9 para salvar... ", end="")
                next_key = await loop.run_in_executor(None, getch)
                if next_key.isdigit() and next_key != '0':
                    self.shortcuts[next_key] = {
                        'h': self.hue,
                        's': self.saturation,
                        'v': self.brightness
                    }
                    self.save_shortcuts()
                else:
                    print("\rCancelado.                 ")

        await self.led.stop()
        print("\nDesconectado.")

async def scan():
    print("Escaneando dispositivos BLE...")
    devices = await BleakScanner.discover()
    led_devices = []
    for d in devices:
        if d.name and d.name != "Unknown":
            led_devices.append(d)
    
    if not led_devices:
        print("Nenhum dispositivo com nome encontrado. Mostrando todos:")
        led_devices = devices

    if len(led_devices) == 1:
        print(f"Dispositivo único encontrado: {led_devices[0].name} ({led_devices[0].address})")
        return led_devices[0].address

    for i, dev in enumerate(led_devices):
        print(f"{i}: {dev.name} ({dev.address})")
    
    if not led_devices:
        return None

    try:
        idx = int(input("Selecione o número do dispositivo: "))
        return led_devices[idx].address
    except:
        return None

def check_update():
    """Checks for updates in background."""
    try:
        if not os.path.exists(os.path.join(SCRIPT_DIR, ".git")):
            return

        subprocess.run(
            ["git", "fetch"],
            cwd=SCRIPT_DIR,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        result = subprocess.run(
            ["git", "status", "-uno"],
            cwd=SCRIPT_DIR,
            check=True,
            capture_output=True,
            text=True
        )
        
        if "behind" in result.stdout:
            print("\n\033[93mAviso: Nova versão disponível! Execute ./update.sh\033[0m")
            
    except Exception:
        pass

async def main():
    # Iniciar check de update em thread para não bloquear
    threading.Thread(target=check_update, daemon=True).start()

    address = None
    if len(sys.argv) > 1:
        address = sys.argv[1]
    else:
        address = await scan()
    
    if not address:
        print("Endereço não fornecido ou inválido.")
        return

    controller = LEDController(address)
    await controller.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Erro: {e}")
