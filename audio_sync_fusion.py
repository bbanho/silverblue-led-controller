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
SMOOTHING_HUE = 0.02 # Cor base lenta e pacífica

# Paletas (Tríades para o "Tapete Harmônico")
PALETTES = [
    [0.0, 0.33, 0.66], 
    [0.55, 0.6, 0.65], 
    [0.0, 0.05, 0.1],  
    [0.75, 0.8, 0.9],  
    [0.25, 0.35, 0.4], 
    [0.1, 0.6, 0.8],   
]

SAMPLE_RATE = 44100 
BLOCK_SIZE = 2048

class AudioReactive:
    def __init__(self):
        self.led = None
        self.running = True
        
        self.current_brightness = 0.0
        self.target_brightness = 0.0
        self.current_hue = 0.0
        self.target_hue = 0.0
        self.current_palette_idx = 0
        self.palette_timer = time.time()
        self.palette_duration = 60.0
        
        # Dinâmica
        self.avg_bass = 5.0
        self.peak_hold = 0.0
        self.peak_decay = 0.05
        self.hue_stack = [] 
        
        # Injeção de Vermelho (Kick)
        self.red_injection = 0.0

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
        palette = PALETTES[self.current_palette_idx]
        if intensity < 0.33: return palette[0]
        elif intensity < 0.66: return palette[1]
        else: return palette[2]

    def audio_callback(self, indata, frames, time_info, status):
        if status: pass
        
        fft_data = np.abs(np.fft.rfft(indata[:, 0]))
        freqs = np.fft.rfftfreq(len(indata), 1/SAMPLE_RATE)
        
        mask_bass = (freqs > 40) & (freqs < 150)
        mask_mid  = (freqs > 200) & (freqs < 3000)
        
        e_bass = np.sum(fft_data[mask_bass]) if np.any(mask_bass) else 0
        
        # --- 1. Brilho Baseado no Grave (Energia) ---
        self.avg_bass = (self.avg_bass * 0.99) + (e_bass * 0.01)
        bass_ratio = e_bass / max(self.avg_bass, 0.1)
        
        if bass_ratio < 0.5: 
            target_bri = 0.1 # Floor de 10%
            self.red_injection = 0.0
        else:
            norm = (bass_ratio - 0.5) / 2.0 
            target_bri = 0.1 + (np.clip(norm, 0, 1.0) ** 2.0 * 0.9)
            
            # Se o grave for muito forte (>1.5x média), injeta vermelho
            if bass_ratio > 1.5:
                self.red_injection = np.clip((bass_ratio - 1.5), 0, 1.0)
            else:
                self.red_injection = 0.0

        if target_bri > self.peak_hold:
            self.peak_hold = target_bri 
        else:
            self.peak_hold = max(self.peak_hold - self.peak_decay, 0)
        self.target_brightness = max(target_bri, self.peak_hold)

        # --- 2. Cor Baseada na Harmonia (Paz) ---
        if self.target_brightness > 0.1 and np.any(mask_mid):
            valid_fft = fft_data[mask_mid]
            valid_freqs = freqs[mask_mid]
            centroid = np.sum(valid_freqs * valid_fft) / (np.sum(valid_fft) + 1e-6)
            harmonic_pos = np.clip((centroid - 200) / 2800, 0.0, 1.0)
            
            raw_hue = self.get_target_color_from_palette(harmonic_pos)
            self.hue_stack.append(raw_hue)
            if len(self.hue_stack) > 20: self.hue_stack.pop(0)
            self.target_hue = sum(self.hue_stack) / len(self.hue_stack)

        if (time.time() - self.palette_timer > self.palette_duration) and (self.target_brightness < 0.2):
            self.current_palette_idx = (self.current_palette_idx + 1) % len(PALETTES)
            self.palette_timer = time.time()
            print(f"\n🎨 Nova Paleta: {self.current_palette_idx}")

        bar = '█' * int(self.target_brightness * 40)
        print(f"Bass:{e_bass:5.0f} Bri:{self.target_brightness:4.2f} RedInj:{self.red_injection:4.2f} |{bar:<40}|", end='\r')

    async def led_control_loop(self):
        print("💡 Loop Fusão (Paz + Kick) Restaurado...")
        while self.running:
            if self.led:
                # Brilho
                self.current_brightness = (self.current_brightness * SMOOTHING_BRI) + \
                                        (self.target_brightness * (1 - SMOOTHING_BRI))
                
                # Cor Base (Harmônica)
                diff = self.target_hue - self.current_hue
                if diff > 0.5: diff -= 1.0
                elif diff < -0.5: diff += 1.0
                self.current_hue = (self.current_hue + (diff * SMOOTHING_HUE)) % 1.0

                # Converter Hue Base para RGB
                r_base, g_base, b_base = colorsys.hsv_to_rgb(self.current_hue, 1.0, self.current_brightness)
                
                # --- Mesclagem com Injeção de Vermelho ---
                r_final = min(1.0, r_base + (self.red_injection * 0.8))
                g_final = g_base 
                b_final = b_base 

                if self.current_brightness < 0.02:
                    r_final, g_final, b_final = 0, 0, 0

                try:
                    await self.led.set_rgb((int(r_final*255), int(g_final*255), int(b_final*255)))
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
