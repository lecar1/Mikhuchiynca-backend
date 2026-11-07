import base64
import os
import re
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types
from models import db, User

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mikhuchiynca-secret-key-2026')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///mikhuchiynca.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

with app.app_context():
    db.create_all()

# ==========================================
# RUTAS DE AUTENTICACIÓN Y PERFIL DE USUARIO
# ==========================================
@app.route('/api/register', methods=['POST'])
def api_register():
    datos = request.json or {}
    email = datos.get('email', '').strip().lower()
    password = datos.get('password', '')
    peso = datos.get('peso')
    estatura = datos.get('estatura')
    edad = datos.get('edad')

    if not email or not password:
        return jsonify({"exito": False, "error": "Email y contraseña son obligatorios."}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"exito": False, "error": "El correo ya está registrado."}), 400

    try:
        nuevo_usuario = User(
            email=email,
            password_hash=generate_password_hash(password),
            peso=float(peso) if peso not in [None, ''] else None,
            estatura=float(estatura) if estatura not in [None, ''] else None,
            edad=int(edad) if edad not in [None, ''] else None
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        login_user(nuevo_usuario, remember=True)
        return jsonify({
            "exito": True,
            "mensaje": "Usuario registrado exitosamente.",
            "usuario": nuevo_usuario.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({"exito": False, "error": f"Error al registrar: {str(e)}"}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    datos = request.json or {}
    email = datos.get('email', '').strip().lower()
    password = datos.get('password', '')

    if not email or not password:
        return jsonify({"exito": False, "error": "Email y contraseña son obligatorios."}), 400

    usuario = User.query.filter_by(email=email).first()
    if not usuario or not check_password_hash(usuario.password_hash, password):
        return jsonify({"exito": False, "error": "Credenciales inválidas. Verifica tu correo y contraseña."}), 401

    login_user(usuario, remember=True)
    return jsonify({
        "exito": True,
        "mensaje": "Sesión iniciada exitosamente.",
        "usuario": usuario.to_dict()
    })

@app.route('/api/logout', methods=['GET', 'POST'])
def api_logout():
    logout_user()
    return jsonify({"exito": True, "mensaje": "Sesión cerrada exitosamente."})

@app.route('/api/perfil', methods=['GET', 'POST'])
def api_perfil():
    if not current_user.is_authenticated:
        return jsonify({"exito": False, "error": "No has iniciado sesión."}), 401

    if request.method == 'GET':
        return jsonify({
            "exito": True,
            "perfil": current_user.to_dict()
        })

    # POST: Actualizar peso, estatura, edad
    datos = request.json or {}
    try:
        if 'peso' in datos and datos['peso'] not in [None, '']:
            current_user.peso = float(datos['peso'])
        if 'estatura' in datos and datos['estatura'] not in [None, '']:
            current_user.estatura = float(datos['estatura'])
        if 'edad' in datos and datos['edad'] not in [None, '']:
            current_user.edad = int(datos['edad'])

        db.session.commit()
        return jsonify({
            "exito": True,
            "mensaje": "Perfil actualizado exitosamente.",
            "perfil": current_user.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"exito": False, "error": f"Error al actualizar perfil: {str(e)}"}), 500

# ==========================================
# FUNCIÓN PARA LIMPIAR LA RESPUESTA DE LA IA
# ==========================================
def clean_ai_response(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'```(?:html|json|markdown|python|javascript)?\n?', '', text)
    text = re.sub(r'```', '', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n\n+', '</p><p>', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', '<br>', text)
    
    if not text.startswith('<p>') and not text.startswith('<h') and not text.startswith('<ul>'):
        text = '<p>' + text + '</p>'
    return text.strip()

# ==========================================
# RUTAS PARA SERVIR EL HTML Y CSS
# ==========================================
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

# ==========================================
# CONFIGURACIÓN DE LA IA
# ==========================================
# Tu clave oficial de Google AI Studio
API_KEY = "AQ.Ab8RN6Kt05_1MX5YvZEWqw_MTwVzxf0ZsIcpNnaAyHQ4SXbjIA" 
cliente = genai.Client(api_key=API_KEY)

# Función auxiliar para llamar a la IA con reintentos automáticos
def generar_con_reintentos(prompt):
    modelos = ['gemini-3.5-flash', 'gemini-3.8-flash', 'gemini-1.5-flash']
    ultimo_error = None
    for modelo in modelos:
        try:
            print(f"Intentando con modelo: {modelo}...")
            respuesta = cliente.models.generate_content(
                model=modelo,
                contents=prompt,
            )
            return respuesta.text
        except Exception as e:
            print(f"Fallo con {modelo}: {e}")
            ultimo_error = e
            continue
    raise Exception(f"Todos los modelos fallaron. Último error: {ultimo_error}")

# ==========================================
# 1. RUTA PARA GENERAR EL PLAN INDIVIDUAL (DIETA + GYM)
# ==========================================
@app.route('/generar-plan', methods=['POST'])
def generar_plan():
    datos = request.json
    if not datos:
        return jsonify({"exito": False, "error": "No se recibieron datos."}), 400

    # Extracción de variables (Todas aseguradas para evitar NameError)
    peso = datos.get('peso')
    estatura = datos.get('estatura')
    edad = datos.get('edad')
    genero = datos.get('genero', 'No especificado')
    region = datos.get('region', 'Costa')
    objetivo = datos.get('objetivo', 'Mantener peso')
    health_history = datos.get('health_history', 'Ninguno')
    imc = datos.get('imc')

    if not peso or not estatura or not edad:
        return jsonify({"exito": False, "error": "Faltan datos obligatorios (peso, estatura o edad)."}), 400

    logica_salud = ""
    if health_history == 'Diabetes':
        logica_salud = "Prioriza ingredientes con bajo índice glucémico, evita azúcares añadidos y usa superalimentos peruanos (kiwicha, sacha inchi)."
    elif health_history == 'Hipertensión':
        logica_salud = "Reduce el sodio al mínimo, evita embutidos y prioriza alimentos frescos."

    prompt = f"""
    Actúa como un equipo de expertos: un Nutricionista y un Entrenador Personal (Coach).
    
    Datos del usuario:
    - Peso: {peso} kg
    - Estatura: {estatura} cm
    - Edad: {edad} años
    - Género: {genero}
    - Objetivo: {objetivo}
    - Antecedentes de salud: {health_history} ({logica_salud})

    CRITERIO OBLIGATORIO DE ECONOMÍA:
    El usuario tiene presupuesto limitado. ESTÁ PROHIBIDO recomendar alimentos costosos o importados (salmón, arándanos, carnes premium).
    Usa alimentos económicos y locales de Perú: menestres (lentejas, frejoles), huevos, pollo, pescado local (bonito, jurel), avena, plátano, papa, camote, quinua y kiwicha.

    Genera un informe completo en HTML puro (usa <h3> y <ul>) dividido en DOS SECCIONES:

    <h2>PARTE 1: Plan Nutricional Peruano</h2>
    Menú de 1 día (Desayuno, Almuerzo, Snack, Cena) adaptado a su objetivo y a la región {region}. Respeta el criterio de economía.

    <h2>PARTE 2: Rutina de Entrenamiento</h2>
    Rutina de 3 a 4 días adaptada a su objetivo ({objetivo}).
    - Si es "Ganar masa muscular": hipertrofia (pesas, 8-12 repeticiones).
    - Si es "Perder grasa": combina pesas con cardio.
    Incluye días, ejercicios, series y repeticiones.

    IMPORTANTE: Devuelve únicamente HTML puro. No incluyas markdown.
    """
    
    try:
        texto_respuesta = generar_con_reintentos(prompt)
        html_limpio = clean_ai_response(texto_respuesta)
        return jsonify({"exito": True, "html": html_limpio})
    except Exception as e:
        print(f"ERROR INDIVIDUAL: {e}")
        return jsonify({"exito": False, "error": "La IA de Google está teniendo problemas. Intenta de nuevo en unos minutos."}), 500

# ==========================================
# 2. RUTA PARA EL PLAN FAMILIAR
# ==========================================
@app.route('/generar-plan-familiar', methods=['POST'])
def generar_plan_familiar():
    datos = request.json
    if not datos:
        return jsonify({"exito": False, "error": "No se recibieron datos."}), 400

    miembros = datos.get('miembros', [])
    if not miembros:
        return jsonify({"exito": False, "error": "La lista de miembros está vacía."}), 400

    descripcion_miembros = ""
    for i, m in enumerate(miembros):
        descripcion_miembros += f"\n- {m.get('nombre', f'Miembro {i+1}')}: {m.get('edad', '?')} años, {m.get('peso', '?')} kg, {m.get('estatura', '?')} cm. Antecedentes: {m.get('antecedentes', 'Ninguno')}."

    prompt = f"""
    Actúa como un equipo de nutricionistas peruanos.
    Diseña un plan familiar para:
    {descripcion_miembros}

    CRITERIO OBLIGATORIO DE ECONOMÍA: Usa ingredientes baratos de mercados locales (menestras, huevos, pollo, pescado local).
    Genera una lista de compras semanal y luego un menú diario (Desayuno, Almuerzo, Cena) para cada miembro.
    Usa HTML puro (h3, ul, li).
    """

    try:
        texto_respuesta = generar_con_reintentos(prompt)
        html_limpio = clean_ai_response(texto_respuesta)
        return jsonify({"exito": True, "html": html_limpio})
    except Exception as e:
        print(f"ERROR FAMILIAR: {e}")
        return jsonify({"exito": False, "error": "La IA está saturada. Intenta de nuevo."}), 500

# ==========================================
# 3. RUTA PARA EL CHAT MULTIMODAL
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
        prompt += "Analiza la foto adjunta de esta comida. Describe ingredientes y calorías. "
        imagen_bytes = base64.b64decode(imagen_b64)
        parte_imagen = types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type)
        contenidos.append(parte_imagen)
        
    if pregunta:
        prompt += f"El usuario pregunta: {pregunta}"
        
    contenidos.append(prompt)
    
    try:
        # Para el chat, usamos el modelo más rápido directamente
        respuesta = cliente.models.generate_content(
            model='gemini-3.5-flash', 
            contents=contenidos,
        )
        texto_limpio = clean_ai_response(respuesta.text)
        return jsonify({"exito": True, "respuesta": texto_limpio})
    except Exception as e:
        print(f"ERROR CHAT: {e}")
        return jsonify({"exito": False, "error": "El chat está en mantenimiento. Intenta pronto."}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
