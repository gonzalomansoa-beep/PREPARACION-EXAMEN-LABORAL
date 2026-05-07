import random
import time

PREGUNTAS = [
    {
        "pregunta": "¿Cuál es el periodo de prueba máximo para trabajadores no cualificados según el ET?",
        "opciones": ["1 mes", "2 meses", "3 meses", "6 meses"],
        "respuesta": 1,
        "explicacion": "Art. 14 ET: 2 meses para trabajadores no cualificados, 6 meses para técnicos titulados."
    },
    {
        "pregunta": "¿Qué indemnización corresponde al despido improcedente (contratos desde 12/02/2012)?",
        "opciones": ["20 días/año con límite de 12 mensualidades", "33 días/año con límite de 24 mensualidades", "45 días/año con límite de 42 mensualidades", "25 días/año con límite de 18 mensualidades"],
        "respuesta": 1,
        "explicacion": "Art. 56 ET: 33 días por año de servicio, con un máximo de 24 mensualidades."
    },
    {
        "pregunta": "¿Cuántos días de permiso retribuido tiene el trabajador por matrimonio?",
        "opciones": ["7 días naturales", "15 días naturales", "10 días naturales", "5 días laborables"],
        "respuesta": 1,
        "explicacion": "Art. 37.3.a ET: 15 días naturales por matrimonio."
    },
    {
        "pregunta": "La duración máxima del contrato temporal por circunstancias de la producción es:",
        "opciones": ["6 meses", "12 meses", "18 meses", "24 meses"],
        "respuesta": 0,
        "explicacion": "Art. 15 ET (tras reforma 2021): máximo 6 meses, ampliable a 1 año por convenio colectivo."
    },
    {
        "pregunta": "¿Cuántas horas extraordinarias puede realizar un trabajador al año como máximo?",
        "opciones": ["40 horas", "60 horas", "80 horas", "100 horas"],
        "respuesta": 2,
        "explicacion": "Art. 35.2 ET: el número de horas extraordinarias no podrá ser superior a 80 al año."
    },
    {
        "pregunta": "El salario mínimo interprofesional lo fija:",
        "opciones": ["El Congreso de los Diputados", "El Gobierno por decreto", "El FOGASA", "La negociación colectiva"],
        "respuesta": 1,
        "explicacion": "Art. 27 ET: El Gobierno fijará anualmente el SMI previa consulta con las organizaciones sindicales y empresariales."
    },
    {
        "pregunta": "¿Qué duración tiene la jornada máxima ordinaria de trabajo?",
        "opciones": ["35 horas semanales", "37,5 horas semanales", "40 horas semanales", "42 horas semanales"],
        "respuesta": 2,
        "explicacion": "Art. 34.1 ET: La jornada máxima ordinaria es de 40 horas semanales de trabajo efectivo de promedio en cómputo anual."
    },
    {
        "pregunta": "¿Cuántos días de vacaciones anuales garantiza el ET como mínimo?",
        "opciones": ["22 días laborables", "30 días naturales", "23 días laborables", "28 días naturales"],
        "respuesta": 1,
        "explicacion": "Art. 38 ET: El periodo de vacaciones anuales retribuidas no será inferior a 30 días naturales."
    },
]

def limpiar_pantalla():
    print("\n" + "="*55)

def mostrar_bienvenida():
    print("="*55)
    print("   SIMULADOR DE EXAMEN - DERECHO LABORAL (ET)")
    print("   UNAV - 3º Derecho")
    print("="*55)
    print("Responde las preguntas eligiendo el número (1-4)")
    print("Al final verás tu puntuación y las explicaciones.")
    print("="*55 + "\n")

def hacer_examen(num_preguntas=5):
    preguntas = random.sample(PREGUNTAS, min(num_preguntas, len(PREGUNTAS)))
    aciertos = 0
    resultados = []

    for i, p in enumerate(preguntas, 1):
        limpiar_pantalla()
        print(f"PREGUNTA {i}/{len(preguntas)}")
        print(f"\n{p['pregunta']}\n")

        for j, opcion in enumerate(p['opciones'], 1):
            print(f"  {j}. {opcion}")

        while True:
            try:
                respuesta = int(input("\nTu respuesta (1-4): ")) - 1
                if 0 <= respuesta <= 3:
                    break
                print("Por favor, elige entre 1 y 4.")
            except ValueError:
                print("Introduce un número.")

        es_correcto = respuesta == p['respuesta']
        if es_correcto:
            aciertos += 1
            print("CORRECTO")
        else:
            print(f"INCORRECTO. La correcta era: {p['opciones'][p['respuesta']]}")

        resultados.append((p, respuesta, es_correcto))
        time.sleep(1.2)

    return aciertos, len(preguntas), resultados

def mostrar_resultados(aciertos, total, resultados):
    limpiar_pantalla()
    porcentaje = (aciertos / total) * 100

    print(f"RESULTADO FINAL: {aciertos}/{total} ({porcentaje:.0f}%)\n")

    if porcentaje >= 90:
        print("Excelente. Dominas la materia.")
    elif porcentaje >= 70:
        print("Bien. Repasa los fallos y estaras listo.")
    elif porcentaje >= 50:
        print("Aprobado justo. Necesitas reforzar.")
    else:
        print("Suspendido. A estudiar mas el ET.")

    print("\n--- EXPLICACIONES DE LOS FALLOS ---")
    fallos = [(p, r) for p, r, correcto in resultados if not correcto]

    if not fallos:
        print("Sin fallos. Perfecto.")
    else:
        for p, r in fallos:
            print(f"\nX {p['pregunta']}")
            print(f"  Tu respuesta: {p['opciones'][r]}")
            print(f"  Correcta:     {p['opciones'][p['respuesta']]}")
            print(f"  Fundamento:   {p['explicacion']}")

if __name__ == "__main__":
    mostrar_bienvenida()
    aciertos, total, resultados = hacer_examen(num_preguntas=5)
    mostrar_resultados(aciertos, total, resultados)
