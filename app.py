import base64
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types

app = Flask(__name__)
CORS(app)

# Tu clave oficial AQ...
API_KEY = "AQ.Ab8RN6Kt05_1MX5YvZEWqw_MTwVzxf0ZsIcpNnaAyHQ4SXbjIA"
cliente = genai.Client(api_key=API_KEY)

# ==========================================
# 1. RUTA PARA GENERAR EL PLAN NUTRICIONAL
# ==========================================
@app.route('/generar-plan', methods=['POST'])
def generar_plan():
    datos = request.json
    region = datos.get('region', 'Costa')
    peso = datos.get('peso', 70)
    objetivo = datos.get('objetivo', 'Mantener peso')
    
    prompt = f"""
    Actúa como un nutricionista experto en la biodiversidad peruana. 
    Diseña un menú de 1 día (Desayuno, Almuerzo, Snack, Cena) para una persona de {peso}kg. 
    OBLIGATORIO: Los alimentos e ingredientes deben ser ESTRICTAMENTE de la región {region} del Perú. 
    Objetivo: {objetivo}. 
    Devuelve la respuesta estructurada usando únicamente HTML puro (usa <h3> y <strong>). No incluyas markdown.
    """
    try:
        # Usamos el modelo ligero para evitar el tráfico 503
        respuesta = cliente.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt,
        )
        html_limpio = respuesta.text.replace('```html', '').replace('```', '').strip()
        return jsonify({"exito": True, "html": html_limpio})
    except Exception as e:
        return jsonify({"exito": False, "error": str(e)}), 500

# ==========================================
# 2. RUTA PARA EL CHAT MULTIMODAL (FOTO + TEXTO)
# ==========================================
@app.route('/chat', methods=['POST'])
def chat_interactivo():
    datos = request.json
    pregunta = datos.get('pregunta', '')
    imagen_b64 = datos.get('imagen')
    mime_type = datos.get('mime_type')
    
    prompt = "Eres el nutricionista de MIKHUCHIYNCA. "
    contenidos = []
    
    if imagen_b64 and mime_type:
        prompt += "Analiza la foto adjunta de esta comida. Describe sus ingredientes, estima las calorías y dinos si es adecuado para una dieta saludable. "
        imagen_bytes = base64.b64decode(imagen_b64)
        parte_imagen = types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type)
        contenidos.append(parte_imagen)
        
    if pregunta:
        prompt += f"Además, el usuario pregunta: {pregunta}"
    elif not imagen_b64:
        prompt += "El usuario no envió ni foto ni texto. Pídele amablemente que envíe su consulta."
        
    contenidos.append(prompt)
    
    try:
        # Usamos el modelo ligero para evitar el tráfico 503
        respuesta = cliente.models.generate_content(
            model='gemini-3.1-flash-lite', 
            contents=contenidos,
        )
        texto_limpio = respuesta.text.replace('**', '').replace('*', '•').strip()
        return jsonify({"exito": True, "respuesta": texto_limpio})
    except Exception as e:
        print(f"Error en chat visual: {e}")
        return jsonify({"exito": False, "error": str(e)}), 500

if __name__ == '__main__':
    # host='0.0.0.0' permite que luego lo abras desde tu teléfono
    app.run(host='0.0.0.0', port=5000, debug=True)
