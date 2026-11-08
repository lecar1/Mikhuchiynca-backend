import base64
import hmac
import html as html_module
import os
import re
import json
import secrets
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types
from sqlalchemy import event
from sqlalchemy.engine import Engine
from models import db, User, PlanHistory

app = Flask(__name__)

# En producción define SECRET_KEY en el entorno. Si no existe, se genera una
# clave aleatoria por proceso (las sesiones se invalidan al reiniciar).
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    print("ADVERTENCIA: define SECRET_KEY en el entorno para sesiones persistentes y seguras.")

app.config['SECRET_KEY'] = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///mikhuchiynca.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Cookies de sesión endurecidas
usa_https = os.environ.get('HTTPS', '0') == '1'
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=usa_https,
    REMEMBER_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SAMESITE='Lax',
    REMEMBER_COOKIE_SECURE=usa_https,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    REMEMBER_COOKIE_DURATION=timedelta(days=7),
    MAX_CONTENT_LENGTH=12 * 1024 * 1024,  # 12 MB, suficiente para una foto
)

# CORS cerrado por defecto. Solo se abre si defines CORS_ORIGINS explícitamente.
origenes_cors = [origen.strip() for origen in os.environ.get('CORS_ORIGINS', '').split(',') if origen.strip()]
if origenes_cors:
    CORS(app, resources={r"/api/*": {"origins": origenes_cors}}, supports_credentials=True)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"exito": False, "error": "No has iniciado sesión."}), 401


# Exigir claves foráneas en SQLite (evita registros huérfanos)
@event.listens_for(Engine, "connect")
def activar_claves_foraneas(dbapi_connection, _connection_record):
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        pass


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None


with app.app_context():
    db.create_all()

    # El archivo SQLite solo debe ser legible por el propietario del proceso.
    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
        try:
            ruta_db = db.engine.url.database
            if ruta_db and os.path.exists(ruta_db):
                os.chmod(ruta_db, 0o600)
        except Exception as error:
            print(f"No se pudo ajustar el permiso de la base de datos: {error}")


# ==========================================
# SEGURIDAD: CSRF, CABECERAS Y LÍMITES
# ==========================================
def obtener_csrf_token():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return token


@app.route('/api/csrf', methods=['GET'])
def api_csrf():
    return jsonify({"exito": True, "csrf_token": obtener_csrf_token()})


@app.before_request
def proteger_csrf():
    """Exige un token CSRF en toda petición que modifique datos."""
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None

    rutas_protegidas = (
        request.path.startswith('/api/')
        or request.path in ('/generar-plan', '/generar-plan-familiar', '/chat')
    )
    if not rutas_protegidas:
        return None

    esperado = session.get('csrf_token')
    recibido = request.headers.get('X-CSRF-Token', '')
    if not esperado or not recibido or not hmac.compare_digest(str(esperado), str(recibido)):
        return jsonify({
            "exito": False,
            "error": "Token de seguridad inválido o vencido. Recarga la página e inténtalo de nuevo."
        }), 403

    return None


@app.after_request
def cabeceras_seguridad(respuesta):
    respuesta.headers['X-Content-Type-Options'] = 'nosniff'
    respuesta.headers['X-Frame-Options'] = 'DENY'
    respuesta.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    respuesta.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=(self)'
    respuesta.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    if usa_https:
        respuesta.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    if request.path.startswith('/api/'):
        respuesta.headers['Cache-Control'] = 'no-store'

    return respuesta


# Límite de peticiones en memoria (por IP). Suficiente para una sola instancia.
_LIMITES = {}
_LIMITES_LOCK = threading.Lock()


def _ip_cliente():
    return request.remote_addr or 'desconocido'


def permitir_peticion(clave, maximo, ventana_segundos):
    ahora = time.monotonic()
    with _LIMITES_LOCK:
        if len(_LIMITES) > 5000:
            for k in list(_LIMITES.keys()):
                _LIMITES[k] = [t for t in _LIMITES[k] if ahora - t < ventana_segundos]
                if not _LIMITES[k]:
                    del _LIMITES[k]

        marcas = [t for t in _LIMITES.get(clave, []) if ahora - t < ventana_segundos]
        if len(marcas) >= maximo:
            _LIMITES[clave] = marcas
            return False
        marcas.append(ahora)
        _LIMITES[clave] = marcas
        return True


def respuesta_limite():
    return jsonify({
        "exito": False,
        "error": "Demasiados intentos. Espera unos minutos y vuelve a intentarlo."
    }), 429


# Hash de relleno para igualar tiempos cuando el correo no existe.
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_hex(16))
PATRON_EMAIL = re.compile(r'^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$')


def validar_credenciales(email, password):
    if not email or not password:
        return "Email y contraseña son obligatorios."
    if len(email) > 120 or not PATRON_EMAIL.match(email):
        return "Ingresa un correo electrónico válido."
    if len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if len(password) > 128:
        return "La contraseña es demasiado larga."
    return None


# ==========================================
# RUTAS DE AUTENTICACIÓN Y PERFIL DE USUARIO
# ==========================================
@app.route('/api/register', methods=['POST'])
def api_register():
    if not permitir_peticion(f"register:{_ip_cliente()}", 10, 3600):
        return respuesta_limite()

    datos = request.json or {}
    email = str(datos.get('email', '')).strip().lower()
    password = datos.get('password', '')
    peso = datos.get('peso')
    estatura = datos.get('estatura')
    edad = datos.get('edad')

    error_credenciales = validar_credenciales(email, password)
    if error_credenciales:
        return jsonify({"exito": False, "error": error_credenciales}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"exito": False, "error": "El correo ya está registrado."}), 400

    try:
        nuevo_usuario = User(
            email=email,
            password_hash=generate_password_hash(password),
            peso=numero_seguro(peso, 20, 400),
            estatura=numero_seguro(estatura, 80, 260),
            edad=int(numero_seguro(edad, 10, 120)) if numero_seguro(edad, 10, 120) is not None else None
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        login_user(nuevo_usuario, remember=True)
        session.permanent = True
        return jsonify({
            "exito": True,
            "mensaje": "Usuario registrado exitosamente.",
            "usuario": nuevo_usuario.to_dict()
        }), 201
    except Exception:
        db.session.rollback()
        return jsonify({"exito": False, "error": "No se pudo crear la cuenta. Inténtalo de nuevo."}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    if not permitir_peticion(f"login:{_ip_cliente()}", 10, 300):
        return respuesta_limite()

    datos = request.json or {}
    email = str(datos.get('email', '')).strip().lower()
    password = datos.get('password', '')

    if not email or not password:
        return jsonify({"exito": False, "error": "Email y contraseña son obligatorios."}), 400
    if len(email) > 120 or len(password) > 128:
        return jsonify({"exito": False, "error": "Credenciales inválidas. Verifica tu correo y contraseña."}), 401

    if not permitir_peticion(f"login-email:{email}", 6, 300):
        return respuesta_limite()

    usuario = User.query.filter_by(email=email).first()
    hash_a_verificar = usuario.password_hash if usuario else DUMMY_PASSWORD_HASH
    password_valida = check_password_hash(hash_a_verificar, password)

    if not usuario or not password_valida:
        return jsonify({"exito": False, "error": "Credenciales inválidas. Verifica tu correo y contraseña."}), 401

    login_user(usuario, remember=True)
    session.permanent = True
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
    if not permitir_peticion(f"perfil:{current_user.id}", 30, 60):
        return respuesta_limite()

    datos = request.json or {}
    try:
        if 'peso' in datos and datos['peso'] not in [None, '']:
            valor = numero_seguro(datos['peso'], 20, 400)
            if valor is None:
                return jsonify({"exito": False, "error": "Peso fuera de rango."}), 400
            current_user.peso = valor
        if 'estatura' in datos and datos['estatura'] not in [None, '']:
            valor = numero_seguro(datos['estatura'], 80, 260)
            if valor is None:
                return jsonify({"exito": False, "error": "Estatura fuera de rango."}), 400
            current_user.estatura = valor
        if 'edad' in datos and datos['edad'] not in [None, '']:
            valor = numero_seguro(datos['edad'], 10, 120)
            if valor is None:
                return jsonify({"exito": False, "error": "Edad fuera de rango."}), 400
            current_user.edad = int(valor)

        db.session.commit()
        return jsonify({
            "exito": True,
            "mensaje": "Perfil actualizado exitosamente.",
            "perfil": current_user.to_dict()
        })
    except Exception:
        db.session.rollback()
        return jsonify({"exito": False, "error": "No se pudo actualizar el perfil."}), 500

# ==========================================
# HISTORIAL DE PLANES (solo del usuario dueño)
# ==========================================
def guardar_plan_en_historial(tipo, titulo, resumen, html_plan, objetivos=None):
    """Guarda un plan solo si hay sesión. Nunca acepta user_id del cliente."""
    if not current_user.is_authenticated or not html_plan:
        return None

    try:
        registro = PlanHistory(
            user_id=current_user.id,
            tipo='familiar' if tipo == 'familiar' else 'individual',
            titulo=texto_seguro(titulo, 150) or 'Plan nutricional',
            resumen=texto_seguro(resumen, 350),
            html=html_plan[:MAX_HTML_PLAN],
            objetivos_json=(
                json.dumps(objetivos, ensure_ascii=False)[:10_000]
                if objetivos else None
            ),
        )
        db.session.add(registro)
        db.session.commit()

        # Retención: máximo 100 planes por usuario.
        ids_antiguos = [
            fila.id for fila in PlanHistory.query
            .filter_by(user_id=current_user.id)
            .order_by(PlanHistory.creado_en.desc(), PlanHistory.id.desc())
            .offset(100)
            .all()
        ]
        if ids_antiguos:
            PlanHistory.query.filter(
                PlanHistory.user_id == current_user.id,
                PlanHistory.id.in_(ids_antiguos)
            ).delete(synchronize_session=False)
            db.session.commit()

        return registro
    except Exception as error:
        db.session.rollback()
        print(f"ERROR GUARDANDO HISTORIAL: {error}")
        return None


@app.route('/api/historial', methods=['GET'])
@login_required
def api_historial_listar():
    if not permitir_peticion(f"historial:{current_user.id}", 120, 60):
        return respuesta_limite()

    pagina = request.args.get('pagina', 1, type=int) or 1
    pagina = max(1, min(pagina, 10_000))

    paginacion = (
        PlanHistory.query
        .filter_by(user_id=current_user.id)
        .order_by(PlanHistory.creado_en.desc(), PlanHistory.id.desc())
        .paginate(page=pagina, per_page=20, error_out=False)
    )

    return jsonify({
        "exito": True,
        "planes": [plan.to_dict() for plan in paginacion.items],
        "pagina": paginacion.page,
        "total": paginacion.total,
        "paginas": paginacion.pages,
        "hay_mas": paginacion.has_next,
    })


@app.route('/api/historial/<int:plan_id>', methods=['GET'])
@login_required
def api_historial_detalle(plan_id):
    if not permitir_peticion(f"historial-detalle:{current_user.id}", 120, 60):
        return respuesta_limite()

    # El filtro por user_id es la barrera de aislamiento entre cuentas.
    plan = PlanHistory.query.filter_by(id=plan_id, user_id=current_user.id).first()
    if not plan:
        return jsonify({"exito": False, "error": "Plan no encontrado."}), 404

    datos = plan.to_dict(incluir_html=True)
    datos['html'] = sanear_html_ia(datos.get('html', ''))
    return jsonify({"exito": True, "plan": datos})


@app.route('/api/historial/<int:plan_id>', methods=['DELETE'])
@login_required
def api_historial_eliminar(plan_id):
    if not permitir_peticion(f"historial-borrar:{current_user.id}", 60, 60):
        return respuesta_limite()

    plan = PlanHistory.query.filter_by(id=plan_id, user_id=current_user.id).first()
    if not plan:
        return jsonify({"exito": False, "error": "Plan no encontrado."}), 404

    try:
        db.session.delete(plan)
        db.session.commit()
        return jsonify({"exito": True, "mensaje": "Plan eliminado."})
    except Exception:
        db.session.rollback()
        return jsonify({"exito": False, "error": "No se pudo eliminar el plan."}), 500

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
# SANITIZACIÓN DEL HTML GENERADO POR LA IA
# ==========================================
ETIQUETAS_PERMITIDAS = {
    'p', 'br', 'hr', 'h2', 'h3', 'h4', 'ul', 'ol', 'li',
    'strong', 'b', 'em', 'i', 'u', 'blockquote', 'small',
    'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div'
}
ETIQUETAS_VOID = {'br', 'hr'}
ETIQUETAS_PELIGROSAS = {
    'script', 'style', 'iframe', 'object', 'embed', 'svg', 'math',
    'template', 'noscript', 'form', 'input', 'button', 'link', 'meta', 'base'
}
MAX_HTML_PLAN = 300_000


class _SanitizadorHTML(HTMLParser):
    """Deja solo etiquetas seguras sin atributos y elimina scripts/estilos."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []
        self.pila = []
        self.omitir = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ETIQUETAS_PELIGROSAS:
            self.omitir += 1
            return
        if self.omitir:
            return
        if tag in ETIQUETAS_PERMITIDAS:
            if tag in ETIQUETAS_VOID:
                self.partes.append(f'<{tag}>')
            else:
                self.pila.append(tag)
                self.partes.append(f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if not self.omitir and tag in ETIQUETAS_PERMITIDAS and tag in ETIQUETAS_VOID:
            self.partes.append(f'<{tag}>')

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ETIQUETAS_PELIGROSAS:
            if self.omitir:
                self.omitir -= 1
            return
        if self.omitir:
            return
        if tag in ETIQUETAS_PERMITIDAS and tag not in ETIQUETAS_VOID and tag in self.pila:
            while self.pila:
                actual = self.pila.pop()
                self.partes.append(f'</{actual}>')
                if actual == tag:
                    break

    def handle_data(self, data):
        if not self.omitir:
            self.partes.append(html_module.escape(data, quote=False))

    def resultado(self):
        while self.pila:
            self.partes.append(f'</{self.pila.pop()}>')
        return ''.join(self.partes)


def sanear_html_ia(texto):
    if not texto:
        return ''
    texto = str(texto)[:MAX_HTML_PLAN]
    sanitizador = _SanitizadorHTML()
    try:
        sanitizador.feed(texto)
        sanitizador.close()
        return sanitizador.resultado()
    except Exception as error:
        print(f"ERROR SANITIZANDO HTML: {error}")
        return ''


# ==========================================
# CÁLCULOS NUTRICIONALES (PREVIOS A LA IA)
# ==========================================
ACTIVIDADES_VALIDAS = (1.2, 1.375, 1.55, 1.725, 1.9)

DESCRIPCION_ACTIVIDAD = {
    1.2: 'sedentario (poco o ningún ejercicio)',
    1.375: 'ligero (ejercicio 1-3 días por semana)',
    1.55: 'moderado (ejercicio 3-5 días por semana)',
    1.725: 'intenso (ejercicio 6-7 días por semana)',
    1.9: 'muy intenso (entrenamiento 2 veces al día)',
}

def normalizar_texto(valor):
    """Minúsculas y sin tildes, para comparar textos de forma tolerante."""
    if valor is None:
        return ''
    texto = str(valor).strip().lower()
    return ''.join(
        caracter for caracter in unicodedata.normalize('NFD', texto)
        if unicodedata.category(caracter) != 'Mn'
    )

def texto_seguro(valor, max_longitud=200):
    """Limpia y recorta texto del usuario antes de insertarlo en un prompt."""
    texto = re.sub(r'\s+', ' ', str(valor or '')).strip()
    return texto[:max_longitud]

def numero_seguro(valor, minimo, maximo, defecto=None):
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return defecto
    if numero < minimo or numero > maximo:
        return defecto
    return numero

def logica_salud(health_history):
    """Reglas nutricionales según antecedentes declarados."""
    condicion = normalizar_texto(health_history)
    if 'diabet' in condicion:
        return ('Diabetes: prioriza alimentos de bajo índice glucémico, evita azúcares '
                'añadidos y jugos, controla el tamaño de las porciones de carbohidratos '
                'y prefiere granos integrales como quinua, kiwicha y avena.')
    if 'hipertens' in condicion:
        return ('Hipertensión: reduce el sodio al mínimo, evita embutidos, enlatados y '
                'salsas industriales; condimenta con limón, hierbas y ajo; prioriza '
                'alimentos frescos y cocidos en casa.')
    if 'obes' in condicion:
        return ('Obesidad: aplica déficit calórico moderado, alta saciedad con fibra y '
                'proteína, controla porciones y evita bebidas azucaradas y ultraprocesados.')
    return 'Sin condiciones declaradas: mantén una alimentación equilibrada y variada.'

def calcular_objetivos_nutricionales(peso, estatura, edad, genero, actividad, objetivo):
    """
    Calcula IMC, gasto energético total y macros con la fórmula de Mifflin-St Jeor.
    Devuelve None si faltan datos físicos válidos.
    """
    peso = numero_seguro(peso, 20, 400)
    estatura = numero_seguro(estatura, 80, 260)
    edad = numero_seguro(edad, 10, 120)
    if not peso or not estatura or not edad:
        return None

    factor = numero_seguro(actividad, 1.0, 2.5, 1.55)
    if factor not in ACTIVIDADES_VALIDAS:
        factor = min(ACTIVIDADES_VALIDAS, key=lambda opcion: abs(opcion - factor))

    genero_n = normalizar_texto(genero)
    if genero_n.startswith('f') or genero_n in ('female', 'mujer', 'femenino'):
        ajuste = -161
        es_masculino = False
    elif genero_n.startswith('m') or genero_n in ('male', 'hombre', 'masculino'):
        ajuste = 5
        es_masculino = True
    else:
        ajuste = -78
        es_masculino = False

    bmr = 10 * peso + 6.25 * estatura - 5 * edad + ajuste
    tdee = bmr * factor

    imc = peso / ((estatura / 100) ** 2)
    if imc < 18.5:
        clasificacion = 'bajo peso'
    elif imc < 25:
        clasificacion = 'peso normal'
    elif imc < 30:
        clasificacion = 'sobrepeso'
    else:
        clasificacion = 'obesidad'

    objetivo_n = normalizar_texto(objetivo)
    notas = []

    if 'perder' in objetivo_n:
        tipo = 'pérdida de grasa'
        kcal = tdee * 0.80
        proteina_por_kg = 2.0
    elif 'ganar' in objetivo_n or 'musculo' in objetivo_n or 'masa' in objetivo_n:
        tipo = 'ganancia de masa muscular'
        kcal = tdee * 1.10
        proteina_por_kg = 1.8
    else:
        tipo = 'mantenimiento'
        kcal = tdee
        proteina_por_kg = 1.6

    # Seguridad: no aplicar déficit a personas con bajo peso
    if tipo == 'pérdida de grasa' and imc < 18.5:
        tipo = 'mantenimiento'
        kcal = tdee
        proteina_por_kg = 1.6
        notas.append('IMC bajo: no se aplica déficit calórico.')

    # Piso mínimo de seguridad
    piso = 1500 if es_masculino else 1200
    if kcal < piso:
        kcal = piso
        notas.append(f'Se aplicó un piso mínimo de {piso} kcal por seguridad.')

    proteinas = proteina_por_kg * peso
    grasas = (kcal * 0.25) / 9
    carbohidratos = max((kcal - proteinas * 4 - grasas * 9) / 4, 0)

    return {
        'imc': round(imc, 1),
        'clasificacion_imc': clasificacion,
        'actividad_factor': factor,
        'actividad_descripcion': DESCRIPCION_ACTIVIDAD.get(factor, 'moderado'),
        'bmr': int(round(bmr)),
        'tdee': int(round(tdee)),
        'kcal_objetivo': int(round(kcal / 10.0) * 10),
        'proteinas_g': int(round(proteinas / 5.0) * 5),
        'grasas_g': int(round(grasas / 5.0) * 5),
        'carbohidratos_g': int(round(carbohidratos / 5.0) * 5),
        'proteina_por_kg': proteina_por_kg,
        'tipo_objetivo': tipo,
        'notas': notas,
    }

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
def generar_con_reintentos(prompt, system_instruction=None, temperature=0.7):
    modelos = ['gemini-3.5-flash', 'gemini-3.8-flash', 'gemini-1.5-flash']
    ultimo_error = None

    configuracion = types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=system_instruction,
    ) if system_instruction else types.GenerateContentConfig(temperature=temperature)

    for modelo in modelos:
        try:
            print(f"Intentando con modelo: {modelo}...")
            respuesta = cliente.models.generate_content(
                model=modelo,
                contents=prompt,
                config=configuracion,
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
    if not permitir_peticion(f"plan:{current_user.id if current_user.is_authenticated else _ip_cliente()}", 15, 300):
        return respuesta_limite()

    datos = request.json
    if not datos:
        return jsonify({"exito": False, "error": "No se recibieron datos."}), 400

    # Datos físicos y preferencias (todos saneados antes de entrar al prompt)
    peso = datos.get('peso')
    estatura = datos.get('estatura')
    edad = datos.get('edad')
    genero = texto_seguro(datos.get('genero', 'No especificado'), 30) or 'No especificado'
    region = texto_seguro(datos.get('region', 'Costa'), 30) or 'Costa'
    objetivo = texto_seguro(datos.get('objetivo', 'Mantener peso'), 60) or 'Mantener peso'
    health_history = texto_seguro(datos.get('health_history', 'Ninguno'), 60) or 'Ninguno'
    actividad = datos.get('actividad', 1.55)
    presupuesto = texto_seguro(datos.get('presupuesto', 'Económico'), 40) or 'Económico'
    tiempo_cocina = texto_seguro(datos.get('tiempo_cocina', '30 min'), 40) or '30 min'
    comidas_al_dia = numero_seguro(datos.get('comidas_al_dia'), 2, 6, 4)
    alergias = texto_seguro(datos.get('alergias', ''), 160)

    if not peso or not estatura or not edad:
        return jsonify({"exito": False, "error": "Faltan datos obligatorios (peso, estatura o edad)."}), 400

    objetivos = calcular_objetivos_nutricionales(peso, estatura, edad, genero, actividad, objetivo)
    if not objetivos:
        return jsonify({
            "exito": False,
            "error": "Los datos físicos no son válidos. Revisa peso (20-400 kg), estatura (80-260 cm) y edad (10-120 años)."
        }), 400

    reglas_salud = logica_salud(health_history)

    if presupuesto.lower().startswith('econ'):
        criterio_presupuesto = (
            'Presupuesto ECONÓMICO: usa alimentos locales y de temporada. Está prohibido '
            'recomendar salmón, arándanos, carnes premium, suplementos caros o productos '
            'importados. Prioriza menestras, huevos, pollo, pescado local (bonito, jurel), '
            'avena, plátano, papa, camote, quinua, kiwicha y verduras del mercado.'
        )
    elif presupuesto.lower().startswith('flex'):
        criterio_presupuesto = (
            'Presupuesto FLEXIBLE: puedes incluir algunos alimentos de mayor costo, pero '
            'mantén como base los alimentos locales peruanos y evita lujos innecesarios.'
        )
    else:
        criterio_presupuesto = (
            'Presupuesto MODERADO: combina alimentos locales económicos con algunas '
            'opciones de mayor valor nutricional sin disparar el costo semanal.'
        )

    if alergias:
        criterio_alergias = (
            f'ALERGIAS/INTOLERANCIAS DECLARADAS: "{alergias}". '
            'NO incluyas estos ingredientes ni sus derivados en ninguna comida, snack o bebida. '
            'Si un plato tradicional los contiene, sustitúyelo y explica brevemente la sustitución.'
        )
    else:
        criterio_alergias = 'Alergias: ninguna declarada. Aun así, evita ingredientes poco comunes sin justificarlo.'

    notas = ' '.join(objetivos['notas']) if objetivos['notas'] else 'Sin ajustes de seguridad adicionales.'

    prompt = f"""
Actúa como un equipo de nutricionistas y entrenadores peruanos. Debes respetar los cálculos
entregados: NO los recalcules ni los cambies. Tu trabajo es traducirlos a un plan práctico.

DATOS DEL USUARIO
- Peso: {peso} kg
- Estatura: {estatura} cm
- Edad: {edad} años
- Género: {genero}
- Región: {region}
- Objetivo declarado: {objetivo}
- Nivel de actividad: {objetivos['actividad_descripcion']} (factor {objetivos['actividad_factor']})
- Antecedentes de salud: {health_history}
- Alergias declaradas: {alergias or 'Ninguna'}
- Presupuesto: {presupuesto}
- Tiempo máximo de cocina por comida: {tiempo_cocina}
- Comidas al día: {int(comidas_al_dia)}

OBJETIVOS CALCULADOS (obligatorios, no modificar)
- IMC: {objetivos['imc']} kg/m² ({objetivos['clasificacion_imc']})
- Metabolismo basal estimado: {objetivos['bmr']} kcal
- Gasto energético total estimado: {objetivos['tdee']} kcal
- Calorías objetivo del día: {objetivos['kcal_objetivo']} kcal
- Proteínas: {objetivos['proteinas_g']} g ({objetivos['proteina_por_kg']} g/kg)
- Grasas: {objetivos['grasas_g']} g
- Carbohidratos: {objetivos['carbohidratos_g']} g
- Estrategia: {objetivos['tipo_objetivo']}
- Notas de seguridad: {notas}

REGLAS NUTRICIONALES
- {reglas_salud}
- {criterio_presupuesto}
- {criterio_alergias}
- Distribuye las calorías y macros entre las {int(comidas_al_dia)} comidas del día.
- Cada comida debe poder prepararse en {tiempo_cocina} o menos.
- Incluye al menos 2 superalimentos peruanos adecuados a la región {region} (por ejemplo
  quinua, kiwicha, cañihua, sacha inchi, camu camu, cacao, maca, tarwi, aguaymanto).
- Usa medidas caseras claras (taza, cucharada, unidad, gramos aproximados).
- No recomiendes suplementos, medicamentos ni dietas extremas. No prometas resultados médicos.
- Si el antecedente de salud lo requiere, recuerda consultar a su médico tratante.

FORMATO DE SALIDA
Devuelve ÚNICAMENTE HTML puro (sin markdown ni bloques de código), con esta estructura:

<h2>Objetivos calculados</h2>
<ul> con IMC y su clasificación, calorías objetivo, proteínas, grasas y carbohidratos.

<h2>PARTE 1: Plan nutricional peruano</h2>
<h3>Desayuno</h3><ul> ingredientes con cantidades, preparación breve y aproximado de kcal/proteína.
Repite el mismo formato para cada una de las {int(comidas_al_dia)} comidas.

<h2>PARTE 2: Rutina de entrenamiento</h2>
Rutina de 3 a 4 días adaptada al objetivo "{objetivo}", con días, ejercicios, series y repeticiones.
Si el objetivo es ganar masa muscular, prioriza hipertrofia (6-12 repeticiones).
Si es perder grasa, combina fuerza con cardio moderado.

<h2>Recomendaciones y advertencias</h2>
<ul> con 3 a 5 recomendaciones prácticas, alergias a vigilar y el aviso de consultar a un
profesional de la salud.
"""

    try:
        texto_respuesta = generar_con_reintentos(
            prompt,
            system_instruction=(
                'Eres un nutricionista y entrenador peruano. Respetas estrictamente los cálculos '
                'nutricionales entregados, usas alimentos locales y devuelves solo HTML válido.'
            ),
            temperature=0.55,
        )
        html_limpio = sanear_html_ia(clean_ai_response(texto_respuesta))
        registro = guardar_plan_en_historial(
            'individual',
            f"Plan individual · {objetivo}",
            f"{region} · {objetivos['kcal_objetivo']} kcal/día · {int(comidas_al_dia)} comidas · {objetivos['clasificacion_imc']}",
            html_limpio,
            objetivos,
        )
        return jsonify({
            "exito": True,
            "html": html_limpio,
            "objetivos": objetivos,
            "historial_id": registro.id if registro else None,
        })
    except Exception as e:
        print(f"ERROR INDIVIDUAL: {e}")
        return jsonify({"exito": False, "error": "La IA de Google está teniendo problemas. Intenta de nuevo en unos minutos."}), 500

# ==========================================
# 2. RUTA PARA EL PLAN FAMILIAR
# ==========================================
@app.route('/generar-plan-familiar', methods=['POST'])
def generar_plan_familiar():
    if not permitir_peticion(f"plan-familiar:{current_user.id if current_user.is_authenticated else _ip_cliente()}", 10, 300):
        return respuesta_limite()

    datos = request.json
    if not datos:
        return jsonify({"exito": False, "error": "No se recibieron datos."}), 400

    miembros = datos.get('miembros', [])
    if not isinstance(miembros, list) or not miembros:
        return jsonify({"exito": False, "error": "La lista de miembros está vacía."}), 400
    if len(miembros) > 12:
        return jsonify({"exito": False, "error": "El plan familiar admite como máximo 12 integrantes."}), 400

    presupuesto = texto_seguro(datos.get('presupuesto', 'Económico'), 40) or 'Económico'

    descripcion_miembros = ""
    objetivos_familia = []

    for i, m in enumerate(miembros):
        nombre = texto_seguro(m.get('nombre', f'Miembro {i+1}'), 60) or f'Miembro {i+1}'
        edad = numero_seguro(m.get('edad'), 1, 120, None)
        peso = numero_seguro(m.get('peso'), 5, 400, None)
        estatura = numero_seguro(m.get('estatura'), 40, 260, None)
        antecedentes = texto_seguro(m.get('antecedentes', 'Ninguno'), 60) or 'Ninguno'

        objetivos = None
        if peso and estatura and edad:
            # Primero estimamos el IMC para elegir una estrategia razonable por integrante.
            base = calcular_objetivos_nutricionales(peso, estatura, edad, 'No especificado', 1.55, 'Mantener peso')
            if base:
                if base['imc'] >= 25:
                    objetivo_miembro = 'Perder grasa'
                elif base['imc'] < 18.5:
                    objetivo_miembro = 'Ganar masa muscular'
                else:
                    objetivo_miembro = 'Mantener peso'
                objetivos = calcular_objetivos_nutricionales(
                    peso, estatura, edad, 'No especificado', 1.55, objetivo_miembro
                )

        if objetivos:
            objetivos_familia.append({
                'nombre': nombre,
                'edad': edad,
                'imc': objetivos['imc'],
                'clasificacion_imc': objetivos['clasificacion_imc'],
                'kcal_objetivo': objetivos['kcal_objetivo'],
                'proteinas_g': objetivos['proteinas_g'],
                'grasas_g': objetivos['grasas_g'],
                'carbohidratos_g': objetivos['carbohidratos_g'],
                'estrategia': objetivos['tipo_objetivo'],
            })
            descripcion_miembros += (
                f"\n- {nombre}: {int(edad)} años, {peso} kg, {estatura} cm, antecedentes: {antecedentes}. "
                f"IMC {objetivos['imc']} ({objetivos['clasificacion_imc']}). "
                f"Objetivo diario: {objetivos['kcal_objetivo']} kcal, {objetivos['proteinas_g']} g de proteína, "
                f"{objetivos['grasas_g']} g de grasa, {objetivos['carbohidratos_g']} g de carbohidratos "
                f"({objetivos['tipo_objetivo']})."
            )
        else:
            descripcion_miembros += (
                f"\n- {nombre}: {edad or '?'} años, {peso or '?'} kg, {estatura or '?'} cm, "
                f"antecedentes: {antecedentes}. Datos físicos incompletos: no calcular calorías exactas; "
                'aplica porciones familiares estándar y señala la limitación.'
            )

    resumen_objetivos = ''
    for o in objetivos_familia:
        resumen_objetivos += (
            f"<li>{o['nombre']}: IMC {o['imc']} ({o['clasificacion_imc']}), "
            f"{o['kcal_objetivo']} kcal, {o['proteinas_g']} g proteína, "
            f"{o['grasas_g']} g grasa, {o['carbohidratos_g']} g carbohidratos "
            f"(estrategia: {o['estrategia']}).</li>"
        )
    if not resumen_objetivos:
        resumen_objetivos = '<li>No se pudieron calcular objetivos individuales por datos incompletos.</li>'

    prompt = f"""
Actúa como un equipo de nutricionistas peruanos especializados en alimentación familiar.

INTEGRANTES Y OBJETIVOS YA CALCULADOS (no los modifiques):
{descripcion_miembros}

CRITERIOS OBLIGATORIOS
- Presupuesto: {presupuesto}. Si es económico, prohíbe salmón, arándanos, carnes premium e
  importados; usa menestras, huevos, pollo, pescado local, avena, papa, camote, quinua y kiwicha.
- Las comidas deben compartir una base familiar para cocinar una sola vez y ajustar porciones.
- Respeta los antecedentes de salud de cada integrante y evita ingredientes incompatibles.
- No prometas resultados médicos ni recomiendes suplementos o medicamentos.
- Usa superalimentos peruanos accesibles y de temporada.

FORMATO DE SALIDA
Devuelve ÚNICAMENTE HTML puro (sin markdown ni bloques de código), con esta estructura:

<h2>Objetivos por integrante</h2>
<ul>{resumen_objetivos}</ul>

<h2>Menú familiar diario</h2>
<h3>Desayuno</h3><ul> opciones y porciones diferenciadas por integrante cuando corresponda.
<h3>Almuerzo</h3><ul> ...
<h3>Cena</h3><ul> ...

<h2>Lista de compras semanal</h2>
<ul> con alimentos, cantidades aproximadas para toda la familia y costo estimado en soles (S/).
Cierra con el <strong>costo total estimado</strong> de la semana.

<h2>Consejos de preparación y advertencias</h2>
<ul> con 3 a 5 consejos prácticos, sustituciones económicas y el aviso de consultar a un
profesional de la salud ante condiciones médicas.
"""

    try:
        texto_respuesta = generar_con_reintentos(
            prompt,
            system_instruction=(
                'Eres un nutricionista peruano especializado en familias. Respetas los objetivos '
                'calculados por integrante, ajustas porciones y devuelves solo HTML válido.'
            ),
            temperature=0.55,
        )
        html_limpio = sanear_html_ia(clean_ai_response(texto_respuesta))
        registro = guardar_plan_en_historial(
            'familiar',
            f"Plan familiar · {len(miembros)} integrantes",
            f"{len(miembros)} integrantes · presupuesto {presupuesto} · objetivos calculados",
            html_limpio,
            objetivos_familia,
        )
        return jsonify({
            "exito": True,
            "html": html_limpio,
            "objetivos": objetivos_familia,
            "historial_id": registro.id if registro else None,
        })
    except Exception as e:
        print(f"ERROR FAMILIAR: {e}")
        return jsonify({"exito": False, "error": "La IA está saturada. Intenta de nuevo."}), 500

# ==========================================
# 3. RUTA PARA EL CHAT MULTIMODAL
# ==========================================
@app.route('/chat', methods=['POST'])
def chat_interactivo():
    if not permitir_peticion(f"chat:{current_user.id if current_user.is_authenticated else _ip_cliente()}", 60, 300):
        return respuesta_limite()

    datos = request.json or {}
    pregunta = texto_seguro(datos.get('pregunta', ''), 800)
    imagen_b64 = datos.get('imagen')
    mime_type = datos.get('mime_type')

    system_instruction = (
        'Eres el nutricionista virtual de MIKHUCHIYNCA, especializado en alimentación peruana. '
        'Respondes en español claro y cálido, en un máximo de 120 palabras, usando HTML simple '
        '(párrafos y listas cortas). Priorizas alimentos locales y económicos de la costa, sierra '
        'y selva. Si falta contexto, haces una sola pregunta breve. '
        'No das diagnósticos médicos, no recetas medicamentos ni suplementos, y no prometes '
        'resultados. Ante síntomas, embarazo, menores de edad o enfermedades crónicas, recomiendas '
        'consultar a un profesional de la salud. Si el usuario menciona alergias, las respetas '
        'estrictamente. No inventes calorías exactas: da rangos aproximados y aclara que son estimados.'
    )

    prompt = 'Consulta del usuario: '
    contenidos = []

    if imagen_b64 and mime_type:
        if mime_type not in ('image/jpeg', 'image/png', 'image/webp', 'image/gif'):
            return jsonify({"exito": False, "error": "Formato de imagen no permitido."}), 400
        if not isinstance(imagen_b64, str) or len(imagen_b64) > 8_000_000:
            return jsonify({"exito": False, "error": "La imagen es demasiado grande (máximo 6 MB)."}), 400

        prompt = (
            'Analiza la foto adjunta de una comida. Identifica los ingredientes visibles, estima '
            'las porciones y da un rango aproximado de calorías y macronutrientes. Señala que es una '
            'estimación visual. '
        )
        try:
            imagen_bytes = base64.b64decode(imagen_b64, validate=True)
            if len(imagen_bytes) > 6 * 1024 * 1024:
                return jsonify({"exito": False, "error": "La imagen es demasiado grande (máximo 6 MB)."}), 400

            firmas = {
                'image/jpeg': (b'\xff\xd8\xff',),
                'image/png': (b'\x89PNG\r\n\x1a\n',),
                'image/gif': (b'GIF87a', b'GIF89a'),
                'image/webp': (b'RIFF',),
            }
            if not any(imagen_bytes.startswith(firma) for firma in firmas[mime_type]):
                return jsonify({"exito": False, "error": "El archivo no es una imagen válida."}), 400
            if mime_type == 'image/webp' and imagen_bytes[8:12] != b'WEBP':
                return jsonify({"exito": False, "error": "El archivo no es una imagen válida."}), 400

            parte_imagen = types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type)
            contenidos.append(parte_imagen)
        except Exception as e:
            print(f"ERROR IMAGEN CHAT: {e}")
            return jsonify({"exito": False, "error": "No pudimos leer la imagen. Intenta con otra foto."}), 400

    if pregunta:
        prompt += f'El usuario pregunta: {pregunta}'
    elif not imagen_b64:
        return jsonify({"exito": False, "error": "Escribe una pregunta o adjunta una foto."}), 400

    contenidos.append(prompt)

    try:
        respuesta = cliente.models.generate_content(
            model='gemini-3.5-flash',
            contents=contenidos,
            config=types.GenerateContentConfig(
                temperature=0.6,
                system_instruction=system_instruction,
            ),
        )
        texto_limpio = sanear_html_ia(clean_ai_response(respuesta.text))
        return jsonify({"exito": True, "respuesta": texto_limpio})
    except Exception as e:
        print(f"ERROR CHAT: {e}")
        return jsonify({"exito": False, "error": "El chat está en mantenimiento. Intenta pronto."}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
