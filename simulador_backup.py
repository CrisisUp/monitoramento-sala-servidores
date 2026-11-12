#!/usr/bin/env python3
import requests
import time
import os
from dotenv import load_dotenv

# Carrega o .env para pegar as credenciais
load_dotenv()

ZABBIX_URL = "http://localhost:8080/api_jsonrpc.php"
ZABBIX_USER = "Admin"
ZABBIX_PASS = os.getenv("ZABBIX_PASSWORD", "zabbix")
HOST_NAME = "Sensores da sala"

def zabbix_api(method, params, auth=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    if auth:
        payload["auth"] = auth
    headers = {"Content-Type": "application/json-rpc"}
    r = requests.post(ZABBIX_URL, json=payload, headers=headers)
    r.raise_for_status()
    return r.json().get("result")

def main():
    print("=" * 60)
    print("🛠️  SIMULADOR DE MANUTENÇÃO")
    print("Coloca o host em manutenção no Zabbix por 2 minutos.")
    print("=" * 60)

    try:
        # Login no Zabbix
        auth = zabbix_api("user.login", {"user": ZABBIX_USER, "password": ZABBIX_PASS})
        
        # Busca o ID do host
        hosts = zabbix_api("host.get", {"filter": {"host": [HOST_NAME]}}, auth)
        if not hosts:
            print(f"❌ Host '{HOST_NAME}' não encontrado.")
            return
        host_id = hosts[0]["hostid"]

        # Cria a manutenção
        now = int(time.time())
        print(f"Ativando manutenção no host '{HOST_NAME}' por 120 segundos...")
        
        result = zabbix_api("maintenance.create", {
            "name": "Simulação de Manutenção",
            "active_since": now,
            "active_till": now + 120,
            "hostids": [host_id],
            "timeperiods": [{"timeperiod_type": 0, "start_date": now, "period": 120}],
            "maintenance_type": 0 # Com coleta de dados
        }, auth)
        
        print(f"✅ Manutenção criada (ID: {result['maintenanceids'][0]}).")
        print("   Os alertas deste host estão silenciados no Grafana.")
        print("   Aguarde 2 minutos para a manutenção expirar.")
        
    except Exception as e:
        print(f"❌ Erro: {e}")

if __name__ == "__main__":
    main()
