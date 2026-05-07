import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from anthropic import Anthropic

app = Flask(__name__)
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Guarda el historial de cada conversación por número de teléfono
conversaciones = {}

SYSTEM_PROMPT = """Eres el asistente virtual de Odontología Sánchez, una clínica dental en Madrid.
Tu objetivo es atender a los pacientes de forma amable, recoger sus datos para pedir cita y resolver dudas.

Cuando alguien quiera pedir cita, recoge en orden:
1. Nombre completo
2. Tratamiento que necesita (revisión, blanqueamiento, ortodoncia, implantes, etc.)
3. Día y hora preferida

Una vez tengas los 3 datos, confirma la cita con un mensaje así:
"✅ ¡Cita confirmada! Te esperamos el [día] a las [hora] para [tratamiento]. Te llamaremos al [número] para confirmar. ¡Hasta pronto! 🦷"

Información de la clínica:
- Dirección: Calle Gran Vía, 42, Madrid
- Teléfono: 628 493 012
- Horario: Lunes-Viernes 9:00-21:00 | Sábados 9:00-14:00
- Urgencias: 24h
- Primera visita: GRATUITA
- Servicios: Ortodoncia invisible, blanqueamiento, implantes, carillas, odontopediatría, sedación

Responde siempre en español, de forma cercana y profesional. Usa emojis con moderación 🦷✨
Si preguntan por precios, diles que depende del caso y que la primera visita es gratuita para valorarlo.
Nunca inventes datos médicos ni des diagnósticos.
Mantén las respuestas cortas (máximo 3-4 líneas)."""


@app.route("/webhook", methods=["POST"])
def webhook():
    numero = request.form.get("From", "")
    mensaje_usuario = request.form.get("Body", "").strip()

    if numero not in conversaciones:
        conversaciones[numero] = []

    conversaciones[numero].append({
        "role": "user",
        "content": mensaje_usuario
    })

    # Limitar historial a últimos 20 mensajes para no pasarse de tokens
    historial = conversaciones[numero][-20:]

    respuesta = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=SYSTEM_PROMPT,
        messages=historial
    )

    texto_respuesta = respuesta.content[0].text

    conversaciones[numero].append({
        "role": "assistant",
        "content": texto_respuesta
    })

    resp = MessagingResponse()
    resp.message(texto_respuesta)
    return str(resp)


@app.route("/", methods=["GET"])
def home():
    return "🦷 Bot de Odontología Sánchez funcionando correctamente."


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
