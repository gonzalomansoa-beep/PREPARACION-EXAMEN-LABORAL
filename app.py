import os
import json
import requests
import time
from flask import Flask, request, Response
from google.oauth2 import service_account
from googleapiclient.discovery import build

app = Flask(__name__)

# --- CONFIGURACIÓN REQUERIDA ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Usando exactamente la versión que pediste
MODELO = "gemini-2.5-flash" 
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent?key={GEMINI_API_KEY}"
CALENDAR_ID = os.environ.get("CALENDAR_ID", "")

def agendar_en_google(datos_cita):
    try:
        print(f"DEBUG: Intentando conectar con Google Calendar ID: {CALENDAR_ID}")
        creds_raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
        
        if not creds_raw:
            print("❌ ERROR CRÍTICO: La variable GOOGLE_CREDENTIALS_JSON está VACÍA en Railway.")
            return False
            
        info_servicio = json.loads(creds_raw)
        creds = service_account.Credentials.from_service_account_info(
            info_servicio, scopes=['https://www.googleapis.com/auth/calendar']
        )
        service = build('calendar', 'v3', credentials=creds)

        evento = {
            'summary': f"CITA: {datos_cita.get('nombre')} - {datos_cita.get('tratamiento')}",
            'description': 'Agendado por Agente IA Dental.',
            'start': {'dateTime': datos_cita['inicio'], 'timeZone': 'Europe/Madrid'},
            'end': {'dateTime': datos_cita['fin'], 'timeZone': 'Europe/Madrid'},
        }

        print(f"DEBUG: Enviando JSON a Google: {json.dumps(evento)}")
        res = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        print(f"✅ ¡CITA CREADA EXITOSAMENTE! ID de evento: {res.get('id')}")
        return True
    except Exception as e:
        print(f"❌ FALLO EN GOOGLE CALENDAR: {str(e)}")
        return False

def llamar_gemini(historial, prompt_especifico=None):
    if prompt_especifico:
        # Modo extracción de datos
        payload = {"contents": [{"role": "user", "parts": [{"text": prompt_especifico}]}]}
    else:
        # Modo conversación normal
        sys_prompt = "Eres el asistente de Odontología Sánchez. Pide: Nombre, Tratamiento y Día/Hora. Sé breve. Cuando los tengas, di: ✅ ¡Cita confirmada!"
        payload = {
            "system_instruction": {"parts": [{"text": sys_prompt}]},
            "contents": historial
        }

    print(f"DEBUG: Llamando a {MODELO}...")
    r = requests.post(GEMINI_URL, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

@app.route("/webhook", methods=["POST"])
def webhook():
    numero = request.form.get("From", "")
    mensaje = request.form.get("Body", "").strip()
    
    if numero not in conversaciones: conversaciones[numero] = []
    conversaciones[numero].append({"role": "user", "parts": [{"text": mensaje}]})

    try:
        # 1. Hablar con el paciente
        respuesta = llamar_gemini(conversaciones[numero])
        conversaciones[numero].append({"role": "model", "parts": [{"text": respuesta}]})
        
        # 2. Si detecta confirmación, dispara el calendario
        if "✅ ¡Cita confirmada!" in respuesta:
            print("🚀 DETECTADA CONFIRMACIÓN. Iniciando proceso de agenda...")
            
            # Pedimos a Gemini 2.5 que extraiga el JSON de la conversación
            prompt_json = (
                f"Analiza esta respuesta: '{respuesta}'. "
                "Extrae los datos. Hoy es 2026. "
                "Responde ÚNICAMENTE un objeto JSON con este formato exacto: "
                '{"nombre": "...", "tratamiento": "...", "inicio": "YYYY-MM-DDTHH:MM:SS", "fin": "YYYY-MM-DDTHH:MM:SS"}'
            )
            
            try:
                raw_json = llamar_gemini([], prompt_especifico=prompt_json)
                print(f"DEBUG: IA devolvió para el calendario: {raw_json}")
                
                # Limpiar la respuesta de la IA por si pone marcas de código
                clean_json = raw_json.replace("```json", "").replace("```", "").strip()
                datos = json.loads(clean_json)
                
                # Llamar a la función de Google
                agendar_en_google(datos)
            except Exception as ex:
                print(f"⚠️ Error procesando los datos de la cita: {ex}")

        return Response(f"<Response><Message>{respuesta}</Message></Response>", mimetype="text/xml")
    
    except Exception as e:
        print(f"🔥 ERROR GENERAL: {e}")
        return Response("<Response><Message>Error técnico, por favor llámanos. 🦷</Message></Response>", mimetype="text/xml")

conversaciones = {}

@app.route("/")
def home(): return f"Bot Dental Activo - Modelo: {MODELO}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
