#!/usr/bin/env python3
import asyncio
import sys
import socket

SOCKET_PATH = "/tmp/silverblue_led.sock"

async def send_ping(color="green"):
    try:
        reader, writer = await asyncio.open_unix_connection(SOCKET_PATH)
        message = f"PING {color}"
        writer.write(message.encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        print(f"✅ Comando enviado: {message}")
    except FileNotFoundError:
        print("❌ Serviço LED não está rodando (Socket não encontrado).")
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")

if __name__ == "__main__":
    color = sys.argv[1] if len(sys.argv) > 1 else "magenta"
    asyncio.run(send_ping(color))
