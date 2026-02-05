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

SAMPLE_RATE = 44100 
BLOCK_SIZE = 2048

# --- Paletas por Vibe ---
PALETTES_CHILL = [[0.5, 0.55, 0.6], [0.0, 0.05, 0.1], [0.25, 0.3, 0.35]] # Ocean, Fire, Forest
PALETTES_PARTY = [[0.8, 0.9, 0.0], [0.4, 0.5, 0.6], [0.1, 0.5, 0.9]]     # Neon, Cyber, Tropical
PALETTES_RAGE  = [[0.0, 0.02, 0.98], [0.0, 0.0, 0.0]]                    # Red/Dark

class VibeEngine:
    def __init__(self):
        self.onsets = []
        self.spectral_flux = 0.0
        self.current_vibe = "CHILL"
        self.last_switch = 0
    
    def analyze(self, indata, energy_ratio):
        # 1. Detecção de Onset (Ataque) simplificada
        now = time.time()
        if energy_ratio > 1.5: # Pico significativo
            # Limpa onsets antigos (> 5s)
            self.onsets = [t for t in self.onsets if now - t < 5.0]
            # Adiciona novo se não for duplicado (debounce 0.1s)
            if not self.onsets or (now - self.onsets[-1] > 0.1):
                self.onsets.append(now)
        
        # 2. Densidade (BPM feeling)
        density = len(self.onsets) / 5.0 # Ataques por segundo
        
        # 3. Decisão (Histerese de 10s para não ficar trocando loucamente)
        if now - self.last_switch > 10.0:
            new_vibe = self.current_vibe
            
            if density > 4.0: # Muito rápido -> RAGE
                new_vibe = "RAGE"
            elif density > 1.0: # Ritmo marcado -> PARTY
                new_vibe = "PARTY"
            else: # Calmo -> CHILL
                new_vibe = "CHILL"
            
            if new_vibe != self.current_vibe:
                print(f"\n🧠 Vibe Shift: {self.current_vibe} -> {new_vibe} (Dens: {density:.1f})")
                self.current_vibe = new_vibe
                self.last_switch = now
        
        return self.current_vibe

class AudioReactive:
    def __init__(self):
        self.led = None
        self.running = True
        self.vibe = VibeEngine()
        
        # Estado
        self.current_brightness = 0.0
        self.target_brightness = 0.0
        self.current_hue = 0.0
        self.target_hue = 0.0
        self.current_sat = 1.0
        self.target_sat = 1.0
        
        self.current_palette_idx = 0
        self.palette_timer = time.time()
        
        self.avg_bass = 10.0
        self.peak_hold = 0.0
        self.hue_stack = [] 
        
        self.last_flash_time = 0
        self.red_channel = 0.0
        self.is_kicking = False

    async def connect(self):
        print(f"🔍 Conectando a {DEVICE_ADDRESS}...")
        try:
            device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=5.0)
            if not device:
                await asyncio.sleep(20); return False
            self.led = LEDBLE(device)
            await self.led.update()
            await self.led.turn_on()
            print(f"✅ Conectado: {device.name}")
            return True
        except Exception:
            await asyncio.sleep(5); return False

    def get_color_from_vibe(self, intensity):
        # Seleciona paleta baseada na Vibe atual
        if self.vibe.current_vibe == "RAGE":
            palettes = PALETTES_RAGE
        elif self.vibe.current_vibe == "PARTY":
            palettes = PALETTES_PARTY
        else:
            palettes = PALETTES_CHILL
            
        palette = palettes[self.current_palette_idx % len(palettes)]
        if intensity < 0.33: return palette[0]
        elif intensity < 0.66: return palette[1]
        else: return palette[2]

    def audio_callback(self, indata, frames, time_info, status):
        if status: pass
        
        # FFT e Energia
        fft_data = np.abs(np.fft.rfft(indata[:, 0]))
        freqs = np.fft.rfftfreq(len(indata), 1/SAMPLE_RATE)
        
        mask_bass = (freqs > 40) & (freqs < 150)
        mask_mid  = (freqs > 200) & (freqs < 3000)
        e_bass = np.sum(fft_data[mask_bass]) if np.any(mask_bass) else 0
        
        self.avg_bass = (self.avg_bass * 0.99) + (e_bass * 0.01)
        bass_ratio = e_bass / max(self.avg_bass, 0.1)
        
        # --- VIBE ENGINE ANALYSE ---
        current_mode = self.vibe.analyze(indata, bass_ratio)
        
        # Configurar parâmetros baseado no modo
        if current_mode == "RAGE":
            smoothing = 0.1 # Rápido
            flash_enabled = True
            red_priority = True # Kick Vermelho
            pastel_mode = False
        elif current_mode == "PARTY":
            smoothing = 0.25 # Médio
            flash_enabled = False # Sem strobe agressivo
            red_priority = False
            pastel_mode = True # Cores lavadas no grave
        else: # CHILL
            smoothing = 0.5 # Lento
            flash_enabled = False
            red_priority = False
            pastel_mode = False # Cores puras

        # Lógica de Brilho
        if bass_ratio < 0.5:
            target_bri = 0.1 
            self.red_channel = 0.0
            self.target_sat = 1.0
        else:
            norm = (bass_ratio - 0.5) / 2.0 
            target_bri = 0.1 + (np.clip(norm, 0, 1.0) ** 2.0 * 0.9)
            
            # Efeitos por Modo
            if red_priority and target_bri > 0.4:
                self.red_channel = (target_bri - 0.4) * 2.0 
            else:
                self.red_channel = 0.0
                
            if pastel_mode:
                sat_drop = np.clip(norm * 0.7, 0.0, 0.7)
                self.target_sat = 1.0 - sat_drop
            else:
                self.target_sat = 1.0

        if target_bri > self.peak_hold:
            self.peak_hold = target_bri 
        else:
            self.peak_hold = max(self.peak_hold - 0.05, 0)
        self.target_brightness = max(target_bri, self.peak_hold)

        # Cor Base
        if self.target_brightness > 0.1 and np.any(mask_mid):
            valid_fft = fft_data[mask_mid]
            valid_freqs = freqs[mask_mid]
            centroid = np.sum(valid_freqs * valid_fft) / (np.sum(valid_fft) + 1e-6)
            harmonic_pos = np.clip((centroid - 200) / 2800, 0.0, 1.0)
            
            raw_hue = self.get_color_from_vibe(harmonic_pos)
            self.hue_stack.append(raw_hue)
            if len(self.hue_stack) > 20: self.hue_stack.pop(0)
            self.target_hue = sum(self.hue_stack) / len(self.hue_stack)

        if (time.time() - self.palette_timer > 60.0) and (self.target_brightness < 0.2):
            self.current_palette_idx += 1
            self.palette_timer = time.time()

        # Debug
        vibe_icon = "🔥" if current_mode == "RAGE" else "🎉" if current_mode == "PARTY" else "🧊"
        bar = '█' * int(self.target_brightness * 40)
        print(f"{vibe_icon} Bass:{e_bass:5.0f} Bri:{self.target_brightness:4.2f} |{bar:<40}|", end='\r')

    async def led_control_loop(self):
        print("💡 Loop Vibe Engine iniciado...")
        while self.running:
            if self.led:
                # Smoothing
                self.current_brightness = (self.current_brightness * 0.8) + (self.target_brightness * 0.2)
                
                # Cor
                diff = self.target_hue - self.current_hue
                if diff > 0.5: diff -= 1.0
                elif diff < -0.5: diff += 1.0
                self.current_hue = (self.current_hue + (diff * 0.02)) % 1.0 # Hue sempre suave
                
                self.current_sat = (self.current_sat * 0.8) + (self.target_sat * 0.2)

                r, g, b = colorsys.hsv_to_rgb(self.current_hue, self.current_sat, self.current_brightness)
                
                # Prioridade Vermelha (RAGE MODE)
                if self.vibe.current_vibe == "RAGE":
                    ducking = 1.0 - (self.red_channel * 0.8)
                    r = r * ducking + (self.red_channel * self.current_brightness)
                    g *= ducking
                    b *= ducking
                    
                    # Strobe
                    now = time.time()
                    if self.target_brightness > 0.95 and (now - self.last_flash_time) > 2.0:
                        r, g, b = 1.0, 1.0, 1.0
                        self.last_flash_time = now

                # Clip e Envio
                r, g, b = min(1.0, r), min(1.0, g), min(1.0, b)
                if self.current_brightness < 0.02: r, g, b = 0, 0, 0

                try:
                    await self.led.set_rgb((int(r*255), int(g*255), int(b*255)))
                except Exception: pass
            
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
