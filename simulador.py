#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulador.py — Gêmeo Digital (Dashboard + API REST + Modo Caos via terminal)
"""

import time
import random
import json
import socket
import threading
import sys
import os
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text
from flask import Flask, jsonify

# =========================================================================
# CONFIGURAÇÕES
# =========================================================================
ZABBIX_SERVER = "127.0.0.1"
ZABBIX_PORT = 10051
ZABBIX_HOST = "esp32-sala"
ZABBIX_KEY = "esp32.status"
INTERVALO_ENVIO = 5
API_PORT = 8080

# =========================================================================
# ESTADO DO AMBIENTE
# =========================================================================
class SalaServidores:
    def __init__(self):
        self.temp = 24.0
        self.umid = 50.0
        self.ar_condicionado_ligado = True
        self.porta_aberta = False
        self.agua = 0
        self.energia = True
        self.tempo_ligado = 0
        
        self.forcar_agua = False
        self.forcar_porta = False
        self.forcar_energia = False

    def tick(self, delta_t):
        self.tempo_ligado += delta_t
        
        if self.forcar_energia:
            self.energia = False
            self.ar_condicionado_ligado = False
        else:
            if self.energia and random.random() < 0.005:
                self.energia = False
                self.ar_condicionado_ligado = False
            elif not self.energia and random.random() < 0.05:
                self.energia = True
                self.ar_condicionado_ligado = True
                
        if self.energia:
            if self.ar_condicionado_ligado and self.temp <= 23.0:
                self.ar_condicionado_ligado = False
            elif not self.ar_condicionado_ligado and self.temp >= 26.0:
                self.ar_condicionado_ligado = True
        
        self.temp += -0.1 * delta_t if self.ar_condicionado_ligado else 0.2 * delta_t
        if self.porta_aberta: self.temp += 0.3 * delta_t
        self.temp += random.uniform(-0.05, 0.05)
        self.temp = max(15.0, min(40.0, self.temp))

        self.umid = 50.0 - (self.temp - 24.0) * 2.0 + random.uniform(-1.0, 1.0)
        self.umid = max(30.0, min(90.0, self.umid))

        if self.forcar_porta:
            self.porta_aberta = True
        else:
            if self.porta_aberta and random.random() < 0.1 * delta_t:
                self.porta_aberta = False
            elif not self.porta_aberta and random.random() < 0.01 * delta_t:
                self.porta_aberta = True
                
        if self.forcar_agua:
            self.agua = 1
        else:
            if self.agua and random.random() < 0.1 * delta_t:
                self.agua = 0
            elif not self.agua and random.random() < 0.01 * delta_t:
                self.agua = 1

    def obter_json(self):
        return json.dumps({
            "temperatura": round(self.temp, 1),
            "umidade": int(self.umid),
            "dht_ok": True,
            "agua": self.agua,
            "porta_aberta": 1 if self.porta_aberta else 0,
            "energia": 1 if self.energia else 0,
            "uptime_s": int(self.tempo_ligado),
            "versao": "Gemeo-Digital-API"
        })

# =========================================================================
# API REST
# =========================================================================
app = Flask(__name__)
sala_global = None

@app.route('/status', methods=['GET'])
def status_api():
    assert sala_global is not None
    return jsonify(json.loads(sala_global.obter_json()))

def iniciar_api():
    app.run(port=API_PORT, host='0.0.0.0', debug=False, use_reloader=False)

# =========================================================================
# ZABBIX PUSH
# =========================================================================
def enviar_zabbix(payload_str):
    try:
        cabecalho = b'ZBXD\x01'
        tamanho = len(payload_str).to_bytes(8, byteorder='little')
        cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cliente.settimeout(1.0)
        cliente.connect((ZABBIX_SERVER, ZABBIX_PORT))
        cliente.sendall(cabecalho + tamanho + payload_str.encode('utf-8'))
        cliente.recv(1024)
        cliente.close()
        return True
    except:
        return False

# =========================================================================
# DASHBOARD
# =========================================================================
console = Console()

def gerar_layout(sala):
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=3)
    )

    layout["header"].update(Panel(
        Text(f"🌡️  GÊMEO DIGITAL DA SALA DE SERVIDORES  |  Uptime: {int(sala.tempo_ligado)}s", style="bold cyan"),
        border_style="cyan"
    ))

    table = Table(show_header=False, box=None)
    table.add_column("Sensor", style="bold")
    table.add_column("Valor", justify="right")
    table.add_column("Status")

    cor_temp = "green" if 20 <= sala.temp <= 28 else "yellow" if sala.temp < 32 else "red"
    table.add_row("Temperatura", f"[{cor_temp}]{sala.temp:.1f} °C[/]", "")
    table.add_row("Umidade", f"{sala.umid:.0f} %", "")
    
    st_energia = "[green]⚡ OK[/]" if sala.energia else "[red]🔌 SEM ENERGIA[/]"
    table.add_row("Energia", st_energia, "")
    
    st_porta = "[red]🚪 ABERTA[/]" if sala.porta_aberta else "[green]🔒 FECHADA[/]"
    table.add_row("Porta", st_porta, "")
    
    st_agua = "[red]💧 MOLHADO[/]" if sala.agua else "[green]☀️ SECO[/]"
    table.add_row("Água", st_agua, "")
    
    st_ac = "[cyan]❄️ LIGADO[/]" if sala.ar_condicionado_ligado else "[dim]🔥 DESLIGADO[/]"
    table.add_row("Ar-Condicionado", st_ac, "")

    layout["body"].update(Panel(table, title="Sensores", border_style="blue"))

    layout["footer"].update(Panel(
        Text("Digite no terminal: [A] Água  [P] Porta  [E] Energia  [R] Resetar  [Q] Sair", style="dim"),
        border_style="dim"
    ))
    return layout

# =========================================================================
# THREAD DE COMANDOS (MODO CAOS VIA INPUT)
# =========================================================================
def thread_comandos(sala):
    while True:
        try:
            cmd = input() # Lê o que o usuário digita no terminal
            cmd = cmd.strip().lower()
            if cmd == 'a':
                sala.forcar_agua = not sala.forcar_agua
            elif cmd == 'p':
                sala.forcar_porta = not sala.forcar_porta
            elif cmd == 'e':
                sala.forcar_energia = not sala.forcar_energia
            elif cmd == 'r':
                sala.forcar_agua = False
                sala.forcar_porta = False
                sala.forcar_energia = False
            elif cmd == 'q':
                os._exit(0)
        except EOFError:
            break

# =========================================================================
# LOOP PRINCIPAL
# =========================================================================
def main():
    global sala_global
    sala_global = SalaServidores()
    sala = sala_global

    threading.Thread(target=iniciar_api, daemon=True).start()
    threading.Thread(target=thread_comandos, args=(sala,), daemon=True).start()
    
    with Live(gerar_layout(sala), refresh_per_second=1, screen=True) as live:
        ultimo_envio = 0
        while True:
            sala.tick(1.0)
            live.update(gerar_layout(sala))

            if time.time() - ultimo_envio >= INTERVALO_ENVIO:
                ultimo_envio = time.time()
                payload = {
                    "request": "sender data",
                    "data": [{
                        "host": ZABBIX_HOST,
                        "key": ZABBIX_KEY,
                        "value": sala.obter_json()
                    }]
                }
                enviar_zabbix(json.dumps(payload))

            time.sleep(1)

if __name__ == "__main__":
    main()