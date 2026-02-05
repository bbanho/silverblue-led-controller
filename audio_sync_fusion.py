#!/usr/bin/env python3
import asyncio
import numpy as np
import sounddevice as sd
import colorsys
import time
from bleak import BleakScanner, BleakClient

# --- Configurações ---
DEVICE_ADDRESS = "C5:50:EB:E3:E5:D0"
CHARACTERISTIC_UUID = "0000ffe9-0000-1000-8000-00805f9b34fb"

# Ajustes Finos
SENSITIVITY = 1.2
DECAY_RATE = 0.15 # Quão rápido a luz "apaga" (Fade adequado)
VOCAL_SHIMMER_AMOUNT = 0.4 # Quanto a voz "brilha"

SAMPLE_RATE = 44100 
BLOCK_SIZE = 2048

class LEDBLE:
    def __init__(self, device):
        self.device = device
        self.client = None

    async def connect(self):
        if self.client and self.client.is_connected: return
        self.client = BleakClient(self.device)
        await self.client.connect()

    async def set_rgb(self, rgb):
        r, g, b = rgb
        packet = [0x56, r, g, b, 0x00, 0xF0, 0xAA]
        await self.send_bytes(packet)
    
    async def turn_on(self): await self.send_bytes([0xCC, 0x23, 0x33])

    async def send_bytes(self, data):
        if not self.client or not self.client.is_connected: await self.connect()
        try: await self.client.write_gatt_char(CHARACTERISTIC_UUID, bytearray(data), response=False)
        except: await self.connect(); await self.client.write_gatt_char(CHARACTERISTIC_UUID, bytearray(data), response=False)

class SpectralComposer:
    def __init__(self):
        self.led = None
        self.running = True
        
        # Estado de Energia (Envelopes)
        self.env_bass = 0.0
        self.env_mid = 0.0
        self.env_high = 0.0
        
        # Estado Harmônico
        self.current_hue = 0.6 # Começa no Azul
        self.target_hue = 0.6
        self.harmonic_stability = 0.0
        
        # Strobo
        self.chaos_counter = 0
        self.last_strobe = 0
        self.strobe_active = False

    async def connect(self):
        print(f"🔍 Conectando a {DEVICE_ADDRESS}...")
        try:
            device = await BleakScanner.find_device_by_address(DEVICE_ADDRESS, timeout=5.0)
            if not device: return False
            self.led = LEDBLE(device)
            await self.led.turn_on()
            print(f"✅ Conectado: {device.name}")
            return True
        except: return False

    def process_audio(self, indata):
        # FFT
        fft = np.abs(np.fft.rfft(indata[:, 0]))
        freqs = np.fft.rfftfreq(len(indata), 1/SAMPLE_RATE)
        
        # 1. Separar Bandas
        mask_bass = (freqs > 40) & (freqs < 100)
        mask_mid  = (freqs > 200) & (freqs < 2000) # Voz / Harmonia
        mask_high = (freqs > 2500) & (freqs < 6000) # Articulação / Shimmer
        
        e_bass = np.sum(fft[mask_bass]) if np.any(mask_bass) else 0
        e_mid  = np.sum(fft[mask_mid]) if np.any(mask_mid) else 0
        e_high = np.sum(fft[mask_high]) if np.any(mask_high) else 0
        
        # Normalização Dinâmica (AGC simplificado)
        e_bass = np.clip(e_bass / 10.0, 0, 1.0) * SENSITIVITY
        e_mid  = np.clip(e_mid / 8.0, 0, 1.0) * SENSITIVITY
        e_high = np.clip(e_high / 5.0, 0, 1.0) * SENSITIVITY

        # 2. Envelopes (Fade Adequado)
        # Ataque rápido, Decay suave
        self.env_bass = max(e_bass, self.env_bass - DECAY_RATE)
        self.env_mid  = max(e_mid,  self.env_mid  - DECAY_RATE)
        self.env_high = max(e_high, self.env_high - (DECAY_RATE * 2)) # Decay rápido para detalhe

        # 3. Análise Harmônica (Centróide)
        if np.any(mask_mid) and e_mid > 0.1:
            # Onde está o peso da nota?
            centroid = np.sum(freqs[mask_mid] * fft[mask_mid]) / np.sum(fft[mask_mid])
            
            # Mapeamento de Frequência -> Cor (Círculo de Quintas visual)
            # 200Hz (Grave) -> 0.6 (Azul)
            # 1000Hz (Agudo) -> 0.1 (Laranja/Amarelo)
            # Oitava acima = Hue shift
            norm_freq = np.clip((centroid - 200) / 1500, 0.0, 1.0)
            
            # Se for grave/fechado = Cores frias (Azul/Roxo)
            # Se for agudo/aberto = Cores quentes (Laranja/Rosa)
            # Invertendo lógica para dar sentido: Voz aguda = Mais "Luz"
            raw_hue = 0.65 - (norm_freq * 0.6) 
            if raw_hue < 0: raw_hue += 1.0
            
            # Inércia Harmônica (Evita piscar cor loucamente, segue o tom)
            self.target_hue = raw_hue

        # 4. Detecção de Clímax (Strobo)
        total_energy = self.env_bass + self.env_mid
        if total_energy > 2.5: # Clímax absurdo
            self.chaos_counter += 1
        else:
            self.chaos_counter = max(0, self.chaos_counter - 1)
            
        if self.chaos_counter > 5 and (time.time() - self.last_strobe > 5.0):
            self.strobe_active = True
            self.last_strobe = time.time()
            self.chaos_counter = 0

    def audio_callback(self, indata, frames, time_info, status):
        try: self.process_audio(indata)
        except: pass

    async def led_loop(self):
        print("💡 Spectral Composer Iniciado...")
        while self.running:
            if self.led:
                # --- RENDERIZAÇÃO ---
                
                # 1. Strobo (Prioridade)
                if self.strobe_active:
                    try: await self.led.set_rgb((255, 255, 255))
                    except: pass
                    await asyncio.sleep(0.05)
                    self.strobe_active = False # Flash único
                    continue

                # 2. Interpolação de Cor (Smooth Hue)
                # O tom caminha até a nota cantada
                diff = self.target_hue - self.current_hue
                if diff > 0.5: diff -= 1.0
                elif diff < -0.5: diff += 1.0
                self.current_hue = (self.current_hue + (diff * 0.05)) % 1.0

                # 3. Composição de Camadas
                
                # Camada A: Base Vermelha (Graves)
                # Vermelho puro, intensidade controlada pelo grave
                r_bass = self.env_bass
                g_bass = 0
                b_bass = 0
                
                # Camada B: Harmonia (Vocal/Teclado)
                # Cor definida pelo Hue harmônico
                # Saturação cai se o volume for muito alto (brilho "estoura" a cor)
                h_sat = 1.0 - (self.env_mid * 0.3) 
                rh, gh, bh = colorsys.hsv_to_rgb(self.current_hue, h_sat, self.env_mid)
                
                # Camada C: Shimmer (Articulação/Detalhe)
                # Adiciona Branco puro nas sílabas rápidas
                shimmer = self.env_high * VOCAL_SHIMMER_AMOUNT
                
                # Soma Vetorial (Mixagem)
                r_final = r_bass + rh + shimmer
                g_final = g_bass + gh + shimmer
                b_final = b_bass + bh + shimmer
                
                # Escuro Total Permitido
                # Se a soma for baixa, apaga mesmo
                if max(r_final, g_final, b_final) < 0.05:
                    r_final, g_final, b_final = 0, 0, 0
                
                # Clipping e Gamma
                r_final = min(1.0, r_final) ** 2.2
                g_final = min(1.0, g_final) ** 2.2
                b_final = min(1.0, b_final) ** 2.2
                
                try:
                    await self.led.set_rgb((int(r_final*255), int(g_final*255), int(b_final*255)))
                except: pass
            
            await asyncio.sleep(0.03)

    async def main(self):
        while True:
            if await self.connect():
                try:
                    target_id = None
                    devices = sd.query_devices()
                    for i, d in enumerate(devices):
                        if "Easy Effects Sink" in d['name']: target_id = i; break
                    if target_id is None:
                        for i, d in enumerate(devices):
                            if "Monitor" in d['name']: target_id = i; break
                    if target_id is None: target_id = sd.default.device[0]

                    dev_info = sd.query_devices(target_id)
                    rate = int(dev_info['default_samplerate'])
                    print(f"🎤 Audio: {dev_info['name']} @ {rate}Hz")
                    global SAMPLE_RATE; SAMPLE_RATE = rate

                    stream = sd.InputStream(callback=self.audio_callback, device=target_id, channels=1, blocksize=BLOCK_SIZE, samplerate=rate)
                    with stream: await self.led_loop()
                except Exception as e: print(f"❌ Erro: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    app = SpectralComposer()
    try: asyncio.run(app.main())
    except KeyboardInterrupt: print("\n👋")
