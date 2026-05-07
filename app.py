import os
import json
import time
import logging
import smtplib
import requests
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, Response, jsonify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response

@app.route("/contacto", methods=["OPTIONS"])
def contacto_options():
    return "", 204

# ─── Credenciales ─────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-2.0-flash"
GEMINI_URL     = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)

CALENDAR_ID       = "548fdbd91d1fe5f545da2d8c0c4cfebbcbf30c749a3527c9b25a79baaf9d25e2@group.calendar.google.com"
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

GMAIL_USER         = os.environ.get("GMAIL_USER", "gonzalomansoa@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

TELEFONO_CLINICA = "628 493 012"
EMAIL_CLINICA    = "gonzalomansoa@gmail.com"

# ─── Google Calendar ──────────────────────────────────────────────────────────
_cal_service = None

def get_calendar_service():
    global _cal_service
    if _cal_service:
        return _cal_service
    if not GOOGLE_CREDS_JSON:
        return None
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_service_account_info(
            json.loads(GOOGLE_CREDS_JSON),
            scopes=["https://www.googleapis.com/auth/calendar"],
        )
        _cal_service = build("calendar", "v3", credentials=creds)
        log.info("Google Calendar conectado correctamente")
        return _cal_service
    except Exception as exc:
        log.error(f"Error conectando Google Calendar: {exc}")
        return None


def crear_evento_calendario(nombre, tratamiento, fecha_iso, hora_iso):
    service = get_calendar_service()
    if not service:
        log.warning("Calendar no disponible — cita guardada solo en WhatsApp")
        return False
    try:
        inicio = datetime.fromisoformat(f"{fecha_iso}T{hora_iso}:00")
        fin    = inicio + timedelta(hours=1)
        evento = {
            "summary":     f"Cita: {nombre} — {tratamiento}",
            "description": f"Paciente: {nombre}\nTratamiento: {tratamiento}\nReservado via WhatsApp Bot",
            "start":       {"dateTime": inicio.isoformat(), "timeZone": "Europe/Madrid"},
            "end":         {"dateTime": fin.isoformat(),    "timeZone": "Europe/Madrid"},
            "reminders":   {"useDefault": False, "overrides": [{"method": "email", "minutes": 60}]},
        }
        service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        log.info(f"✅ Evento Calendar creado: {nombre} | {tratamiento} | {fecha_iso} {hora_iso}")
        return True
    except Exception as exc:
        log.error(f"Error creando evento Calendar: {exc}")
        return False


# ─── Gemini ───────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Eres Carmen, la recepcionista virtual de Odontología Sánchez, la clínica dental de referencia en Madrid.

Tu personalidad: Eres cálida, empática, cercana y muy profesional. Hablas como una persona real que atiende WhatsApp, no como un sistema automático. Cuando conoces el nombre del paciente, lo usas. Si alguien menciona dolor, urgencia o nervios, primero transmites calma y comprensión antes de pedir ningún dato.

IMPORTANTE: Nunca digas que eres una IA, un bot o un sistema automático. Si te preguntan, di que eres la recepcionista virtual de la clínica disponible 24h.

Para concertar cita, reúne de forma natural estos datos:
1. Nombre completo del paciente
2. Qué tratamiento o consulta necesita
3. Qué día y hora prefiere (Lun-Vie 9:00-21:00, Sáb 9:00-14:00)

Cuando tengas los tres datos, confirma EXACTAMENTE con este formato (es obligatorio usar ✅ al inicio):
"✅ ¡Cita confirmada! Te esperamos el [día completo, fecha] a las [hora] para tu [tratamiento], [nombre]. Te enviaremos confirmación por este mismo número. ¡Hasta pronto! 🦷"

Información de la clínica:
- Nombre oficial: Odontología Sánchez — Excelencia Dental
- Dirección: Calle Gran Vía, 42, Madrid 28013
- Teléfono: 628 493 012
- Email: gonzalomansoa@gmail.com
- Horario: Lunes a Viernes 9:00-21:00 | Sábados 9:00-14:00
- Urgencias: atención 24h, 365 días al año
- Primera visita: siempre GRATUITA

Servicios y precios orientativos:
• Revisión y limpieza bucodental: desde 60€
• Ortodoncia invisible (Invisalign): desde 1.500€
• Blanqueamiento dental profesional: desde 250€
• Implantes dentales: desde 750€/unidad
• Carillas de porcelana: desde 350€/unidad
• Odontopediatría (niños): desde 40€
• Sedación consciente: desde 100€
• Endodoncia: desde 180€

Planes anuales:
• Plan Básico: primera visita gratis
• Plan Mantenimiento: 149€/año (revisiones + limpiezas)
• Plan Familiar: 299€/año hasta 4 miembros

Normas de estilo:
- Responde siempre en español de España
- Mensajes cortos y naturales, máximo 3-4 líneas
- Solo estos emojis: 🦷 ✅ (con moderación)
- Nunca des diagnósticos ni precios exactos como garantía
- En situaciones de urgencia o dolor, prioriza siempre la empatía"""

conversaciones: dict = {}


def llamar_gemini(historial: list, system: str = None, timeout: int = 12) -> str:
    payload = {
        "system_instruction": {"parts": [{"text": system or SYSTEM_PROMPT}]},
        "contents": historial,
        "generationConfig": {"temperature": 0.75, "maxOutputTokens": 350},
    }
    for intento in range(2):
        try:
            r = requests.post(GEMINI_URL, json=payload, timeout=timeout)
            if r.status_code == 429 and intento == 0:
                time.sleep(2)
                continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except requests.exceptions.Timeout:
            if intento == 0:
                continue
            raise
    raise RuntimeError("Gemini sin respuesta tras reintentos")


def extraer_datos_cita(texto_confirmacion: str, historial: list) -> dict | None:
    hoy = datetime.now().strftime("%A %d de %B de %Y")
    prompt = f"""Hoy es {hoy} (mayo 2026). Analiza esta confirmación de cita dental y el historial de conversación.
Devuelve UNICAMENTE un objeto JSON valido con estos campos exactos:
{{
  "nombre": "nombre completo del paciente",
  "tratamiento": "tipo de tratamiento solicitado",
  "fecha_iso": "YYYY-MM-DD (fecha exacta calculada desde hoy)",
  "hora_iso": "HH:MM (formato 24h)"
}}

Confirmacion: {texto_confirmacion}
Historial reciente: {json.dumps(historial[-8:], ensure_ascii=False)}

Responde SOLO con el JSON. Sin markdown, sin explicaciones."""
    try:
        respuesta = llamar_gemini(
            [{"role": "user", "parts": [{"text": prompt}]}],
            system="Extractor de datos. Devuelves solo JSON valido sin ningun texto adicional.",
            timeout=10,
        )
        limpio = respuesta.strip().strip("`").replace("json\n", "").replace("```", "").strip()
        datos = json.loads(limpio)
        log.info(f"Datos cita extraidos: {datos}")
        return datos
    except Exception as exc:
        log.error(f"Error extrayendo datos de cita: {exc}")
        return None


# ─── Webhook WhatsApp ──────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    numero          = request.form.get("From", "desconocido")
    mensaje_usuario = request.form.get("Body", "").strip()

    if not mensaje_usuario:
        return twiml_response("")

    log.info(f"📱 [{numero}] → {mensaje_usuario[:80]}")

    if numero not in conversaciones:
        conversaciones[numero] = []

    conversaciones[numero].append({"role": "user", "parts": [{"text": mensaje_usuario}]})

    try:
        texto_respuesta = llamar_gemini(conversaciones[numero])
        conversaciones[numero].append({"role": "model", "parts": [{"text": texto_respuesta}]})

        if "✅ ¡Cita confirmada!" in texto_respuesta:
            log.info(f"🗓️  Cita detectada para {numero} — extrayendo datos...")
            datos = extraer_datos_cita(texto_respuesta, conversaciones[numero])
            if datos and datos.get("fecha_iso") and datos.get("hora_iso"):
                crear_evento_calendario(
                    datos.get("nombre", "Paciente"),
                    datos.get("tratamiento", "Consulta"),
                    datos["fecha_iso"],
                    datos["hora_iso"],
                )

        log.info(f"📤 [{numero}] ← {texto_respuesta[:80]}")

    except Exception as exc:
        log.error(f"❌ Error procesando {numero}: {exc}")
        conversaciones[numero].pop()
        texto_respuesta = (
            f"Disculpa, tengo un pequeño problema técnico ahora mismo. "
            f"Puedes llamarnos directamente al {TELEFONO_CLINICA} y te atendemos enseguida. "
            f"¡Perdona las molestias! 🦷"
        )

    return twiml_response(texto_respuesta)


# ─── Formulario web ───────────────────────────────────────────────────────────
@app.route("/contacto", methods=["POST"])
def contacto():
    data        = request.get_json(silent=True) or request.form.to_dict()
    nombre      = data.get("nombre", "").strip()
    email       = data.get("email", "").strip()
    telefono    = data.get("telefono", "").strip()
    tratamiento = data.get("tratamiento", "").strip()
    mensaje     = data.get("mensaje", "").strip()

    if not email or not nombre or not mensaje:
        return jsonify({"ok": False, "error": "Faltan campos obligatorios"}), 400

    log.info(f"📧 Formulario web: {nombre} ({email}) — {tratamiento or 'sin especificar'}")

    prompt_email = f"""Eres Carmen, recepcionista de Odontología Sánchez (clínica dental premium en Madrid).
Un paciente ha enviado este mensaje desde nuestra web:

Nombre: {nombre}
Email del paciente: {email}
Telefono: {telefono or "No facilitado"}
Tratamiento de interes: {tratamiento or "No especificado"}
Mensaje: {mensaje}

Redacta una respuesta de email breve (maximo 6 lineas), calida y profesional en español de España.
- Empieza directamente, sin "Estimado/a" ni saludos genericos
- Usa el nombre del paciente de forma natural
- Responde especificamente a su consulta
- Invitale a llamar al 628 493 012 o responder el email para concertar cita
- Firma: Carmen · Odontologia Sanchez · 628 493 012
- Tono: cercano, experto, confiable. NO uses plantillas ni frases genericas."""

    try:
        respuesta_ia = llamar_gemini(
            [{"role": "user", "parts": [{"text": prompt_email}]}],
            system="Redactas emails breves, calidos y personalizados para una clinica dental premium.",
            timeout=12,
        )
    except Exception as exc:
        log.error(f"Error generando respuesta IA para email: {exc}")
        respuesta_ia = (
            f"Hola {nombre},\n\nMuchas gracias por contactar con Odontologia Sanchez.\n\n"
            f"Hemos recibido tu consulta y nos pondremos en contacto contigo en breve. "
            f"Si necesitas atencion urgente, llamanos al 628 493 012.\n\n"
            f"Carmen · Odontologia Sanchez · 628 493 012"
        )

    # Aviso interno
    enviar_email(
        EMAIL_CLINICA,
        f"Nuevo contacto web: {nombre} — {tratamiento or 'General'}",
        f"Nombre: {nombre}\nEmail: {email}\nTelefono: {telefono}\nTratamiento: {tratamiento}\n\nMensaje:\n{mensaje}\n\n{'─'*40}\nRespuesta IA enviada:\n{respuesta_ia}",
    )

    # Auto-respuesta al paciente
    exito = enviar_email(email, "Hemos recibido tu consulta — Odontologia Sanchez", respuesta_ia)
    if exito:
        log.info(f"✅ Auto-respuesta IA enviada a {email}")
    else:
        log.warning(f"⚠️  No se pudo enviar email a {email} (configura GMAIL_APP_PASSWORD)")

    return jsonify({"ok": True})


def enviar_email(destino: str, asunto: str, cuerpo: str) -> bool:
    if not GMAIL_APP_PASSWORD:
        log.warning("GMAIL_APP_PASSWORD no configurado — email omitido")
        return False
    try:
        msg = MIMEMultipart()
        msg["From"]    = f"Odontologia Sanchez <{GMAIL_USER}>"
        msg["To"]      = destino
        msg["Subject"] = asunto
        msg.attach(MIMEText(cuerpo, "plain", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            srv.send_message(msg)
        log.info(f"📧 Email enviado → {destino}: {asunto}")
        return True
    except Exception as exc:
        log.error(f"❌ Email fallido → {destino}: {exc}")
        return False


# ─── Utilidades ───────────────────────────────────────────────────────────────
def twiml_response(texto: str) -> Response:
    import xml.etree.ElementTree as ET
    root = ET.Element("Response")
    ET.SubElement(root, "Message").text = texto
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")
    return Response(xml_str, mimetype="text/xml")


@app.route("/health", methods=["GET"])
def health():
    cal_ok = get_calendar_service() is not None
    return {
        "status":   "ok",
        "modelo":   GEMINI_MODEL,
        "calendar": "conectado" if cal_ok else "pendiente GOOGLE_CREDENTIALS_JSON",
        "email":    "configurado" if GMAIL_APP_PASSWORD else "pendiente GMAIL_APP_PASSWORD",
    }, 200


@app.route("/", methods=["GET"])
def home():
    return "🦷 Odontologia Sanchez — Sistema activo."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
