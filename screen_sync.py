#!/usr/bin/env python3
import asyncio
import subprocess
import io
import time
from PIL import Image
from bleak import BleakScanner
from led_ble import LEDBLE

# Configurações
DEVICE_ADDRESS = "C5:50:EB:E3:E5:D0" 
SCALE_FACTOR = 0.1 # Reduz resolução para processar rápido
SMOOTHING = 0.3 # Suavização da cor (0.0 a 1.0)

class ScreenSync:
    def __init__(self):
        self.led = None
        self.running = True
        self.current_r = 0.0
        self.current_g = 0.0
        self.current_b = 0.0

    async def connect(self):
        print(f"🔍 Conectando a {DEVICE_ADDRESS}...")
        try:
            device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=5.0)
            if not device:
                print("❌ Dispositivo não encontrado. Aguardando...")
                await asyncio.sleep(5)
                return False
            self.led = LEDBLE(device)
            await self.led.update()
            await self.led.turn_on()
            print(f"✅ Conectado: {device.name}")
            return True
        except Exception as e:
            print(f"❌ Erro conexão: {e}")
            await asyncio.sleep(5)
            return False

    def get_screen_color(self):
        try:
            # Captura com grim, saída PNG no stdout
            # Reduz resolução logo na captura se possível? Grim não faz scale.
            # Vamos capturar e o Pillow redimensiona.
            
            # grim -t jpeg -q 50 - | ... (JPEG é mais rápido que PNG para comprimir?)
            # PNG é raw pixel data, talvez PPM seja mais rápido.
            # Vamos de JPEG qualidade baixa.
            
            proc = subprocess.run(['grim', '-t', 'jpeg', '-q', '20', '-'], 
                                  capture_output=True, check=True)
            
            img_data = io.BytesIO(proc.stdout)
            img = Image.open(img_data)
            
            # Redimensiona para 1x1 pixel usando resample (média)
            img_small = img.resize((1, 1), resample=Image.Resampling.BOX)
            color = img_small.getpixel((0, 0))
            
            return color # (R, G, B)
            
        except Exception as e:
            print(f"Erro captura: {e}")
            return (0, 0, 0)

    async def loop(self):
        print("🖥️ Iniciando sincronização de tela (Grim)...")
        while self.running:
            if not self.led:
                if not await self.connect():
                    continue

            start_time = time.time()
            
            # 1. Capturar Cor
            # Executar em thread separada para não bloquear o loop async?
            # Como é CPU bound, sim.
            r, g, b = await asyncio.to_thread(self.get_screen_color)
            
            # 2. Suavização
            self.current_r = (self.current_r * SMOOTHING) + (r * (1 - SMOOTHING))
            self.current_g = (self.current_g * SMOOTHING) + (g * (1 - SMOOTHING))
            self.current_b = (self.current_b * SMOOTHING) + (b * (1 - SMOOTHING))
            
            # 3. Enviar
            try:
                # Boost de saturação/brilho opcional?
                # Se for muito escuro, apaga
                if (self.current_r + self.current_g + self.current_b) < 30:
                    tr, tg, tb = 0, 0, 0
                else:
                    tr, tg, tb = int(self.current_r), int(self.current_g), int(self.current_b)
                
                await self.led.set_rgb((tr, tg, tb))
                
                # Debug
                print(f"Cor: {tr:3} {tg:3} {tb:3} \x1b[48;2;{tr};{tg};{tb}m   \x1b[0m", end='\r')
                
            except Exception as e:
                print(f"Erro BLE: {e}")
                self.led = None # Força reconexão
            
            # Limitar FPS (Grim consome CPU)
            # 10 FPS é suficiente para ambilight ambiente
            elapsed = time.time() - start_time
            sleep_time = max(0.1 - elapsed, 0.01)
            await asyncio.sleep(sleep_time)

if __name__ == "__main__":
    app = ScreenSync()
    try:
        asyncio.run(app.loop())
    except KeyboardInterrupt:
        print("\n👋 Parando...")
