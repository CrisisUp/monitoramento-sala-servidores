#!/usr/bin/env python3
import subprocess
import time
import random

# Nome dos containers (confirme com 'docker compose ps')
CONTAINER_API = "sala-servidor-loja2-api-1"
CONTAINER_PROXY = "sala-servidor-loja2-proxy-1"

def simular_queda_rede():
    print("🌐 Simulando queda de rede no SRV-02...")
    try:
        # Para os containers de rede (simula falha de link)
        subprocess.run(["docker", "stop", CONTAINER_PROXY, CONTAINER_API], check=True, stdout=subprocess.DEVNULL)
        print("   Containers parados. Aguardando 15 segundos...")
        time.sleep(15)
    except Exception as e:
        print(f"   Erro ao parar containers: {e}")
    finally:
        # Traz de volta
        print("   Restaurando containers...")
        subprocess.run(["docker", "start", CONTAINER_PROXY, CONTAINER_API], check=False, stdout=subprocess.DEVNULL)
        print("   Containers restaurados!")

if __name__ == "__main__":
    print("=" * 60)
    print("📡 SIMULADOR DE QUEDA DE REDE (SRV-02)")
    print("Este script derruba o proxy e a API por 15s para testar o Zabbix.")
    print("=" * 60)
    
    while True:
        opcao = input("\nPressione ENTER para simular a queda (ou 'q' para sair): ").strip().lower()
        if opcao == 'q':
            break
        simular_queda_rede()