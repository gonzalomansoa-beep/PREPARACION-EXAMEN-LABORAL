import os
import re
import json
import time
import sqlite3
import logging
import requests
import threading
from datetime import datetime, timedelta
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
GEMINI_MODELS  = ["gemini-2.5-flash", "gemini-2.0-flash"]

def _gemini_url(model):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

CALENDAR_ID       = "548fdbd91d1fe5f545da2d8c0c4cfebbcbf30c749a3527c9b25a79baaf9d25e2@group.calendar.google.com"
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")

GMAIL_USER        = os.environ.get("GMAIL_USER", "gonzalomansoa@gmail.com")
BREVO_API_KEY     = os.environ.get("BREVO_API_KEY", "")

TELEFONO_CLINICA  = "628 493 012"
EMAIL_CLINICA     = "gonzalomansoa@gmail.com"

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
        log.info(f"✅ Evento Calendar: {nombre} | {tratamiento} | {fecha_iso} {hora_iso}")
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

Normas de estilo:
- Responde siempre en español de España
- Mensajes cortos y naturales, máximo 3-4 líneas
- Solo estos emojis: 🦷 ✅ (con moderación)
- Nunca des diagnósticos ni precios exactos como garantía
- En situaciones de urgencia o dolor, prioriza siempre la empatía"""

# ─── Conversaciones persistentes en SQLite ────────────────────────────────────
DB_PATH = "/tmp/conversaciones.db"
_db_lock = threading.Lock()

def _init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS conversaciones (
                numero TEXT PRIMARY KEY,
                historial TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        con.commit()

_init_db()

def conv_get(numero: str) -> list:
    with _db_lock, sqlite3.connect(DB_PATH) as con:
        row = con.execute("SELECT historial, updated_at FROM conversaciones WHERE numero=?", (numero,)).fetchone()
        if not row:
            return []
        # Borrar si la conversación lleva más de 24h sin actividad
        if time.time() - row[1] > 86400:
            con.execute("DELETE FROM conversaciones WHERE numero=?", (numero,))
            con.commit()
            return []
        return json.loads(row[0])

def conv_set(numero: str, historial: list):
    with _db_lock, sqlite3.connect(DB_PATH) as con:
        con.execute(
            "INSERT OR REPLACE INTO conversaciones (numero, historial, updated_at) VALUES (?,?,?)",
            (numero, json.dumps(historial, ensure_ascii=False), time.time())
        )
        con.commit()

def conv_pop_last(numero: str):
    historial = conv_get(numero)
    if historial:
        historial.pop()
        conv_set(numero, historial)


def llamar_gemini(historial: list, system: str = None, timeout: int = 15) -> str:
    payload = {
        "system_instruction": {"parts": [{"text": system or SYSTEM_PROMPT}]},
        "contents": historial,
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 400},
    }
    last_error = None
    for model in GEMINI_MODELS:
        for intento in range(2):
            try:
                r = requests.post(_gemini_url(model), json=payload, timeout=timeout)
                if r.status_code == 429:
                    if intento == 0:
                        time.sleep(3)
                        continue
                    log.warning(f"⚠️  {model} con cuota agotada, probando siguiente modelo...")
                    last_error = "429"
                    break
                r.raise_for_status()
                # Concatena todos los parts de texto (ignora partes de pensamiento vacías)
                parts = r.json()["candidates"][0]["content"]["parts"]
                texto = "".join(
                    p.get("text", "") for p in parts
                    if p.get("text", "").strip() and not p.get("thought", False)
                ).strip()
                if not texto:
                    raise ValueError("Respuesta vacía de Gemini")
                log.info(f"✅ Gemini [{model}] respondió ({len(texto)} chars)")
                return texto
            except requests.exceptions.Timeout:
                log.warning(f"⚠️  {model} timeout intento {intento+1}")
                if intento == 0:
                    continue
                last_error = "timeout"
                break
            except Exception as exc:
                log.error(f"❌ {model} error: {exc}")
                last_error = str(exc)
                break
    raise RuntimeError(f"Gemini no disponible: {last_error}")


def extraer_datos_cita(texto_confirmacion: str, historial: list) -> dict | None:
    hoy = datetime.now().strftime("%A %d de %B de %Y")
    prompt = f"""Hoy es {hoy}. Analiza esta confirmación de cita dental y el historial.
Devuelve UNICAMENTE un objeto JSON valido:
{{
  "nombre": "nombre completo del paciente",
  "tratamiento": "tipo de tratamiento",
  "fecha_iso": "YYYY-MM-DD",
  "hora_iso": "HH:MM"
}}

Confirmacion: {texto_confirmacion}
Historial: {json.dumps(historial[-6:], ensure_ascii=False)}

Solo JSON, sin markdown."""
    try:
        respuesta = llamar_gemini(
            [{"role": "user", "parts": [{"text": prompt}]}],
            system="Extractor de datos. Devuelves solo JSON válido.",
            timeout=10,
        )
        limpio = respuesta.strip().strip("`").replace("json\n", "").replace("```", "").strip()
        return json.loads(limpio)
    except Exception as exc:
        log.error(f"Error extrayendo datos de cita: {exc}")
        return None


# ─── Respuestas inteligentes de fallback ──────────────────────────────────────
def respuesta_whatsapp_fallback(mensaje: str) -> str:
    """Respuesta contextual cuando Gemini no está disponible."""
    msg = mensaje.lower()

    urgencia = any(w in msg for w in ["urgencia", "urgente", "dolor", "duele", "accidente", "roto", "rota", "sangra", "hinchado"])
    cita     = any(w in msg for w in ["cita", "reservar", "pedir", "quiero", "cuando", "disponible", "hueco"])
    precio   = any(w in msg for w in ["precio", "cuanto", "coste", "cuesta", "tarifa", "presupuesto"])
    implante = any(w in msg for w in ["implante", "implantes", "diente perdido", "falta", "faltan"])
    ortod    = any(w in msg for w in ["ortodoncia", "brackets", "invisalign", "dientes torcidos", "alineadores"])
    blanq    = any(w in msg for w in ["blanquear", "blanqueamiento", "whiten", "color", "amarillo"])
    nino     = any(w in msg for w in ["niño", "niña", "hijo", "hija", "infantil", "pediatria"])
    saludo   = any(w in msg for w in ["hola", "buenas", "buenos", "hello", "info", "información"])

    if urgencia:
        return (
            "¡Hola! Entiendo que tienes una urgencia. En Odontología Sánchez atendemos urgencias 24h. "
            "Llámanos ahora al 628 493 012 y te atendemos de inmediato. 🦷"
        )
    if implante and precio:
        return (
            "¡Hola! Los implantes dentales en nuestra clínica tienen un precio orientativo desde 750€/unidad. "
            "El proceso es muy cómodo, con anestesia local para que no sientas nada. "
            "¿Quieres que te hagamos una valoración gratuita? Dime tu nombre y te reservo una visita. 🦷"
        )
    if ortod and precio:
        return (
            "¡Hola! Invisalign (ortodoncia invisible) tiene un precio orientativo desde 1.500€, "
            "dependiendo del caso. Es ideal para adultos porque es casi imperceptible. "
            "¿Te apetece una primera visita gratuita para ver qué necesitas? Dime tu nombre. 🦷"
        )
    if blanq:
        return (
            "¡Hola! El blanqueamiento dental profesional está desde 250€ y los resultados se notan desde la primera sesión. "
            "¿Quieres que te reservemos una consulta gratuita para valorarlo? Dime tu nombre y cuándo te viene bien. 🦷"
        )
    if nino:
        return (
            "¡Hola! Atendemos a los más pequeños desde 40€. Tenemos un equipo especializado en odontopediatría "
            "y sabemos cómo hacer que la visita al dentista sea una experiencia tranquila para ellos. "
            "¿Quieres pedir cita? Dime el nombre del niño y cuándo os viene mejor. 🦷"
        )
    if precio:
        return (
            "¡Hola! Estos son nuestros precios orientativos:\n"
            "• Revisión + limpieza: desde 60€\n"
            "• Implantes: desde 750€/unidad\n"
            "• Invisalign: desde 1.500€\n"
            "• Blanqueamiento: desde 250€\n"
            "• Carillas: desde 350€\n\n"
            "La primera visita es siempre GRATUITA. ¿Te reservo una? 🦷"
        )
    if cita:
        return (
            "¡Hola! Con mucho gusto te reservo una cita. "
            "Estamos disponibles lunes a viernes de 9:00 a 21:00 y sábados de 9:00 a 14:00. "
            "¿Me dices tu nombre y qué día te viene mejor? 🦷"
        )
    if saludo:
        return (
            "¡Hola! Bienvenido a Odontología Sánchez. Soy Carmen y estoy aquí para ayudarte. "
            "La primera visita es siempre gratuita. ¿En qué puedo ayudarte hoy? 🦷"
        )
    return (
        "¡Hola! Soy Carmen de Odontología Sánchez. Puedo ayudarte con información sobre tratamientos, "
        "precios o reservar una cita (primera visita gratuita). ¿Qué necesitas? 🦷"
    )


def email_fallback_inteligente(nombre: str, tratamiento: str, mensaje: str) -> str:
    """Email personalizado cuando Gemini no está disponible."""
    msg = mensaje.lower()
    trat = tratamiento.lower() if tratamiento else ""

    miedo    = any(w in msg for w in ["miedo", "nervios", "nervioso", "nerviosa", "asusta", "duele", "dolor", "doloroso"])
    precio_q = any(w in msg for w in ["precio", "cuanto", "cuesta", "coste", "cuánto"])
    urgente  = any(w in msg for w in ["urgencia", "urgente", "roto", "rota", "accidente", "sangra"])
    nino     = any(w in msg for w in ["niño", "niña", "hijo", "hija", "infantil", "pequeño"])

    apertura = f"Hola {nombre},"

    if urgente:
        cuerpo = (
            f"{apertura}\n\n"
            f"He leído tu mensaje y entiendo que es urgente. Por favor, llámanos ahora mismo al "
            f"628 493 012 — atendemos urgencias las 24 horas y nos ocuparemos de ti enseguida.\n\n"
            f"Si prefieres, también puedes contestar a este email y te respondo de inmediato.\n\n"
            f"Un abrazo,\n\n"
            f"Carmen\n"
            f"Odontología Sánchez · Gran Vía 42, Madrid\n"
            f"📞 628 493 012 | Primera visita gratuita"
        )
        return cuerpo

    if miedo and ("implante" in trat or "implante" in msg):
        detalle = (
            "Entiendo perfectamente que el proceso de un implante pueda dar algo de respeto, "
            "pero te cuento: se hace siempre con anestesia local, así que durante la intervención "
            "no sentirás nada. Muchos de nuestros pacientes se sorprenden de lo cómodo que resulta. "
            "La recuperación suele ser muy llevadera, con alguna molestia los primeros días que se controla bien con analgésicos."
        )
    elif miedo:
        detalle = (
            "Es muy normal sentir algo de nervios antes de una visita dental, y lo entendemos perfectamente. "
            "En nuestra clínica trabajamos especialmente para que cada paciente se sienta tranquilo y cómodo. "
            "Si lo necesitas, ofrecemos sedación consciente para que la experiencia sea lo más relajada posible."
        )
    elif "implante" in trat or "implante" in msg:
        detalle = (
            "Sobre los implantes, te cuento que en nuestra clínica el precio orientativo es desde 750€ por unidad. "
            "El proceso se hace con anestesia local y es mucho más cómodo de lo que la gente imagina. "
            "La recuperación completa lleva unos meses, pero en ese tiempo llevarás una corona provisional para que puedas hacer vida normal."
        )
    elif "invisalign" in trat or "ortodoncia" in trat or "invisalign" in msg or "ortodoncia" in msg:
        detalle = (
            "Sobre la ortodoncia invisible, te cuento que Invisalign es una opción estupenda: "
            "los alineadores son prácticamente invisibles y se pueden quitar para comer. "
            "El precio orientativo está desde 1.500€ dependiendo del caso. "
            "La primera visita es gratuita y sin compromiso, así que podemos valorar exactamente qué necesitas."
        )
    elif "blanquea" in trat or "blanquea" in msg:
        detalle = (
            "El blanqueamiento dental profesional es un tratamiento muy sencillo y los resultados se notan muchísimo. "
            "El precio orientativo está desde 250€ y el efecto dura bastante tiempo si se cuidan bien los dientes. "
            "En la primera visita gratuita te explicamos todo en detalle."
        )
    elif nino:
        detalle = (
            "Tenemos un equipo especializado en odontopediatría que sabe muy bien cómo hacer "
            "que los peques se sientan seguros y tranquilos. "
            "La primera visita es gratuita y sin compromiso."
        )
    elif precio_q:
        detalle = (
            "Para darte un presupuesto exacto necesitamos hacer una valoración, "
            "pero te puedo decir que nuestros precios son muy competitivos y "
            "trabajamos con facilidades de pago. La primera visita es siempre gratuita."
        )
    else:
        detalle = (
            "Estaremos encantados de atenderte y resolver todas tus dudas en persona. "
            "La primera visita es siempre gratuita y sin ningún compromiso."
        )

    cuerpo = (
        f"{apertura}\n\n"
        f"Gracias por escribirnos. {detalle}\n\n"
        f"Si quieres dar el siguiente paso, puedes llamarnos al 628 493 012 o contestar a este mismo email "
        f"y te reservamos una cita en el horario que mejor te venga.\n\n"
        f"¡Hasta pronto!\n\n"
        f"Carmen\n"
        f"Odontología Sánchez · Gran Vía 42, Madrid\n"
        f"📞 628 493 012 | Primera visita gratuita"
    )
    return cuerpo


# ─── Webhook WhatsApp ──────────────────────────────────────────────────────────
@app.route("/webhook", methods=["POST"])
def webhook():
    numero          = request.form.get("From", "desconocido")
    mensaje_usuario = request.form.get("Body", "").strip()

    if not mensaje_usuario:
        return twiml_response("")

    log.info(f"📱 [{numero}] → {mensaje_usuario[:80]}")

    historial = conv_get(numero)
    historial.append({"role": "user", "parts": [{"text": mensaje_usuario}]})
    if len(historial) > 40:
        historial = historial[-40:]
    conv_set(numero, historial)

    try:
        texto_respuesta = llamar_gemini(historial)
        historial.append({"role": "model", "parts": [{"text": texto_respuesta}]})
        conv_set(numero, historial)

        if "✅ ¡Cita confirmada!" in texto_respuesta:
            log.info(f"🗓️  Cita detectada para {numero} — extrayendo datos...")
            datos = extraer_datos_cita(texto_respuesta, historial)
            if datos and datos.get("fecha_iso") and datos.get("hora_iso"):
                crear_evento_calendario(
                    datos.get("nombre", "Paciente"),
                    datos.get("tratamiento", "Consulta"),
                    datos["fecha_iso"],
                    datos["hora_iso"],
                )

        log.info(f"📤 [{numero}] ← {texto_respuesta[:80]}")

    except Exception as exc:
        log.warning(f"⚠️  Gemini no disponible para {numero}: {exc} — usando fallback inteligente")
        conv_pop_last(numero)
        texto_respuesta = respuesta_whatsapp_fallback(mensaje_usuario)

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

    prompt_email = f"""Eres Carmen, recepcionista de Odontología Sánchez, clínica dental premium en Madrid.
Has recibido este mensaje de un paciente a través de la web:

Nombre: {nombre}
Tratamiento de interés: {tratamiento or "No especificado"}
Mensaje del paciente: {mensaje}

Escribe una respuesta de email PERSONALIZADA en español de España. Reglas estrictas:

1. LEE el mensaje con atención. Si pregunta precio → da orientación concreta. Si tiene miedo o dolor → muestra empatía primero. Si es urgencia → prioriza llamada. Nunca ignores lo que dice.
2. Empieza con "Hola {nombre}," seguido de una frase cálida que refleje EXACTAMENTE lo que ha contado.
3. Responde a su consulta con información útil y específica al tratamiento que menciona.
4. Invítale a llamar al 628 493 012 o contestar este email.
5. Despídete de forma cercana.
6. Firma exactamente:

Carmen
Odontología Sánchez · Gran Vía 42, Madrid
📞 628 493 012 | Primera visita gratuita

PROHIBIDO: No menciones IA, automatización, bot, sistema ni nada parecido. Eres Carmen, una persona real.
Tono: email personal y cercano. NUNCA suenes a plantilla. Máximo 10 líneas."""

    try:
        respuesta = llamar_gemini(
            [{"role": "user", "parts": [{"text": prompt_email}]}],
            system="Eres Carmen, recepcionista humana de una clínica dental de élite. Escribes emails personales, cálidos y útiles. NUNCA mencionas IA ni automatización.",
            timeout=15,
        )
        log.info(f"✅ Email IA generado para {nombre}")
    except Exception as exc:
        log.warning(f"⚠️  Gemini no disponible para email — usando fallback inteligente: {exc}")
        respuesta = email_fallback_inteligente(nombre, tratamiento, mensaje)

    def _enviar_emails():
        enviar_email(
            EMAIL_CLINICA,
            f"Nuevo contacto web: {nombre} — {tratamiento or 'General'}",
            f"Nombre: {nombre}\nEmail: {email}\nTelefono: {telefono}\nTratamiento: {tratamiento}\n\nMensaje:\n{mensaje}\n\n{'─'*40}\nRespuesta enviada al paciente:\n\n{respuesta}",
        )
        exito = enviar_email(email, "Hemos recibido tu consulta — Odontología Sánchez", respuesta)
        if exito:
            log.info(f"✅ Respuesta enviada a {email}")
        else:
            log.warning(f"⚠️  No se pudo enviar email a {email}")

    threading.Thread(target=_enviar_emails, daemon=True).start()
    return jsonify({"ok": True})


def enviar_email(destino: str, asunto: str, cuerpo: str) -> bool:
    if not BREVO_API_KEY:
        log.warning("BREVO_API_KEY no configurado")
        return False
    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": BREVO_API_KEY, "Content-Type": "application/json"},
            json={
                "sender": {"name": "Odontología Sánchez", "email": GMAIL_USER},
                "to": [{"email": destino}],
                "subject": asunto,
                "textContent": cuerpo,
            },
            timeout=10,
        )
        resp.raise_for_status()
        log.info(f"📧 Email → {destino}: {asunto}")
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
        "modelos":  GEMINI_MODELS,
        "calendar": "conectado" if cal_ok else "pendiente",
        "email":    "ok" if BREVO_API_KEY else "pendiente",
    }, 200


@app.route("/", methods=["GET"])
def home():
    return "🦷 Odontologia Sanchez — Sistema activo."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
