#!/usr/bin/env python3
import asyncio
import numpy as np
import sounddevice as sd
import colorsys
import time
import random
import socket
import os
import signal
import argparse
from bleak import BleakScanner, BleakClient

# --- Configurações ---
DEVICE_ADDRESS = "C5:50:EB:E3:E5:D0" 
DEVICE_NAME_FILTER = "Triones" 
AUDIO_DEVICE_ID = None 
SOCKET_PATH = "/tmp/silverblue_led.sock"

SAMPLE_RATE = 44100 
BLOCK_SIZE = 2048
MAX_BRIGHTNESS = 0.7 

# --- Paletas por Vibe ---
PALETTES_CHILL = [[0.5, 0.55, 0.6], [0.0, 0.05, 0.1], [0.25, 0.3, 0.35]]
PALETTES_PARTY = [[0.8, 0.9, 0.0], [0.4, 0.5, 0.6], [0.1, 0.5, 0.9]]
PALETTES_RAGE  = [[0.0, 0.02, 0.98], [0.0, 0.0, 0.0]]

class VibeEngine:
    def __init__(self):
        self.onsets = []
        self.current_vibe = "CHILL"
        self.last_switch = 0
    
    def analyze(self, indata, energy_ratio):
        now = time.time()
        if energy_ratio > 1.5:
            self.onsets = [t for t in self.onsets if now - t < 5.0]
            if not self.onsets or (now - self.onsets[-1] > 0.1): self.onsets.append(now)
        
        density = len(self.onsets) / 5.0
        
        if now - self.last_switch > 10.0:
            new_vibe = self.current_vibe
            if density > 4.0: new_vibe = "RAGE"
            elif density > 1.0: new_vibe = "PARTY"
            else: new_vibe = "CHILL"
            
            if new_vibe != self.current_vibe:
                print(f"\n🧠 Vibe Shift: {self.current_vibe} -> {new_vibe} (Dens: {density:.1f})")
                self.current_vibe = new_vibe
                self.last_switch = now
        return self.current_vibe

class LEDBLE:
    def __init__(self, device):
        self.device = device
        self.client = None

    async def connect(self):
        if self.client and self.client.is_connected: return
        self.client = BleakClient(self.device)
        await self.client.connect()

    async def disconnect(self):
        if self.client and self.client.is_connected:
            print("🔌 Desconectando LED para liberar recurso...")
            await self.client.disconnect()

    async def set_rgb(self, rgb):
        r, g, b = rgb
        packet = [0x56, r, g, b, 0x00, 0xF0, 0xAA]
        await self.send_bytes(packet)
    
    async def turn_on(self): await self.send_bytes([0xCC, 0x23, 0x33])

    async def send_bytes(self, data):
        if not self.client or not self.client.is_connected: await self.connect()
        try: await self.client.write_gatt_char("0000ffe9-0000-1000-8000-00805f9b34fb", bytearray(data), response=False)
        except: await self.connect(); await self.client.write_gatt_char("0000ffe9-0000-1000-8000-00805f9b34fb", bytearray(data), response=False)

class AudioReactive:
    def __init__(self):
        self.led = None
        self.running = True
        self.vibe = VibeEngine()
        
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
        
        self.override_mode = False

    async def connect(self):
        print(f"🔍 Conectando a {DEVICE_ADDRESS}...")
        try:
            # Tenta desconectar qualquer sessão zumbi anterior
            device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=5.0)
            if not device: await asyncio.sleep(20); return False
            self.led = LEDBLE(device)
            # Tenta um disconnect preventivo caso o objeto persista
            try: await self.led.disconnect()
            except: pass
            
            await asyncio.sleep(1.0) # Breve pausa para o hardware respirar
            
            try: await self.led.update()
            except: pass
            await self.led.turn_on()
            print(f"✅ Conectado: {device.name}")
            return True
        except: await asyncio.sleep(5); return False

    async def shutdown(self):
        print("\n🛑 Encerrando serviço...")
        self.running = False
        if self.led:
            try:
                # Apaga o LED antes de sair
                await self.led.set_rgb((0, 0, 0))
                await asyncio.sleep(0.1)
                await self.led.disconnect()
                print("🔌 Desconectado com sucesso.")
            except: pass
        
        if os.path.exists(SOCKET_PATH): os.remove(SOCKET_PATH)
        print("👋 Tchau!")
        asyncio.get_event_loop().stop()

    def get_color_from_vibe(self, intensity):
        if self.vibe.current_vibe == "RAGE": palettes = PALETTES_RAGE
        elif self.vibe.current_vibe == "PARTY": palettes = PALETTES_PARTY
        else: palettes = PALETTES_CHILL
        palette = palettes[self.current_palette_idx % len(palettes)]
        if intensity < 0.33: return palette[0]
        elif intensity < 0.66: return palette[1]
        else: return palette[2]

    def process_audio(self, indata):
        if self.override_mode: return

        fft_data = np.abs(np.fft.rfft(indata[:, 0]))
        freqs = np.fft.rfftfreq(len(indata), 1/SAMPLE_RATE)
        
        mask_bass = (freqs > 40) & (freqs < 150)
        mask_mid  = (freqs > 200) & (freqs < 3000)
        e_bass = np.sum(fft_data[mask_bass]) if np.any(mask_bass) else 0
        
        self.avg_bass = (self.avg_bass * 0.99) + (e_bass * 0.01)
        bass_ratio = e_bass / max(self.avg_bass, 0.1)
        
        current_mode = self.vibe.analyze(indata, bass_ratio)
        
        if current_mode == "RAGE":
            red_priority = True; pastel_mode = False
        elif current_mode == "PARTY":
            red_priority = False; pastel_mode = True
        else: 
            red_priority = False; pastel_mode = False

        if bass_ratio < 0.5:
            target_bri = 0.1 
            self.red_channel = 0.0
            self.target_sat = 1.0
        else:
            norm = (bass_ratio - 0.5) / 2.0 
            target_bri = 0.1 + (np.clip(norm, 0, 1.0) ** 2.0 * 0.9)
            if red_priority and target_bri > 0.4: self.red_channel = (target_bri - 0.4) * 2.0 
            else: self.red_channel = 0.0
            if pastel_mode:
                sat_drop = np.clip(norm * 0.7, 0.0, 0.7)
                self.target_sat = 1.0 - sat_drop
            else: self.target_sat = 1.0

        if target_bri > self.peak_hold: self.peak_hold = target_bri 
        else: self.peak_hold = max(self.peak_hold - 0.05, 0)
        
        # SCALING: Comprime 0-100% para 0-MAX_BRIGHTNESS
        # Isso mantém a dinâmica dos picos, apenas num volume menor
        scaled_brightness = min(max(target_bri, self.peak_hold), 1.0) * MAX_BRIGHTNESS
        self.target_brightness = scaled_brightness

        if self.target_brightness < (0.2 * MAX_BRIGHTNESS) and np.any(mask_mid):
             valid_fft = fft_data[mask_mid]; valid_freqs = freqs[mask_mid]
             centroid = np.sum(valid_freqs * valid_fft) / (np.sum(valid_fft) + 1e-6)
             harmonic_pos = np.clip((centroid - 200) / 2800, 0.0, 1.0)
             raw_hue = self.get_color_from_vibe(harmonic_pos)
             self.hue_stack.append(raw_hue)
             if len(self.hue_stack) > 20: self.hue_stack.pop(0)
             self.target_hue = sum(self.hue_stack) / len(self.hue_stack)

        if (time.time() - self.palette_timer > 60.0) and (self.target_brightness < 0.2):
            self.current_palette_idx += 1; self.palette_timer = time.time()

    def audio_callback(self, indata, frames, time_info, status):
        try: self.process_audio(indata)
        except: pass

    async def handle_ping(self, color_name):
        print(f"📩 PING: {color_name}")
        self.override_mode = True
        
        COLORS = {
            "green": (0, 255, 0), "red": (255, 0, 0), "blue": (0, 0, 255),
            "cyan": (0, 255, 255), "magenta": (255, 0, 255), "yellow": (255, 200, 0),
            "white": (255, 255, 255)
        }
        rgb = COLORS.get(color_name.strip().lower(), (0, 255, 0))
        
        if self.led:
            for _ in range(2):
                for i in range(0, 101, 20):
                    factor = i / 100.0
                    r, g, b = int(rgb[0]*factor), int(rgb[1]*factor), int(rgb[2]*factor)
                    await self.led.set_rgb((r, g, b))
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.4)
                for i in range(100, -1, -20):
                    factor = i / 100.0
                    r, g, b = int(rgb[0]*factor), int(rgb[1]*factor), int(rgb[2]*factor)
                    await self.led.set_rgb((r, g, b))
                    await asyncio.sleep(0.05)
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.5)
        
        self.override_mode = False

    async def led_control_loop(self):
        print("💡 Loop LED iniciado...")
        while self.running:
            if self.override_mode:
                await asyncio.sleep(0.05); continue

            if self.led:
                self.current_brightness = (self.current_brightness * 0.8) + (self.target_brightness * 0.2)
                
                diff = self.target_hue - self.current_hue
                if diff > 0.5: diff -= 1.0
                elif diff < -0.5: diff += 1.0
                self.current_hue = (self.current_hue + (diff * 0.02)) % 1.0 
                
                self.current_sat = (self.current_sat * 0.8) + (self.target_sat * 0.2)
                r, g, b = colorsys.hsv_to_rgb(self.current_hue, self.current_sat, self.current_brightness)
                
                if self.vibe.current_vibe == "RAGE":
                    ducking = 1.0 - (self.red_channel * 0.8)
                    r = r * ducking + (self.red_channel * self.current_brightness)
                    g *= ducking; b *= ducking
                
                r, g, b = min(1.0, r), min(1.0, g), min(1.0, b)
                if self.current_brightness < 0.02: r, g, b = 0, 0, 0

                try: await self.led.set_rgb((int(r*255), int(g*255), int(b*255)))
                except: pass
            
            await asyncio.sleep(0.05)
    
    async def server_loop(self):
        if os.path.exists(SOCKET_PATH): os.remove(SOCKET_PATH)
        server = await asyncio.start_unix_server(self.handle_client, SOCKET_PATH)
        print(f"👂 Socket server ativo: {SOCKET_PATH}")
        async with server: await server.serve_forever()

    async def handle_client(self, reader, writer):
        data = await reader.read(100)
        message = data.decode().strip()
        if message.startswith("PING"):
            parts = message.split(" ")
            color = parts[1] if len(parts) > 1 else "green"
            asyncio.create_task(self.handle_ping(color))
        writer.close()

    async def main(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.shutdown()))

        asyncio.create_task(self.server_loop()) 
        while self.running:
            if await self.connect():
                try:
                    target_id = None
                    devices = sd.query_devices()
                    for i, d in enumerate(devices):
                        if "Easy Effects Sink" in d['name']: target_id = i; break
                    if target_id is None: target_id = sd.default.device[0]
                    dev_info = sd.query_devices(target_id, 'input')
                    global SAMPLE_RATE; SAMPLE_RATE = int(dev_info['default_samplerate'])
                    print(f"✅ Audio: {dev_info['name']}")
                    
                    stream = sd.InputStream(callback=self.audio_callback, device=target_id, channels=1, blocksize=BLOCK_SIZE, samplerate=SAMPLE_RATE)
                    with stream: await self.led_control_loop()
                except Exception as e: print(f"❌ Erro Loop: {e}")
            
            if self.running:
                print("🔄 Reconectando...")
                await asyncio.sleep(5)

if __name__ == "__main__":
    app = AudioReactive()
    try: asyncio.run(app.main())
    except KeyboardInterrupt: pass
