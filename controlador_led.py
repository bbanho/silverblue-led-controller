#!/usr/bin/env python3
import asyncio
import sys
import tty
import termios
import json
import os
import subprocess
import threading
from bleak import BleakScanner
from led_ble import LEDBLE

# Cores para o terminal
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

# Determinar o diretório onde o script está localizado
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuração para salvar em diretório de usuário (XDG_CONFIG_HOME ou ~/.config)
CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
APP_CONFIG_DIR = os.path.join(CONFIG_DIR, "controlador-led")
os.makedirs(APP_CONFIG_DIR, exist_ok=True)
SHORTCUTS_FILE = os.path.join(APP_CONFIG_DIR, "atalhos_led_rgb.json")

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
        # Estado RGB (0-255)
        self.r = 255
        self.g = 255
        self.b = 255

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
        device = await BleakScanner.find_device_by_address(self.address)
        if not device:
            raise Exception(f"Dispositivo {self.address} não encontrado.")
        
        self.led = LEDBLE(device)
        
        try:
            await self.led.update()
            await self.led.turn_on()
        except IndexError:
             print("\rAviso: Resposta incompleta do LED (IndexError). Ignorando...")
        except Exception as e:
             print(f"\rAviso ao conectar: {e}")

        # Sincronizar estado local
        if self.led.rgb:
            self.r, self.g, self.b = self.led.rgb
        
        print(f"{Colors.GREEN}Conectado!{Colors.ENDC} Ligando LED...")
        
        print(f"\n{Colors.BOLD}=== CONTROLE RGB (RT GH BN) ==={Colors.ENDC}")
        print(f"{Colors.RED}R / T{Colors.ENDC}: Vermelho +/-")
        print(f"{Colors.GREEN}G / H{Colors.ENDC}: Verde    +/-")
        print(f"{Colors.BLUE}B / N{Colors.ENDC}: Azul     +/-")
        print(f"{Colors.BOLD}1-9{Colors.ENDC}: Carregar atalho")
        print(f"{Colors.YELLOW}X{Colors.ENDC} depois numero: Salvar atalho")
        print(f"{Colors.BOLD}Q / ESC{Colors.ENDC}: Sair")
        print("===========================")

    async def set_color(self):
        # Garantir limites
        self.r = max(0, min(255, self.r))
        self.g = max(0, min(255, self.g))
        self.b = max(0, min(255, self.b))
        
        rgb = (self.r, self.g, self.b)
        
        # UI colorida
        print(f"\rRGB: ({Colors.RED}{self.r:3}{Colors.ENDC}, {Colors.GREEN}{self.g:3}{Colors.ENDC}, {Colors.BLUE}{self.b:3}{Colors.ENDC})      ", end="", flush=True)
        
        try:
            await self.led.set_rgb(rgb)
        except Exception:
            pass

    async def run(self):
        await self.connect()
        getch = Getch()
        loop = asyncio.get_running_loop()

        running = True
        step = 15 # Passo do ajuste RGB

        while running:
            key = await loop.run_in_executor(None, getch)

            if key in ('\x03', 'q', '\x1b'): # Ctrl+C, q, Esc
                running = False

            # Vermelho (R/T)
            elif key == 'r':
                self.r += step
                await self.set_color()
            elif key == 't':
                self.r -= step
                await self.set_color()

            # Verde (G/H)
            elif key == 'g':
                self.g += step
                await self.set_color()
            elif key == 'h':
                self.g -= step
                await self.set_color()

            # Azul (B/N)
            elif key == 'b':
                self.b += step
                await self.set_color()
            elif key == 'n':
                self.b -= step
                await self.set_color()
            
            # Atalhos (1-9)
            elif key.isdigit() and key != '0':
                slot = key
                if slot in self.shortcuts:
                    data = self.shortcuts[slot]
                    self.r = data['r']
                    self.g = data['g']
                    self.b = data['b']
                    print(f"\rCarregado slot {slot}      ", end="")
                    await self.set_color()
                else:
                    print(f"\rSlot {slot} vazio          ", end="")

            # Salvar
            elif key == 'x':
                print(f"\r{Colors.YELLOW}Pressione 1-9 para salvar... {Colors.ENDC}", end="")
                next_key = await loop.run_in_executor(None, getch)
                if next_key.isdigit() and next_key != '0':
                    self.shortcuts[next_key] = {
                        'r': self.r,
                        'g': self.g,
                        'b': self.b
                    }
                    self.save_shortcuts()
                else:
                    print("\rCancelado.                 ")

        if self.led:
            await self.led.stop()
        print("\nDesconectado.")

async def scan():
    print(f"{Colors.CYAN}Escaneando dispositivos BLE...{Colors.ENDC}")
    devices = await BleakScanner.discover()
    led_devices = [d for d in devices if d.name and d.name != "Unknown"]
    
    if not led_devices:
        led_devices = devices

    if len(led_devices) == 1:
        print(f"Dispositivo único encontrado: {Colors.BOLD}{led_devices[0].name}{Colors.ENDC} ({led_devices[0].address})")
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
    try:
        if not os.path.exists(os.path.join(SCRIPT_DIR, ".git")):
            return
        subprocess.run(["git", "fetch"], cwd=SCRIPT_DIR, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = subprocess.run(["git", "status", "-uno"], cwd=SCRIPT_DIR, check=True, capture_output=True, text=True)
        if "behind" in result.stdout:
            print(f"\n{Colors.YELLOW}Aviso: Nova versão disponível! Execute ./update.sh{Colors.ENDC}")
    except Exception:
        pass

async def main():
    threading.Thread(target=check_update, daemon=True).start()
    address = sys.argv[1] if len(sys.argv) > 1 else await scan()
    if not address:
        print("Endereço inválido.")
        return
    controller = LEDController(address)
    await controller.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Erro: {e}")