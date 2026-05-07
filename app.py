import os
import time
import requests
from flask import Flask, request, Response

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
)

SYSTEM_PROMPT = """Eres el asistente virtual de Odontología Sánchez, una clínica dental en Madrid.
Tu objetivo es atender a los pacientes de forma amable, recoger sus datos para pedir cita y resolver dudas.

Cuando alguien quiera pedir cita, recoge en orden:
1. Nombre completo
2. Tratamiento que necesita (revisión, blanqueamiento, ortodoncia, implantes, etc.)
3. Día y hora preferida

Una vez tengas los 3 datos confirma así:
"✅ ¡Cita confirmada! Te esperamos el [día] a las [hora] para [tratamiento]. Te llamaremos al número registrado para confirmar. ¡Hasta pronto! 🦷"

Información de la clínica:
- Dirección: Calle Gran Vía, 42, Madrid 28013
- Teléfono: 628 493 012
- Horario: Lunes-Viernes 9:00-21:00 | Sábados 9:00-14:00
- Urgencias: 24 horas, 365 días
- Primera visita: GRATUITA
- Servicios y precios:
  * Ortodoncia invisible: desde 1.500€
  * Blanqueamiento dental: desde 250€
  * Implantes dentales: desde 750€/unidad
  * Carillas de porcelana: desde 350€/unidad
  * Odontopediatría: desde 40€
  * Sedación consciente: desde 100€
- Planes: Básico (primera visita gratis), Mantenimiento Anual (149€/año), Familiar (299€/año hasta 4 personas)

Responde siempre en español, de forma cercana y profesional. Usa emojis con moderación.
Mantén las respuestas cortas (máximo 3-4 líneas).
Nunca inventes datos médicos ni des diagnósticos."""

conversaciones = {}


def twiml_response(texto):
    import xml.etree.ElementTree as ET
    root = ET.Element("Response")
    msg = ET.SubElement(root, "Message")
    msg.text = texto
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")
    return Response(xml_str, mimetype="text/xml")


MENSAJE_ERROR = (
    "Lo siento, estoy teniendo problemas técnicos en este momento. "
    "Por favor llámanos al 628 493 012 o escríbenos a gonzalomansoa@gmail.com. 🦷"
)


def llamar_gemini(historial):
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": historial
    }
    for intento in range(2):
        try:
            r = requests.post(GEMINI_URL, json=payload, timeout=12)
            if r.status_code == 429 and intento == 0:
                time.sleep(3)
                continue
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        except requests.exceptions.Timeout:
            if intento == 0:
                time.sleep(1)
                continue
            raise
    raise Exception("Sin respuesta tras reintentos")


@app.route("/webhook", methods=["POST"])
def webhook():
    numero = request.form.get("From", "")
    mensaje_usuario = request.form.get("Body", "").strip()

    if not mensaje_usuario:
        return twiml_response("")

    if numero not in conversaciones:
        conversaciones[numero] = []

    conversaciones[numero].append({
        "role": "user",
        "parts": [{"text": mensaje_usuario}]
    })

    try:
        texto_respuesta = llamar_gemini(conversaciones[numero])
        conversaciones[numero].append({
            "role": "model",
            "parts": [{"text": texto_respuesta}]
        })
    except Exception:
        conversaciones[numero].pop()
        texto_respuesta = MENSAJE_ERROR

    return twiml_response(texto_respuesta)


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok", "modelo": "gemini-2.5-flash"}, 200


@app.route("/", methods=["GET"])
def home():
    return "🦷 Bot Odontología Sánchez activo."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
