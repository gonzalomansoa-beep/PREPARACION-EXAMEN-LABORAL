import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from google import genai
from google.genai import types

app = Flask(__name__)

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

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


def construir_historial(numero, mensaje_nuevo):
    historial = conversaciones.get(numero, [])
    historial.append(types.Content(role="user", parts=[types.Part(text=mensaje_nuevo)]))
    return historial


@app.route("/webhook", methods=["POST"])
def webhook():
    numero = request.form.get("From", "")
    mensaje_usuario = request.form.get("Body", "").strip()

    if not mensaje_usuario:
        return str(MessagingResponse())

    if numero not in conversaciones:
        conversaciones[numero] = []

    contents = construir_historial(numero, mensaje_usuario)

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        ),
        contents=contents,
    )

    texto_respuesta = response.text

    conversaciones[numero].append(
        types.Content(role="user", parts=[types.Part(text=mensaje_usuario)])
    )
    conversaciones[numero].append(
        types.Content(role="model", parts=[types.Part(text=texto_respuesta)])
    )

    resp = MessagingResponse()
    resp.message(texto_respuesta)
    return str(resp)


@app.route("/", methods=["GET"])
def home():
    return "🦷 Bot Odontología Sánchez activo."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
