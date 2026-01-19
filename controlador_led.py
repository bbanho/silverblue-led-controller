#!/usr/bin/env python3
import asyncio
import sys
import tty
import termios
import json
import colorsys
import os
from bleak import BleakScanner
from led_ble import LEDBLE

# Determinar o diretório onde o script está localizado para salvar o arquivo de atalhos lá
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHORTCUTS_FILE = os.path.join(SCRIPT_DIR, "atalhos_led.json")

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
        await self.led.update()
        print("Conectado! Ligando LED...")
        await self.led.turn_on()
        
        # Sincronizar estado local
        r, g, b = self.led.rgb
        h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
        self.hue = h
        self.saturation = s
        # A biblioteca retorna brilho separado às vezes, mas vamos usar V do HSV
        self.brightness = max(v, 0.1) # Evitar 0 absoluto para não perder a cor ao aumentar
        
        print("\n=== CONTROLE ===")
        print("Setas E/D: Mudar Cor (Hue)")
        print("Setas C/B: Mudar Brilho")
        print("Teclas 1-9: Carregar atalho")
        print("Shift + 1-9 (Ex: ! ou @): Salvar atalho no slot")
        print("Q ou ESC: Sair")
        print("===============")

    async def set_color(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.saturation, self.brightness)
        rgb = (int(r * 255), int(g * 255), int(b * 255))
        # print(f"\rRGB: {rgb} Brilho: {self.brightness:.2f}   ", end="", flush=True)
        await self.led.set_rgb(rgb)

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

            elif key == '\x1b[A': # Cima
                self.brightness = min(1.0, self.brightness + 0.05)
                await self.set_color()

            elif key == '\x1b[B': # Baixo
                self.brightness = max(0.0, self.brightness - 0.05)
                await self.set_color()

            elif key == '\x1b[C': # Direita
                self.hue = (self.hue + 0.02) % 1.0
                await self.set_color()

            elif key == '\x1b[D': # Esquerda
                self.hue = (self.hue - 0.02) % 1.0
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

            # Salvar (Simulado detectando caracteres especiais de Shift+Num)
            # Mapeamento PT-BR/US básico para !@#$%... 
            # Simplificação: Usar 's' depois numero para salvar
            elif key == 's':
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
        # Filtro básico por nomes comuns de fitas LED genéricas se quiser, 
        # mas melhor mostrar todos com sinal forte ou que tenham nome
        if d.name and d.name != "Unknown":
            led_devices.append(d)
    
    if not led_devices:
        print("Nenhum dispositivo com nome encontrado. Mostrando todos:")
        led_devices = devices

    for i, dev in enumerate(led_devices):
        print(f"{i}: {dev.name} ({dev.address})")
    
    if not led_devices:
        return None

    try:
        idx = int(input("Selecione o número do dispositivo: "))
        return led_devices[idx].address
    except:
        return None

async def main():
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
        print(f"Erro: {e}")
