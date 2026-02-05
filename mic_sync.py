#!/usr/bin/env python3
import asyncio
import numpy as np
import sounddevice as sd
import colorsys
import time
from bleak import BleakScanner
from led_ble import LEDBLE

# --- Configurações ---
DEVICE_ADDRESS = "C5:50:EB:E3:E5:D0" 
DEVICE_NAME_FILTER = "Triones" 
AUDIO_DEVICE_ID = None 
MIN_VOL = 15.0  # Ajustado: O piso de ruído da máquina está em ~12.0
MAX_VOL = 40.0  # Ajustado proporcionalmente
SMOOTHING = 0.3 

# Cor Base (Hue: 0-1.0)
BASE_HUE = 0.08 
SATURATION = 1.0

class AudioReactive:
    def __init__(self):
        self.led = None
        self.running = True
        self.current_brightness = 0.0
        self.target_brightness = 0.0

    async def connect(self):
        print(f"🔍 Conectando a {DEVICE_ADDRESS}...")
        try:
            device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=5.0)
            if not device:
                print("❌ Dispositivo não encontrado.")
                print("⚠️  POR FAVOR, REINICIE A LÂMPADA (TOMADA). Aguardando 20s...")
                await asyncio.sleep(20)
                return False
                
            print(f"✅ Encontrado: {device.name}")
            self.led = LEDBLE(device)
            await self.led.update()
            await self.led.turn_on()
            return True
        except Exception as e:
            print(f"❌ Erro conexão: {e}")
            print("⚠️  Aguardando 20s para retry...")
            await asyncio.sleep(20)
            return False

    def audio_callback(self, indata, frames, time_info, status):
        if status:
            print(f"⚠️ Status: {status}")
        
        # Calcular volume (RMS)
        volume = np.linalg.norm(indata) * 10
        
        # Mapear para 0.0 - 1.0
        if volume < MIN_VOL:
            raw_val = 0.0
        else:
            raw_val = np.clip((volume - MIN_VOL) / (MAX_VOL - MIN_VOL), 0, 1)
        
        # Aplicar curva gama 
        self.target_brightness = raw_val ** 2.0

        # Debug Visual
        bar_len = int(self.target_brightness * 40)
        bar = '█' * bar_len
        print(f"Vol: {volume:5.2f} Brilho: {self.target_brightness:4.2f} |{bar:<40}|", end='\r')

    async def led_control_loop(self):
        print("💡 Loop reativo iniciado...")
        while self.running:
            if self.led:
                # Se o alvo for zero (silêncio), corta imediatamente (Fast Decay)
                if self.target_brightness < 0.01:
                    self.current_brightness = 0.0
                else:
                    # Suavização normal 
                    self.current_brightness = (self.current_brightness * SMOOTHING) + \
                                            (self.target_brightness * (1 - SMOOTHING))
                
                # Converter HSV -> RGB
                if self.current_brightness < 0.01:
                    v = 0
                else:
                    v = self.current_brightness

                r, g, b = colorsys.hsv_to_rgb(BASE_HUE, SATURATION, v)
                
                try:
                    await self.led.set_rgb((int(r*255), int(g*255), int(b*255)))
                except Exception as e:
                    pass
            
            await asyncio.sleep(0.05)

    async def main(self):
        while True:
            if await self.connect():
                try:
                    devices = sd.query_devices()
                    target_id = None
                    for idx, dev in enumerate(devices):
                        if "Easy Effects Source" in dev['name']:
                            target_id = idx
                            print(f"✅ Audio: {dev['name']} (ID: {idx})")
                            break
                    
                    if target_id is None:
                        target_id = sd.default.device[0]
                        print(f"⚠️ Usando dispositivo padrão ID {target_id}")

                    stream = sd.InputStream(
                        callback=self.audio_callback,
                        device=target_id,
                        channels=1, 
                        blocksize=2048
                    )
                    stream.start()
                    
                    await self.led_control_loop()
                    
                except Exception as e:
                    print(f"❌ Erro Fatal no Loop: {e}")
                finally:
                    if 'stream' in locals():
                        stream.stop()
                        stream.close()
            
            print("🔄 Tentando reconectar em 5s...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    app = AudioReactive()
    try:
        asyncio.run(app.main())
    except KeyboardInterrupt:
        print("\n👋 Parando...")
