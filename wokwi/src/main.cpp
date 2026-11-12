/**
 * @file main.cpp (RackMonitor_Zabbix)
 * @brief Sistema de Monitoramento adaptado para Zabbix (Wokwi).
 * * Versão refatorada: Core 2.x, ArduinoJson 7.x, Wi-Fi com retry.
 * * Nota: Para o Cloudflare Tunnel, usamos WiFiClientSecure na porta 443.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <Preferences.h>
#include <DHT.h>
#include <ArduinoJson.h>
#include <esp_task_wdt.h>

// =========================================================================
// CONFIGURAÇÃO DE REDE E ZABBIX
// =========================================================================
const char *WIFI_SSID = "Wokwi-GUEST";
const char *WIFI_PASSWORD = "";
// Se for usar o Cloudflare Tunnel, coloque o endereço aqui:
const char *ZABBIX_HOST = "reserves-instrumental-empty-blocks.trycloudflare.com";
const int ZABBIX_PORT = 443; // 443 para Cloudflare Tunnel (HTTPS)
const char *ZABBIX_HOSTNAME = "esp32-sala";
const char *ZABBIX_KEY = "esp32.status";

// =========================================================================
// MAPEAMENTO DE HARDWARE
// =========================================================================
namespace Pins
{
    constexpr uint8_t DHT_PIN = 13;
    constexpr uint8_t PORTA_PIN = 25; // Sensor MC-38 / Botão
    constexpr uint8_t LED_PIN = 2;    // LED da placa
}

constexpr unsigned long DEBOUNCE_PORTA_MS = 200;
constexpr unsigned long INTERVALO_PUSH_MS = 15000;

// =========================================================================
// VARIÁVEIS GLOBAIS
// =========================================================================
DHT dht(Pins::DHT_PIN, DHT22);
Preferences prefs;

float temperatura = 0.0;
float umidade = 0.0;
bool dhtOk = false;
bool portaAberta = false;

unsigned long ultimaLeituraDHT = 0;
unsigned long ultimaLeituraPorta = 0;
unsigned long ultimoPush = 0;
bool portaEstadoAnterior = false;

// =========================================================================
// UTILITÁRIOS E LOG
// =========================================================================
void logSerial(const String &nivel, const String &tag, const String &mensagem)
{
    Serial.print("[");
    Serial.print(millis());
    Serial.print("] [");
    Serial.print(nivel);
    Serial.print("] [");
    Serial.print(tag);
    Serial.print("] ");
    Serial.println(mensagem);
}

// =========================================================================
// COMUNICAÇÃO ZABBIX (PUSH)
// =========================================================================
void enviarParaZabbix()
{
    if (WiFi.status() != WL_CONNECTED)
        return;

    // ArduinoJson 7.x
    JsonDocument sensorDoc;
    sensorDoc["temperatura"] = temperatura;
    sensorDoc["umidade"] = (int)umidade;
    sensorDoc["dht_ok"] = dhtOk;
    sensorDoc["porta_aberta"] = portaAberta ? 1 : 0;
    sensorDoc["agua"] = 0;    // RackMonitor não tem sensor de chuva
    sensorDoc["energia"] = 1; // Assume energia presente
    sensorDoc["uptime_s"] = millis() / 1000;
    sensorDoc["versao"] = "RackMonitor-Zbx";

    String jsonValor;
    serializeJson(sensorDoc, jsonValor);

    JsonDocument doc;
    doc["request"] = "sender data";
    JsonObject d = doc["data"].add<JsonObject>(); // Sintaxe v7
    d["host"] = ZABBIX_HOSTNAME;
    d["key"] = ZABBIX_KEY;
    d["value"] = jsonValor;

    String payload;
    serializeJson(doc, payload);

    // Usa WiFiClientSecure para o túnel HTTPS (Cloudflare)
    WiFiClientSecure cliente;
    cliente.setInsecure(); // Ignora validação de certificado no Wokwi

    if (!cliente.connect(ZABBIX_HOST, ZABBIX_PORT, 2000))
    { // Timeout maior para HTTPS
        logSerial("WARN", "ZABBIX", "Falha ao conectar.");
        return;
    }

    // Protocolo binário do Zabbix
    uint8_t cabecalho[13] = {'Z', 'B', 'X', 'D', 1};
    uint64_t tamanho = payload.length();
    for (int i = 0; i < 8; i++)
        cabecalho[5 + i] = (tamanho >> (8 * i)) & 0xFF;

    cliente.write(cabecalho, 13);
    cliente.write((const uint8_t *)payload.c_str(), payload.length());

    unsigned long inicio = millis();
    while (cliente.connected() && !cliente.available() && millis() - inicio < 2000)
        delay(10);

    String resposta = "";
    while (cliente.available())
        resposta += (char)cliente.read();
    cliente.stop();

    if (resposta.indexOf("\"failed\":0") >= 0 || resposta.indexOf("\"failed\": 0") >= 0)
    {
        logSerial("INFO", "ZABBIX", "Push OK (T=" + String(temperatura, 1) + " P=" + String(portaAberta) + ")");
    }
    else
    {
        logSerial("WARN", "ZABBIX", "Recusado: " + resposta);
    }
}

// =========================================================================
// SETUP
// =========================================================================
void setup()
{
    Serial.begin(115200);
    delay(200);
    Serial.println("\n=== RACK MONITOR -> ZABBIX (WOKWI) ===");

    pinMode(Pins::LED_PIN, OUTPUT);
    pinMode(Pins::PORTA_PIN, INPUT_PULLUP);
    dht.begin();

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("Conectando ao WiFi");
    unsigned long inicio = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - inicio < 30000)
    {
        delay(500);
        Serial.print(".");
        if (millis() - inicio > 15000 && WiFi.status() != WL_CONNECTED)
        {
            WiFi.disconnect();
            WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        }
    }

    if (WiFi.status() == WL_CONNECTED)
    {
        Serial.println("\nWiFi Conectado! IP: " + WiFi.localIP().toString());
        Serial.println("Zabbix Alvo: " + String(ZABBIX_HOST) + ":" + String(ZABBIX_PORT));
    }
    else
    {
        Serial.println("\nFalha no WiFi. O Zabbix não vai receber dados.");
    }

    esp_task_wdt_init(10, true);
    esp_task_wdt_add(NULL);

    portaEstadoAnterior = (digitalRead(Pins::PORTA_PIN) == HIGH);
    portaAberta = portaEstadoAnterior;
}

// =========================================================================
// LOOP
// =========================================================================
void loop()
{
    unsigned long agora = millis();
    esp_task_wdt_reset();

    bool leituraPorta = (digitalRead(Pins::PORTA_PIN) == HIGH);
    if (leituraPorta != portaAberta && (agora - ultimaLeituraPorta > DEBOUNCE_PORTA_MS))
    {
        portaAberta = leituraPorta;
        ultimaLeituraPorta = agora;
        logSerial("INFO", "PORTA", portaAberta ? "ABERTA" : "FECHADA");
        enviarParaZabbix();
        ultimoPush = agora;
    }

    if (agora - ultimaLeituraDHT > 5000)
    {
        ultimaLeituraDHT = agora;
        float t = dht.readTemperature();
        float h = dht.readHumidity();
        if (!isnan(t) && !isnan(h))
        {
            temperatura = t;
            umidade = h;
            dhtOk = true;
            logSerial("INFO", "DHT", "T=" + String(temperatura, 1) + " U=" + String(umidade, 0));
        }
        else
        {
            dhtOk = false;
            logSerial("WARN", "DHT", "Falha na leitura");
        }
    }

    if (agora - ultimoPush > INTERVALO_PUSH_MS)
    {
        ultimoPush = agora;
        enviarParaZabbix();
    }

    if (portaAberta)
    {
        digitalWrite(Pins::LED_PIN, (agora / 200) % 2);
    }
    else
    {
        digitalWrite(Pins::LED_PIN, LOW);
    }

    delay(10);
}