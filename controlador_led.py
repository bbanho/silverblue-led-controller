#!/usr/bin/env python3
import asyncio
import sys
import json
import colorsys
import os
import subprocess
from bleak import BleakScanner
from led_ble import LEDBLE

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Header, Footer, Label, Button, Static
from textual.reactive import reactive
from textual.binding import Binding

# Configurações de diretório
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
APP_CONFIG_DIR = os.path.join(CONFIG_DIR, "controlador-led")
os.makedirs(APP_CONFIG_DIR, exist_ok=True)
SHORTCUTS_FILE = os.path.join(APP_CONFIG_DIR, "atalhos_v2.json")

class SimpleBar(Static):
    """Uma barra de progresso ASCII simples que reage à seleção."""
    value = reactive(0.0)
    selected = reactive(False)
    
    def __init__(self, label, initial_value=0.0, **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.value = initial_value

    def render(self) -> str:
        width = self.size.width - 20
        if width <= 0: width = 20
        filled = int(self.value * width)
        
        prefix = "> " if self.selected else "  "
        bar_char = "█" if self.selected else "▒"
        empty_char = " " if self.selected else "░"
        
        bar = bar_char * filled + empty_char * (width - filled)
        style = "reverse" if self.selected else ""
        
        return f"{prefix}{self.label_text:10} [{style}]{bar}[/] {int(self.value * 100):3}%"

class LEDControllerApp(App):
    CSS = """
    Screen {
        align: center middle;
    }

    #main_container {
        width: 60;
        height: auto;
        border: thick $primary;
        padding: 1;
        background: $surface;
    }

    .preview {
        width: 100%;
        height: 3;
        content-align: center middle;
        margin: 1 0;
        border: double white;
        text-style: bold;
    }

    SimpleBar {
        margin: 0 0;
        height: 1;
    }

    #status {
        background: $accent;
        color: $text;
        text-style: bold;
        margin-bottom: 1;
        padding: 0 1;
    }

    .selected {
        color: $accent;
        text-style: bold;
    }
    """

    TITLE = "Controlador LED Teclado"
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("up", "select_prev", "Sel. Acima", show=False),
        Binding("down", "select_next", "Sel. Abaixo", show=False),
        Binding("left", "adj_minus", "Ajustar -", show=False),
        Binding("right", "adj_plus", "Ajustar +", show=False),
        Binding("x", "toggle_save", "Modo Salvar"),
    ]

    # Estado HSV
    hue = reactive(0.0)
    sat = reactive(1.0)
    val = reactive(1.0)
    selected_idx = reactive(0) # 0=Hue, 1=Sat, 2=Val
    status_msg = reactive("Escaneando...")
    save_mode = reactive(False)

    def __init__(self, address=None):
        super().__init__()
        self.address = address
        self.led = None
        self.shortcuts = self.load_shortcuts()

    def load_shortcuts(self):
        if os.path.exists(SHORTCUTS_FILE):
            try:
                with open(SHORTCUTS_FILE, 'r') as f: return json.load(f)
            except: return {}
        return {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main_container"):
            yield Label("", id="status")
            yield Static("PREVIEW", classes="preview", id="preview")
            
            yield SimpleBar("MATIZ (H)", id="bar_0")
            yield SimpleBar("SATUR (S)", id="bar_1")
            yield SimpleBar("BRILHO (V)", id="bar_2")
            
            yield Label("\n[b]Setas: Selecionar e Ajustar[/b]", classes="hint")
            yield Label("", id="mode_hint")
        yield Footer()

    async def on_mount(self):
        self.update_selection()
        self.update_visuals()
        if self.address:
            await self.connect_to_device(self.address)
        else:
            self.run_worker(self.auto_scan)

    async def auto_scan(self):
        devices = await BleakScanner.discover()
        leds = [d for d in devices if d.name and d.name != "Unknown"]
        if leds:
            await self.connect_to_device(leds[0].address)
        else:
            self.status_msg = "Nenhum dispositivo encontrado."

    async def connect_to_device(self, address):
        self.status_msg = f"Conectando: {address}..."
        try:
            device = await BleakScanner.find_device_by_address(address)
            self.led = LEDBLE(device)
            try:
                await self.led.update()
                await self.led.turn_on()
            except: pass
            
            if self.led.rgb:
                r, g, b = self.led.rgb
                h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
                self.hue, self.sat, self.val = h, s, v
            
            self.status_msg = f"CONECTADO: {device.name or address}"
        except Exception as e:
            self.status_msg = f"ERRO: {e}"

    def update_selection(self):
        for i in range(3):
            bar = self.query_one(f"#bar_{i}", SimpleBar)
            bar.selected = (i == self.selected_idx)

    def update_visuals(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        rgb = (int(r*255), int(g*255), int(b*255))
        hex_c = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}".upper()
        
        try:
            prev = self.query_one("#preview")
            prev.styles.background = hex_c
            prev.update(f"RGB: {rgb[0]}, {rgb[1]}, {rgb[2]} | {hex_c}")
            
            self.query_one("#bar_0").value = self.hue
            self.query_one("#bar_1").value = self.sat
            self.query_one("#bar_2").value = self.val
            
            if self.led:
                self.run_worker(self.led.set_rgb(rgb))
        except: pass

    # Ações de Teclado
    def action_select_next(self):
        self.selected_idx = (self.selected_idx + 1) % 3
        self.update_selection()

    def action_select_prev(self):
        self.selected_idx = (self.selected_idx - 1) % 3
        self.update_selection()

    def action_adj_plus(self):
        step = 0.05
        if self.selected_idx == 0: self.hue = (self.hue + step) % 1.0
        elif self.selected_idx == 1: self.sat = min(1.0, self.sat + step)
        elif self.selected_idx == 2: self.val = min(1.0, self.val + step)
        self.update_visuals()

    def action_adj_minus(self):
        step = 0.05
        if self.selected_idx == 0: self.hue = (self.hue - step) % 1.0
        elif self.selected_idx == 1: self.sat = max(0.0, self.sat - step)
        elif self.selected_idx == 2: self.val = max(0.0, self.val - step)
        self.update_visuals()

    def action_toggle_save(self):
        self.save_mode = not self.save_mode
        self.query_one("#mode_hint").update("[b yellow]MODO SALVAR: PRESSIONE 1-9[/]" if self.save_mode else "")

    def on_key(self, event):
        if event.key.isdigit() and event.key != "0":
            slot = event.key
            if self.save_mode:
                self.shortcuts[slot] = {'h': self.hue, 's': self.sat, 'v': self.val}
                with open(SHORTCUTS_FILE, 'w') as f: json.dump(self.shortcuts, f)
                self.notify(f"Slot {slot} salvo")
                self.save_mode = False
                self.query_one("#mode_hint").update("")
            else:
                if slot in self.shortcuts:
                    s = self.shortcuts[slot]
                    self.hue, self.sat, self.val = s['h'], s['s'], s['v']
                    self.update_visuals()
                    self.notify(f"Slot {slot} carregado")

    def watch_status_msg(self, msg):
        self.query_one("#status").update(msg)

if __name__ == "__main__":
    app = LEDControllerApp(sys.argv[1] if len(sys.argv) > 1 else None)
    app.run()
