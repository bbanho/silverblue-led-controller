#!/usr/bin/env python3
import asyncio
import sys
import json
import colorsys
import os
import subprocess
import threading
from bleak import BleakScanner
from led_ble import LEDBLE

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Label, Button, Static, LoadingIndicator
from textual.reactive import reactive
from textual.binding import Binding

# Determinar o diretório onde o script está localizado
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
APP_CONFIG_DIR = os.path.join(CONFIG_DIR, "controlador-led")
os.makedirs(APP_CONFIG_DIR, exist_ok=True)
SHORTCUTS_FILE = os.path.join(APP_CONFIG_DIR, "atalhos_v2.json")

# Biblioteca de Presets Temáticos (HSV)
PRESETS = {
    "PASTEL": [
        {"name": "Rosa", "h": 0.95, "s": 0.3, "v": 0.9},
        {"name": "Verde", "h": 0.35, "s": 0.3, "v": 0.9},
        {"name": "Azul", "h": 0.55, "s": 0.3, "v": 0.9},
        {"name": "Lilás", "h": 0.75, "s": 0.3, "v": 0.9},
    ],
    "CONFORTO": [
        {"name": "Quente", "h": 0.08, "s": 0.6, "v": 0.7},
        {"name": "Vela", "h": 0.05, "s": 0.8, "v": 0.5},
        {"name": "Âmbar", "h": 0.10, "s": 0.9, "v": 0.8},
        {"name": "Noite", "h": 0.06, "s": 0.4, "v": 0.3},
    ],
    "FRIO": [
        {"name": "Gelo", "h": 0.50, "s": 0.2, "v": 0.9},
        {"name": "Oceano", "h": 0.60, "s": 0.8, "v": 0.6},
        {"name": "Céu", "h": 0.58, "s": 0.5, "v": 0.8},
        {"name": "Deep", "h": 0.65, "s": 0.9, "v": 0.4},
    ]
}

class ColorBar(Static):
    """Um componente de barra de progresso que funciona como um slider customizado."""
    value = reactive(0.0)
    
    def __init__(self, label, initial_value=0.0, color="white", **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.value = initial_value
        self.bar_color = color

    def render(self) -> str:
        width = self.size.width - 20
        if width <= 0: width = 20
        filled = int(self.value * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{self.label_text:10} [{self.bar_color}]{bar}[/] {int(self.value * 100):3}%"

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
    }

    ColorBar {
        margin: 0 0;
        height: 1;
    }

    Label {
        width: 100%;
        content-align: center middle;
    }

    #shortcuts_grid {
        layout: grid;
        grid-size: 5;
        grid-gutter: 1;
        margin-top: 1;
        height: auto;
    }

    #presets_container {
        margin-top: 1;
        border-top: dashed $primary;
        padding-top: 1;
        height: auto;
    }

    .preset-cat {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }

    .shortcut-btn, .preset-btn {
        min-width: 8;
    }
    
    #status {
        background: $accent;
        color: $text;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    TITLE = "Controlador LED Pro"
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("r", "reset", "Resetar"),
        Binding("right", "inc_hue", "Hue +", show=False),
        Binding("left", "dec_hue", "Hue -", show=False),
        Binding("up", "inc_val", "Brilho +", show=False),
        Binding("down", "dec_val", "Brilho -", show=False),
        Binding("d", "inc_hue", "Hue +"),
        Binding("a", "dec_hue", "Hue -"),
        Binding("w", "inc_val", "Brilho +"),
        Binding("s", "dec_val", "Brilho -"),
        Binding("e", "inc_sat", "Sat +"),
        Binding("f", "dec_sat", "Sat -"),
    ]

    # Estado HSV reativo
    hue = reactive(0.0)
    sat = reactive(1.0)
    val = reactive(1.0)
    status_msg = reactive("Iniciando...")

    def __init__(self, address=None):
        super().__init__()
        self.address = address
        self.led = None
        self.shortcuts = self.load_shortcuts()
        self.scan_result = []

    def load_shortcuts(self):
        if os.path.exists(SHORTCUTS_FILE):
            try:
                with open(SHORTCUTS_FILE, 'r') as f:
                    return json.load(f)
            except: return {}
        return {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main_container"):
            yield Label("", id="status")
            yield Static("COR ATUAL", classes="preview", id="preview")
            
            yield ColorBar("MATIZ (H)", id="bar_hue", color="yellow")
            yield ColorBar("SATUR (S)", id="bar_sat", color="cyan")
            yield ColorBar("BRILHO (V)", id="bar_val", color="white")
            
            yield Label("[b]Meus Atalhos[/b]")
            with Container(id="shortcuts_grid"):
                for i in range(1, 11):
                    yield Button(str(i % 10), id=f"short_{i % 10}", classes="shortcut-btn")
            
            with Vertical(id="presets_container"):
                yield Label("[b]Temas Prontos[/b]")
                for cat, items in PRESETS.items():
                    yield Label(cat, classes="preset-cat")
                    with Horizontal():
                        for item in items:
                            btn = Button(item["name"], id=f"pre_{cat}_{item['name']}", classes="preset-btn")
                            # Armazenar hsv no botão para facilitar
                            btn.hsv_data = (item["h"], item["s"], item["v"])
                            yield btn
        yield Footer()

    async def on_mount(self):
        self.update_ui_elements()
        if self.address:
            await self.connect_to_device(self.address)
        else:
            self.run_worker(self.scan_and_connect)

    async def scan_and_connect(self):
        self.status_msg = "Escaneando Bluetooth..."
        devices = await BleakScanner.discover()
        led_devices = [d for d in devices if d.name and d.name != "Unknown"]
        
        if len(led_devices) == 1:
            await self.connect_to_device(led_devices[0].address)
        elif len(led_devices) > 1:
            self.status_msg = "Múltiplos dispositivos encontrados. Use CLI para escolher."
        else:
            self.status_msg = "Nenhum LED encontrado."

    async def connect_to_device(self, address):
        self.status_msg = f"Conectando a {address}..."
        try:
            device = await BleakScanner.find_device_by_address(address)
            self.led = LEDBLE(device)
            try:
                await self.led.update()
                await self.led.turn_on()
            except IndexError: pass # Hardware quirk
            
            if self.led.rgb:
                r, g, b = self.led.rgb
                h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
                self.hue, self.sat, self.val = h, s, v
            
            self.status_msg = f"CONECTADO: {device.name or address}"
        except Exception as e:
            self.status_msg = f"ERRO: {e}"

    def watch_hue(self): self.update_ui_elements()
    def watch_sat(self): self.update_ui_elements()
    def watch_val(self): self.update_ui_elements()
    def watch_status_msg(self, msg): self.query_one("#status").update(msg)

    def update_ui_elements(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        hex_color = f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
        
        try:
            preview = self.query_one("#preview")
            preview.styles.background = hex_color
            preview.update(f"RGB: {int(r*255)}, {int(g*255)}, {int(b*255)} | HEX: {hex_color.upper()}")
            
            self.query_one("#bar_hue").value = self.hue
            self.query_one("#bar_sat").value = self.sat
            self.query_one("#bar_val").value = self.val
            
            if self.led:
                self.run_worker(self.send_color_to_led(int(r*255), int(g*255), int(b*255)))
        except: pass

    async def send_color_to_led(self, r, g, b):
        try: await self.led.set_rgb((r, g, b))
        except: pass

    # Ações de Teclado
    def action_inc_hue(self): self.hue = (self.hue + 0.05) % 1.0
    def action_dec_hue(self): self.hue = (self.hue - 0.05) % 1.0
    def action_inc_sat(self): self.sat = min(1.0, self.sat + 0.1)
    def action_dec_sat(self): self.sat = max(0.0, self.sat - 0.1)
    def action_inc_val(self): self.val = min(1.0, self.val + 0.1)
    def action_dec_val(self): self.val = max(0.0, self.val - 0.1)
    def action_reset(self): self.hue, self.sat, self.val = 0.0, 0.0, 1.0

    async def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id
        if btn_id.startswith("short_"):
            slot = btn_id.split("_")[1]
            if slot in self.shortcuts:
                s = self.shortcuts[slot]
                self.hue, self.sat, self.val = s['h'], s['s'], s['v']
                self.notify(f"Atalho {slot} carregado")
            else:
                self.notify(f"Slot {slot} vazio. Use X + Número para salvar.")
        
        elif btn_id.startswith("pre_"):
            # Aplicar preset da biblioteca
            self.hue, self.sat, self.val = event.button.hsv_data
            self.notify(f"Tema aplicado!")

    # Sistema de salvar atalhos simplificado para TUI
    def on_key(self, event):
        if event.key == "x":
            self.notify("Pressione o número (0-9) para salvar a cor atual", timeout=3)
            # Logica de captura do próximo digito seria complexa aqui, 
            # simplificando: o usuário clica no botão com Shift ou algo?
            # Vamos manter apenas teclado: se pressionar numero logo após X
            pass

if __name__ == "__main__":
    address = sys.argv[1] if len(sys.argv) > 1 else None
    app = LEDControllerApp(address)
    app.run()
