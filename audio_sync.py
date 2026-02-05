#!/usr/bin/env python3
import asyncio
import numpy as np
import sounddevice as sd
import colorsys
import time
import random
from bleak import BleakScanner
from led_ble import LEDBLE

# --- Configurações ---
DEVICE_ADDRESS = "C5:50:EB:E3:E5:D0" 
DEVICE_NAME_FILTER = "Triones" 
AUDIO_DEVICE_ID = None 
SMOOTHING_BRI = 0.2  
SMOOTHING_HUE = 0.1 

# Paletas (Tríades de Hue 0.0-1.0)
PALETTES = [
    [0.0, 0.33, 0.66], # RGB Clássico
    [0.55, 0.6, 0.65], # Ocean (Azul/Ciano)
    [0.0, 0.05, 0.1],  # Fire (Vermelho/Laranja/Ouro)
    [0.75, 0.8, 0.9],  # Cyberpunk (Roxo/Magenta/Rosa)
    [0.25, 0.35, 0.4], # Forest (Verde/Lima/Esmeralda)
    [0.1, 0.6, 0.8],   # Tropical (Laranja/Azul/Roxo)
]

# Configuração FFT
SAMPLE_RATE = 44100 
BLOCK_SIZE = 2048

class AudioReactive:
    def __init__(self):
        self.led = None
        self.running = True
        
        # Estado
        self.current_brightness = 0.0
        self.target_brightness = 0.0
        self.current_hue = 0.0
        self.target_hue = 0.0
        
        # Paleta
        self.current_palette_idx = 0
        self.palette_timer = time.time()
        self.palette_duration = 60.0 # Troca a cada 60s
        
        # Dinâmica
        self.avg_volume = 10.0  
        self.peak_hold = 0.0
        self.peak_decay = 0.05
        self.last_spectral_centroid = 0

    async def connect(self):
        print(f"🔍 Conectando a {DEVICE_ADDRESS}...")
        try:
            device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=5.0)
            if not device:
                print("❌ Dispositivo não encontrado. Aguardando 20s...")
                await asyncio.sleep(20)
                return False
            self.led = LEDBLE(device)
            await self.led.update()
            await self.led.turn_on()
            print(f"✅ Conectado: {device.name}")
            return True
        except Exception:
            await asyncio.sleep(5)
            return False

    def get_target_color_from_palette(self, intensity):
        # intensity: 0.0 a 1.0 (onde na música estamos harmônicamente?)
        # Mapeia intensity para uma das 3 cores da paleta atual
        palette = PALETTES[self.current_palette_idx]
        
        if intensity < 0.33:
            return palette[0]
        elif intensity < 0.66:
            return palette[1]
        else:
            return palette[2]

    def audio_callback(self, indata, frames, time_info, status):
        if status: pass
        
        # --- 1. Energia (Brilho) ---
        raw_vol = np.linalg.norm(indata) * 10
        self.avg_volume = (self.avg_volume * 0.995) + (raw_vol * 0.005)
        ratio = raw_vol / max(self.avg_volume, 0.1)
        
        if ratio < 0.2: 
            target_bri = 0.0
        else:
            norm = (ratio - 0.5) / 1.5 
            target_bri = np.clip(norm, 0, 1.0) ** 1.8

        if target_bri > self.peak_hold:
            self.peak_hold = target_bri 
        else:
            self.peak_hold = max(self.peak_hold - self.peak_decay, 0)
        self.target_brightness = max(target_bri, self.peak_hold)

        # --- 2. Harmonia & Paleta ---
        # Troca de paleta se passou tempo E está "escuro" (transição suave)
        if (time.time() - self.palette_timer > self.palette_duration) and (self.target_brightness < 0.1):
            self.current_palette_idx = (self.current_palette_idx + 1) % len(PALETTES)
            self.palette_timer = time.time()
            print(f"\n🎨 Nova Paleta: {self.current_palette_idx}")

        if self.target_brightness > 0.1:
            fft_data = np.abs(np.fft.rfft(indata[:, 0]))
            freqs = np.fft.rfftfreq(len(indata), 1/SAMPLE_RATE)
            mask = (freqs > 200) & (freqs < 2000)
            
            harmonic_pos = 0.5 # Padrão meio
            
            if np.any(mask):
                valid_fft = fft_data[mask]
                valid_freqs = freqs[mask]
                centroid = np.sum(valid_freqs * valid_fft) / (np.sum(valid_fft) + 1e-6)
                
                # Normaliza centroide (200-2000Hz) para 0.0-1.0
                harmonic_pos = np.clip((centroid - 200) / 1800, 0.0, 1.0)
            
            # Escolhe cor da paleta baseada na posição harmônica (Grave/Médio/Agudo relativo)
            self.target_hue = self.get_target_color_from_palette(harmonic_pos)

        # Debug
        bar = '█' * int(self.target_brightness * 40)
        print(f"Vol:{raw_vol:5.2f} Bri:{self.target_brightness:4.2f} P:{self.current_palette_idx} |{bar:<40}|", end='\r')

    async def led_control_loop(self):
        print("💡 Loop Palette iniciado...")
        while self.running:
            if self.led:
                # Brilho
                self.current_brightness = (self.current_brightness * SMOOTHING_BRI) + \
                                        (self.target_brightness * (1 - SMOOTHING_BRI))
                
                # Cor (Lerp circular)
                diff = self.target_hue - self.current_hue
                if diff > 0.5: diff -= 1.0
                elif diff < -0.5: diff += 1.0
                self.current_hue = (self.current_hue + (diff * SMOOTHING_HUE)) % 1.0

                if self.current_brightness < 0.02:
                    v = 0
                else:
                    v = self.current_brightness

                r, g, b = colorsys.hsv_to_rgb(self.current_hue, 1.0, v)
                
                try:
                    await self.led.set_rgb((int(r*255), int(g*255), int(b*255)))
                except Exception:
                    pass
            
            await asyncio.sleep(0.05)

    async def main(self):
        while True:
            if await self.connect():
                try:
                    devices = sd.query_devices()
                    target_id = None
                    global SAMPLE_RATE
                    
                    for idx, dev in enumerate(devices):
                        if "Easy Effects Sink" in dev['name'] and dev['max_input_channels'] > 0:
                            target_id = idx; break
                        if "Ryzen" in dev['name'] and "monitor" in dev['name'].lower():
                            target_id = idx; break

                    if target_id is None: target_id = sd.default.device[0]
                    
                    dev_info = sd.query_devices(target_id, 'input')
                    SAMPLE_RATE = dev_info['default_samplerate']
                    print(f"✅ Audio: {dev_info['name']}")

                    stream = sd.InputStream(
                        callback=self.audio_callback,
                        device=target_id,
                        channels=1, 
                        blocksize=BLOCK_SIZE,
                        samplerate=SAMPLE_RATE
                    )
                    stream.start()
                    await self.led_control_loop()
                    
                except Exception as e:
                    print(f"❌ Erro Loop: {e}")
                finally:
                    if 'stream' in locals(): stream.stop(); stream.close()
            
            print("🔄 Reconectando...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    app = AudioReactive()
    try:
        asyncio.run(app.main())
    except KeyboardInterrupt:
        print("\n👋 Parando...")
