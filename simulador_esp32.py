#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulador_esp32.py — Simulação simples por linha de comando (sem rich)
"""

import time
import random
import json
import socket
import threading
import os

ZABBIX_SERVER, ZABBIX_PORT = "127.0.0.1", 10051
ZABBIX_HOST, ZABBIX_KEY = "esp32-sala", "esp32.status"
INTERVALO_ENVIO = 5
API_PORT = 8080

class SalaServidores:
    def __init__(self):
        self.temp, self.umid = 24.0, 50.0
        self.ar_condicionado_ligado = True
        self.porta_aberta, self.agua, self.energia = False, 0, True
        self.tempo_ligado = 0
        self.forcar_agua = self.forcar_porta = self.forcar_energia = False

    def tick(self, dt):
        self.tempo_ligado += dt
        if self.forcar_energia:
            self.energia, self.ar_condicionado_ligado = False, False
        else:
            if self.energia and random.random() < 0.005:
                self.energia, self.ar_condicionado_ligado = False, False
            elif not self.energia and random.random() < 0.05:
                self.energia, self.ar_condicionado_ligado = True, True

        if self.energia:
            if self.ar_condicionado_ligado and self.temp <= 23.0: self.ar_condicionado_ligado = False
            elif not self.ar_condicionado_ligado and self.temp >= 26.0: self.ar_condicionado_ligado = True

        self.temp += -0.1 * dt if self.ar_condicionado_ligado else 0.2 * dt
        if self.porta_aberta: self.temp += 0.3 * dt
        self.temp += random.uniform(-0.05, 0.05)
        self.temp = max(15.0, min(40.0, self.temp))
        self.umid = max(30.0, min(90.0, 50.0 - (self.temp - 24.0) * 2.0 + random.uniform(-1.0, 1.0)))

        if self.forcar_porta: self.porta_aberta = True
        else:
            if self.porta_aberta and random.random() < 0.1 * dt: self.porta_aberta = False
            elif not self.porta_aberta and random.random() < 0.01 * dt: self.porta_aberta = True

        if self.forcar_agua: self.agua = 1
        else:
            if self.agua and random.random() < 0.1 * dt: self.agua = 0
            elif not self.agua and random.random() < 0.01 * dt: self.agua = 1

    def obter_json(self):
        return json.dumps({"temperatura": round(self.temp, 1), "umidade": int(self.umid), "dht_ok": True,
                           "agua": self.agua, "porta_aberta": 1 if self.porta_aberta else 0,
                           "energia": 1 if self.energia else 0, "uptime_s": int(self.tempo_ligado), "versao": "Gemeo-Digital"})

# Zabbix push
def enviar_zabbix(payload_str):
    try:
        cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        cliente.settimeout(1.0)
        cliente.connect((ZABBIX_SERVER, ZABBIX_PORT))
        cliente.sendall(b'ZBXD\x01' + len(payload_str).to_bytes(8, 'little') + payload_str.encode('utf-8'))
        cliente.recv(1024)
        cliente.close()
        return True
    except: return False

# --- THREAD DE COMANDOS (SEM CONFLITO COM A TELA) ---
def thread_comandos(sala):
    print("\n[CONTROLE DE CAOS] Digite A (Água), P (Porta), E (Energia), R (Resetar) ou Q (Sair) e aperte Enter:\n")
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == 'a':
                sala.forcar_agua = not sala.forcar_agua
                print(f" -> Água: {'FORÇADO MOLHADO' if sala.forcar_agua else 'NORMAL'}")
            elif cmd == 'p':
                sala.forcar_porta = not sala.forcar_porta
                print(f" -> Porta: {'FORÇADO ABERTA' if sala.forcar_porta else 'NORMAL'}")
            elif cmd == 'e':
                sala.forcar_energia = not sala.forcar_energia
                print(f" -> Energia: {'FORÇADO SEM ENERGIA' if sala.forcar_energia else 'NORMAL'}")
            elif cmd == 'r':
                sala.forcar_agua = sala.forcar_porta = sala.forcar_energia = False
                print(" -> Resetado!")
            elif cmd == 'q':
                print("\nSaindo...")
                os._exit(0)
            else:
                print(" -> Comando inválido. Use A, P, E, R ou Q.")
        except EOFError:
            break

def main():
    sala = SalaServidores()
    threading.Thread(target=thread_comandos, args=(sala,), daemon=True).start()

    print("=" * 60)
    print(f"🌡️  SIMULADOR DE SALA INICIADO")
    print(f"   Zabbix Alvo: {ZABBIX_SERVER}:{ZABBIX_PORT}")
    print("=" * 60)

    ultimo_envio = 0
    try:
        while True:
            sala.tick(1.0)
            
            # Imprime o status a cada 3 segundos (sem poluir o terminal)
            if int(sala.tempo_ligado) % 3 == 0 and int(sala.tempo_ligado) > 0:
                st_ac = "❄️ ON " if sala.ar_condicionado_ligado else "🔥 OFF"
                st_porta = "🚪 ABERTA" if sala.porta_aberta else "🔒 FECHADA"
                st_agua = "💧 MOLHADO" if sala.agua else "☀️ SECO"
                print(f"[T={sala.temp:.1f}°C | U={sala.umid:.0f}% | AC={st_ac} | {st_porta} | {st_agua}]")

            if time.time() - ultimo_envio >= INTERVALO_ENVIO:
                ultimo_envio = time.time()
                payload = {"request": "sender data", "data": [{"host": ZABBIX_HOST, "key": ZABBIX_KEY, "value": sala.obter_json()}]}
                enviar_zabbix(json.dumps(payload))

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSimulação encerrada.")

if __name__ == "__main__":
    main()