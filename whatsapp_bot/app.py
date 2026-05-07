import os
import json
import time
import requests
from flask import Flask, request, Response
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# --- CONFIGURACIÓN ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
CALENDAR_ID = os.environ.get("CALENDAR_ID", "")

# --- LÓGICA DE GOOGLE CALENDAR ---
def agendar_en_google(datos_cita):
    try:
        info_servicio = json.loads(os.environ.get("GOOGLE_CREDENTIALS_JSON", "{}"))
        creds = service_account.Credentials.from_service_account_info(
            info_servicio, scopes=['https://www.googleapis.com/auth/calendar']
        )
        service = build('calendar', 'v3', credentials=creds)

        evento = {
            'summary': f"CITA: {datos_cita['nombre']} - {datos_cita['tratamiento']}",
            'location': 'Calle Gran Vía, 42, Madrid',
            'description': f"Tratamiento: {datos_cita['tratamiento']}\nAgendado por el Bot Dental.",
            'start': {'dateTime': datos_cita['inicio'], 'timeZone': 'Europe/Madrid'},
            'end': {'dateTime': datos_cita['fin'], 'timeZone': 'Europe/Madrid'},
        }

        service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        return True
    except Exception as e:
        print(f"Error en Calendar: {e}")
        return False

# --- LÓGICA DE IA ---
def llamar_gemini(historial, extra_prompt=None):
    prompt_sistema = """Eres el asistente de Odontología Sánchez. 
    Tu objetivo es agendar citas pidiendo: Nombre, Tratamiento y Día/Hora.
    Cuando tengas los 3 datos, confirma con: '✅ ¡Cita confirmada! Te esperamos el [día] a las [hora] para [tratamiento].'"""
    
    if extra_prompt: # Usado para extraer datos estructurados
        payload = {"contents": [{"parts": [{"text": extra_prompt}]}]}
    else:
        payload = {
            "system_instruction": {"parts": [{"text": prompt_sistema}]},
            "contents": historial
        }

    r = requests.post(GEMINI_URL, json=payload)
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

def procesar_confirmacion(texto_bot):
    # Pedimos a Gemini que convierta el texto amigable en datos para el calendario
    prompt_extraccion = f"""Extrae los datos de esta confirmación: "{texto_bot}"
    Responde SOLAMENTE un JSON con este formato:
    {{"nombre": "...", "tratamiento": "...", "inicio": "ISO_DATETIME", "fin": "ISO_DATETIME"}}
    Nota: La cita dura 1 hora. Hoy es 2026. Formato ISO: YYYY-MM-DDTHH:MM:SS"""
    
    try:
        respuesta_json = llamar_gemini([], extra_prompt=prompt_extraccion)
        # Limpiar posibles bloques de código markdown
        clean_json = respuesta_json.replace("```json", "").replace("```", "").strip()
        datos = json.loads(clean_json)
        return agendar_en_google(datos)
    except:
        return False

# --- WEBHOOK TWILIO ---
conversaciones = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    numero = request.form.get("From", "")
    mensaje_usuario = request.form.get("Body", "").strip()
    
    if numero not in conversaciones: conversaciones[numero] = []
    conversaciones[numero].append({"role": "user", "parts": [{"text": mensaje_usuario}]})

    try:
        respuesta = llamar_gemini(conversaciones[numero])
        conversaciones[numero].append({"role": "model", "parts": [{"text": respuesta}]})
        
        # Si el bot confirma la cita, la enviamos al calendario
        if "✅ ¡Cita confirmada!" in respuesta:
            procesar_confirmacion(respuesta)

        root = f"<Response><Message>{respuesta}</Message></Response>"
        return Response(root, mimetype="text/xml")
    except Exception:
        return Response("<Response><Message>Error técnico, llámanos.</Message></Response>", mimetype="text/xml")

@app.route("/")
def home(): return "🦷 Bot Dental con Google Calendar Activo."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
