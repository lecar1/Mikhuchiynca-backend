from google import genai

API_KEY = "AQ.Ab8RN6Kt05_1MX5YvZEWqw_MTwVzxf0ZsIcpNnaAyHQ4SXbjIA"
cliente = genai.Client(api_key=API_KEY)

print("🔍 Consultando modelos activos para tu llave...")
for modelo in cliente.models.list():
    print(f"✅ Modelo disponible: {modelo.name}")
