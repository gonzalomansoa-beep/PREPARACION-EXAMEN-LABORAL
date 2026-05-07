import os
import json
import time
import requests
from flask import Flask, request, Response
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# --- CONFIGURACIÓN ---
# Usamos gemini-2.5-flash que es el que te funcionaba antes
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODELO = "gemini-2.5-flash" 
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent?key={GEMINI_API_KEY}"
CALENDAR_ID = os.environ.get("CALENDAR_ID", "")

def agendar_en_google(datos_cita):
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}")
        info_servicio = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info_servicio, scopes=['https://www.googleapis.com/auth/calendar']
        )
        service = build('calendar', 'v3', credentials=creds)

        evento = {
            'summary': f"CITA: {datos_cita.get('nombre', 'Paciente')} - {datos_cita.get('tratamiento', 'Consulta')}",
            'description': 'Agendado automáticamente por Bot Dental.',
            'start': {'dateTime': datos_cita['inicio'], 'timeZone': 'Europe/Madrid'},
            'end': {'dateTime': datos_cita['fin'], 'timeZone': 'Europe/Madrid'},
        }

        service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        return True
    except Exception as e:
        print(f"❌ Error Calendar: {e}")
        return False

def llamar_gemini(historial, es_extraccion=False):
    prompt_sistema = "Eres el asistente de Odontología Sánchez. Agenda citas pidiendo Nombre, Tratamiento y Día/Hora. Confirma con: '✅ ¡Cita confirmada!'"
    
    if es_extraccion:
        # Prompt para convertir texto en JSON para el calendario
        payload = {"contents": historial}
    else:
        payload = {
            "system_instruction": {"parts": [{"text": prompt_sistema}]},
            "contents": historial
        }

    r = requests.post(GEMINI_URL, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

@app.route("/webhook", methods=["POST"])
def webhook():
    numero = request.form.get("From", "")
    mensaje_usuario = request.form.get("Body", "").strip()
    
    if not mensaje_usuario: return Response("<Response/>", mimetype="text/xml")
    
    if numero not in conversaciones: conversaciones[numero] = []
    conversaciones[numero].append({"role": "user", "parts": [{"text": mensaje_usuario}]})

    try:
        # 1. Obtener respuesta de la IA
        respuesta = llamar_gemini(conversaciones[numero])
        conversaciones[numero].append({"role": "model", "parts": [{"text": respuesta}]})
        
        # 2. Si hay confirmación, intentamos agendar (en segundo plano)
        if "✅ ¡Cita confirmada!" in respuesta:
            try:
                # Pedimos a la IA que nos dé el JSON de esa última respuesta
                prompt_json = f"Transforma esto en JSON: '{respuesta}'. Hoy es 2026. JSON con: nombre, tratamiento, inicio (ISO), fin (ISO)."
                datos_raw = llamar_gemini([{"role": "user", "parts": [{"text": prompt_json}]}], es_extraccion=True)
                clean_json = datos_raw.replace("```json", "").replace("```", "").strip()
                agendar_en_google(json.loads(clean_json))
            except Exception as e:
                print(f"⚠️ No se pudo agendar pero el bot seguirá: {e}")

        return Response(f"<Response><Message>{respuesta}</Message></Response>", mimetype="text/xml")
    
    except Exception as e:
        print(f"🔥 ERROR CRÍTICO: {e}")
        return Response("<Response><Message>Lo siento, tengo un problema técnico. Llámanos al 628 493 012. 🦷</Message></Response>", mimetype="text/xml")

conversaciones = {}

@app.route("/")
def home(): return "Bot Dental Activo"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
