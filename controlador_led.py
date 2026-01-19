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
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Label, Button, Static
from textual.reactive import reactive
from textual.binding import Binding
from textual.message import Message

# Configurações de diretório
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.environ.get("XDG_CONFIG_HOME", os.path.join(os.path.expanduser("~"), ".config"))
APP_CONFIG_DIR = os.path.join(CONFIG_DIR, "controlador-led")
os.makedirs(APP_CONFIG_DIR, exist_ok=True)
SHORTCUTS_FILE = os.path.join(APP_CONFIG_DIR, "atalhos_v2.json")

class ColorBar(Static):
    """Componente de barra interativo (Slider via Mouse)."""
    value = reactive(0.0)
    
    class Changed(Message):
        """Mensagem enviada quando o valor muda via mouse."""
        def __init__(self, value: float):
            self.value = value
            super().__init__()

    def __init__(self, label, initial_value=0.0, color="white", **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.value = initial_value
        self.bar_color = color

    def render(self) -> str:
        # Cálculo visual da barra
        width = self.size.width - 20
        if width <= 0: width = 20
        filled = int(self.value * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{self.label_text:10} [{self.bar_color}]{bar}[/] {int(self.value * 100):3}%"

    def on_mouse_down(self, event) -> None:
        self.capture_mouse()
        self.update_from_mouse(event.x)

    def on_mouse_move(self, event) -> None:
        if event.button != 0: # Se algum botão estiver pressionado (arrastando)
            self.update_from_mouse(event.x)

    def on_mouse_up(self, event) -> None:
        self.release_mouse()

    def update_from_mouse(self, mouse_x):
        # A barra começa após o label (10 chars) + "[" (1 char) + espaço = ~12
        bar_start = 12
        bar_end = self.size.width - 6 # Espaço para o "%" no final
        total_width = bar_end - bar_start
        if total_width > 0:
            rel_x = mouse_x - bar_start
            new_val = max(0.0, min(1.0, rel_x / total_width))
            if new_val != self.value:
                self.value = new_val
                self.post_message(self.Changed(new_val))

class LEDControllerApp(App):
    CSS = """
    Screen {
        align: center middle;
    }

    #main_container {
        width: 65;
        height: auto;
        border: thick $primary;
        padding: 1;
        background: $surface;
    }

    .preview {
        width: 100%;
        height: 4;
        content-align: center middle;
        margin: 1 0;
        border: double white;
        text-style: bold;
    }

    ColorBar {
        margin: 1 0;
        height: 1;
        cursor: pointer;
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

    .shortcut-btn {
        min-width: 8;
    }
    
    #status {
        background: $accent;
        color: $text;
        text-style: bold;
        margin-bottom: 1;
        padding: 0 1;
    }

    .hint {
        color: $text-disabled;
        font-size: 80%;
    }
    """

    TITLE = "Controlador LED Mouse-Friendly"
    BINDINGS = [
        Binding("q", "quit", "Sair"),
        Binding("r", "reset", "Reset"),
        Binding("x", "toggle_save", "Modo Salvar"),
    ]

    hue = reactive(0.0)
    sat = reactive(1.0)
    val = reactive(1.0)
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

    def save_shortcut(self, slot):
        self.shortcuts[str(slot)] = {'h': self.hue, 's': self.sat, 'v': self.val}
        with open(SHORTCUTS_FILE, 'w') as f: json.dump(self.shortcuts, f)
        self.notify(f"Slot {slot} salvo")
        self.save_mode = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main_container"):
            yield Label("", id="status")
            yield Static("PREVIEW", classes="preview", id="preview")
            
            yield ColorBar("MATIZ (H)", id="bar_hue", color="yellow")
            yield ColorBar("SATUR (S)", id="bar_sat", color="cyan")
            yield ColorBar("BRILHO (V)", id="bar_val", color="white")
            
            yield Label("CLIQUE NAS BARRAS PARA AJUSTAR", classes="hint")
            yield Label("", id="mode_hint")
            
            with Container(id="shortcuts_grid"):
                for i in range(1, 11):
                    yield Button(str(i % 10), id=f"short_{i % 10}", classes="shortcut-btn")
        yield Footer()

    async def on_mount(self):
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

    def on_color_bar_changed(self, message: ColorBar.Changed):
        """Captura mudanças vindo do clique/arraste do mouse."""
        if message.control.id == "bar_hue": self.hue = message.value
        elif message.control.id == "bar_sat": self.sat = message.value
        elif message.control.id == "bar_val": self.val = message.value
        self.update_visuals()

    def update_visuals(self):
        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        rgb = (int(r*255), int(g*255), int(b*255))
        hex_c = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}".upper()
        
        try:
            prev = self.query_one("#preview")
            prev.styles.background = hex_c
            prev.update(f"HSV: {self.hue:.2f}, {self.sat:.2f}, {self.val:.2f}\nRGB: {rgb[0]}, {rgb[1]}, {rgb[2]} | {hex_c}")
            
            self.query_one("#bar_hue").value = self.hue
            self.query_one("#bar_sat").value = self.sat
            self.query_one("#bar_val").value = self.val
            
            if self.led:
                self.run_worker(self.led.set_rgb(rgb))
        except: pass

    def watch_status_msg(self, msg): self.query_one("#status").update(msg)
    
    def watch_save_mode(self, active):
        hint = self.query_one("#mode_hint")
        if active:
            hint.update("[b yellow]MODO SALVAR ATIVO: CLIQUE NUM NÚMERO[/]")
            self.query_one("#main_container").styles.border = ("thick", "yellow")
        else:
            hint.update("")
            self.query_one("#main_container").styles.border = ("thick", "blue")

    def action_toggle_save(self): self.save_mode = not self.save_mode
    def action_reset(self): self.hue, self.sat, self.val = 0.0, 0.0, 1.0; self.update_visuals()

    async def on_button_pressed(self, event: Button.Pressed):
        slot = event.button.id.split("_")[1]
        if self.save_mode:
            self.save_shortcut(slot)
        else:
            if slot in self.shortcuts:
                s = self.shortcuts[slot]
                self.hue, self.sat, self.val = s['h'], s['s'], s['v']
                self.update_visuals()
                self.notify(f"Slot {slot} carregado")
            else:
                self.notify("Slot vazio. Pressione 'X' para salvar a cor atual aqui.")

if __name__ == "__main__":
    app = LEDControllerApp(sys.argv[1] if len(sys.argv) > 1 else None)
    app.run()