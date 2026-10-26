import base64
import os
import re
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from google import genai
from google.genai import types

app = Flask(__name__)
CORS(app)

# ==========================================
# UTILIDAD: Limpia respuesta de Gemini
# ==========================================
def clean_ai_response(text: str) -> str:
    """Limpia la respuesta de la IA eliminando sintaxis Markdown y convirtiéndola a HTML."""
    if not text:
        return ""
    text = re.sub(r'```(?:html|json|markdown|python|javascript)?\n?', '', text)
    text = re.sub(r'```', '', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
    text = re.sub(r'^[-*_]{3,}$', '<hr>', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*[-*+]\s+', '<li>', text, flags=re.MULTILINE)
    text = re.sub(r'\n\n+', '</p><p>', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', '<br>', text)
    if not text.startswith('<p>') and not text.startswith('<li>') and not text.startswith('<h'):
        text = '<p>' + text + '</p>'
    text = re.sub(r'<p>\s*</p>', '', text)
    text = re.sub(r'<li>\s*</li>', '', text)
    text = text.replace('<p><li>', '<li>').replace('</li></p>', '</li>')
    text = re.sub(r'(<li>.*?</li>)(?=\s*<li>)', r'\1', text)
    text = re.sub(r'(<li>.*?</li>)+', lambda m: '<ul>' + m.group(0) + '</ul>', text, flags=re.DOTALL)
    return text.strip()

# ==========================================
# RUTAS ESTÁTICAS
# ==========================================

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# ==========================================
# CONFIGURACIÓN DE LA IA
# ==========================================
API_KEY = os.environ.get('GEMINI_API_KEY', 'AQ.Ab8RN6Kt05_1MX5YvZEWqw_MTwVzxf0ZsIcpNnaAyHQ4SXbjIA')
cliente = genai.Client(api_key=API_KEY)

# ==========================================
# 1. RUTA: GENERAR PLAN NUTRICIONAL INDIVIDUAL
# ==========================================
@app.route('/generar-plan', methods=['POST'])
def generar_plan():
    datos = request.json
    if not datos:
        return jsonify({"exito": False, "error": "No se recibieron datos."}), 400

    peso         = datos.get('peso')
    region       = datos.get('region')
    objetivo     = datos.get('objetivo')
    health_history = datos.get('health_history', 'Ninguno')
    imc          = datos.get('imc')

    # --- Validaciones ---
    if peso is None or peso == '':
        return jsonify({"exito": False, "error": "El campo 'peso' es obligatorio."}), 400
    try:
        peso = float(peso)
        if peso < 30 or peso > 200:
            return jsonify({"exito": False, "error": "El peso debe estar entre 30 y 200 kg."}), 400
    except (ValueError, TypeError):
        return jsonify({"exito": False, "error": "El peso debe ser un número válido."}), 400

    if not region or region not in ['Costa', 'Sierra', 'Selva']:
        return jsonify({"exito": False, "error": "La región debe ser: Costa, Sierra o Selva."}), 400

    objetivos_validos = ['Ganar masa muscular', 'Perder grasa', 'Mantener peso']
    if not objetivo or objetivo not in objetivos_validos:
        objetivo = 'Mantener peso'

    # --- Lógica de salud preventiva ---
    logica_salud = ""
    if health_history == 'Diabetes':
        logica_salud = (
            "ADVERTENCIA CLÍNICA — DIABETES: Prioriza OBLIGATORIAMENTE ingredientes con bajo índice glucémico: "
            "kiwicha, sacha inchi, tarwi, maca, quinua. Elimina azúcares añadidos y harinas refinadas. "
            "Incluye una sección '⚠️ Nota para Diabéticos' en el menú."
        )
    elif health_history == 'Hipertensión':
        logica_salud = "Reduce el sodio al mínimo, evita embutidos y prioriza alimentos frescos."
    elif health_history == 'Obesidad':
        logica_salud = "Ajusta las porciones para déficit calórico moderado, enfocándote en vegetales y proteínas magras."

    if imc:
        try:
            if float(imc) > 30:
                logica_salud += " Ajusta las porciones para un déficit calórico moderado."
        except (ValueError, TypeError):
            pass

    prompt = f"""
Actúa como un nutricionista experto en la biodiversidad peruana.
Diseña un menú de 1 día (Desayuno, Almuerzo, Snack, Cena) para una persona de {peso}kg.
OBLIGATORIO: Los alimentos e ingredientes deben ser ESTRICTAMENTE de la región {region} del Perú.
Objetivo nutricional: {objetivo}.
{logica_salud}
Devuelve la respuesta estructurada usando ÚNICAMENTE HTML puro (usa <h3> para cada comida y <ul><li> para los alimentos).
NO incluyas markdown, NO uses bloques de código.
"""
    try:
        respuesta = cliente.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
        )
        html_limpio = clean_ai_response(respuesta.text)
        return jsonify({"exito": True, "html": html_limpio})
    except Exception as e:
        error_str = str(e)
        codigo = 503 if ('503' in error_str or 'overloaded' in error_str.lower()) else 500
        return jsonify({"exito": False, "error": error_str}), codigo

# ==========================================
# 2. RUTA: CHAT MULTIMODAL (FOTO + TEXTO)
# ==========================================
@app.route('/chat', methods=['POST'])
def chat_interactivo():
    datos = request.json
    pregunta    = datos.get('pregunta', '')
    imagen_b64  = datos.get('imagen')
    mime_type   = datos.get('mime_type')

    prompt = "Eres el nutricionista de MIKHUCHIYNCA. "
    contenidos = []

    if imagen_b64 and mime_type:
        prompt += ("Analiza la foto adjunta de esta comida. Describe sus ingredientes, "
                   "estima las calorías y dinos si es adecuado para una dieta saludable. ")
        imagen_bytes = base64.b64decode(imagen_b64)
        parte_imagen = types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type)
        contenidos.append(parte_imagen)

    if pregunta:
        prompt += f"Además, el usuario pregunta: {pregunta}"
    elif not imagen_b64:
        prompt += "El usuario no envió ni foto ni texto. Pídele amablemente que envíe su consulta."

    contenidos.append(prompt)

    try:
        respuesta = cliente.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=contenidos,
        )
        texto_limpio = clean_ai_response(respuesta.text)
        return jsonify({"exito": True, "respuesta": texto_limpio})
    except Exception as e:
        return jsonify({"exito": False, "error": str(e)}), 500

# ==========================================
# 3. RUTA: PLAN FAMILIAR
# ==========================================
@app.route('/generar-plan-familiar', methods=['POST'])
def generar_plan_familiar():
    datos = request.json
    if not datos:
        return jsonify({"exito": False, "error": "No se recibieron datos."}), 400

    miembros = datos.get('miembros', [])
    if not miembros or not isinstance(miembros, list) or len(miembros) == 0:
        return jsonify({"exito": False, "error": "La lista de miembros está vacía."}), 400
    if len(miembros) > 8:
        return jsonify({"exito": False, "error": "Máximo 8 miembros por plan familiar."}), 400

    # Validación numérica
    for m in miembros:
        try:
            if float(m.get('peso', 0)) <= 0:
                return jsonify({"exito": False, "error": f"El peso de '{m.get('nombre', 'un miembro')}' debe ser mayor a 0."}), 400
            if float(m.get('edad', 0)) <= 0:
                return jsonify({"exito": False, "error": f"La edad de '{m.get('nombre', 'un miembro')}' debe ser mayor a 0."}), 400
        except (ValueError, TypeError):
            return jsonify({"exito": False, "error": "Los datos numéricos son inválidos."}), 400

    descripcion_miembros = ""
    hay_diabetes = False
    for i, m in enumerate(miembros):
        nombre       = m.get('nombre', f'Miembro {i+1}')
        peso         = m.get('peso', '?')
        edad         = m.get('edad', '?')
        estatura     = m.get('estatura', '?')
        antecedentes = m.get('antecedentes', 'Ninguno')
        if antecedentes == 'Diabetes':
            hay_diabetes = True
        descripcion_miembros += f"\n  - {nombre}: {edad} años, {peso} kg, {estatura} cm, Antecedentes: {antecedentes}."

    advertencia_diabetes = ""
    if hay_diabetes:
        advertencia_diabetes = (
            "\nADVERTENCIA CRÍTICA — DIABETES DETECTADA: Para los miembros con Diabetes, es OBLIGATORIO "
            "priorizar ingredientes andinos con BAJO ÍNDICE GLUCÉMICO: kiwicha, sacha inchi, tarwi, maca, quinua. "
            "Elimina azúcares añadidos. En la lista de compras marca con [🌿 Bajo IG] los ingredientes seguros."
        )

    nombres_lista = ", ".join([m.get('nombre', f'Miembro {i+1}') for i, m in enumerate(miembros)])

    prompt = f"""
Actúas como un COMITÉ MÉDICO DE NUTRICIONISTAS PERUANOS CERTIFICADOS.
Diseña un plan nutricional familiar completo para {len(miembros)} personas.

INTEGRANTES:
{descripcion_miembros}
{advertencia_diabetes}

INSTRUCCIONES — RESPONDE ÚNICAMENTE EN HTML PURO, SIN MARKDOWN:

PARTE 1 — LISTA DE COMPRAS CONSOLIDADA para toda la semana ({nombres_lista}).
Agrupa por categorías con <h3> y <ul><li>. Incluye cantidades aproximadas.

PARTE 2 — MENÚ DIARIO INDIVIDUAL para CADA INTEGRANTE (Desayuno, Almuerzo, Snack, Cena).
Usa ingredientes peruanos. Adapta a los antecedentes de salud. Estructura con <h3>Nombre</h3> y <ul><li>.

FORMATO DE RESPUESTA — JSON estricto sin bloques de código:
{{"lista_compras_html": "<h3>...</h3><ul>...</ul>", "planes": [{{"nombre": "...", "menu_html": "<h3>...</h3><ul>...</ul>"}}]}}
"""

    try:
        respuesta = cliente.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
        )
        texto_raw   = respuesta.text
        texto_limpio = re.sub(r'```(?:json|html)?\n?', '', texto_raw)
        texto_limpio = re.sub(r'```', '', texto_limpio).strip()

        try:
            datos_ia = json.loads(texto_limpio)
            lista_compras_html = clean_ai_response(datos_ia.get('lista_compras_html', ''))
            planes_resultado = []
            for i, plan in enumerate(datos_ia.get('planes', [])):
                miembro_ref = miembros[i] if i < len(miembros) else {}
                planes_resultado.append({
                    "nombre": plan.get('nombre', miembro_ref.get('nombre', f'Miembro {i+1}')),
                    "html":   clean_ai_response(plan.get('menu_html', ''))
                })
            return jsonify({"exito": True, "lista_compras": lista_compras_html, "planes": planes_resultado})
        except (json.JSONDecodeError, ValueError):
            html_fallback = clean_ai_response(texto_limpio)
            return jsonify({"exito": True, "lista_compras": "", "planes": [], "html": html_fallback})

    except Exception as e:
        error_str = str(e)
        codigo = 503 if ('503' in error_str or 'overloaded' in error_str.lower()) else 500
        return jsonify({"exito": False, "error": error_str}), codigo

# ==========================================
# ARRANQUE
# ==========================================
if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
