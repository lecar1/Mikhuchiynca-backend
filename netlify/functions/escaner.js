// ==========================================
// Netlify Function: /.netlify/functions/escaner
// Proxy seguro para generar plan nutricional (escaner)
// ==========================================
exports.handler = async (event, context) => {
  // Cabeceras CORS y JSON
  const headers = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
  };

  // Responder preflight CORS
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  // Solo permitir POST
  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      headers,
      body: JSON.stringify({ exito: false, error: 'Método no permitido' }),
    };
  }

  try {
    // 1. Extraer el body enviado desde el frontend
    const payload = JSON.parse(event.body || '{}');

    // 2. Hacer la petición HTTP externa al backend real,
    //    inyectando de forma oculta la API_KEY en los headers
    const respuesta = await fetch('https://mikhuchiynca-backend.onrender.com/generar-plan', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${process.env.API_KEY}`,
      },
      body: JSON.stringify(payload),
    });

    const datos = await respuesta.json();

    // 3. Devolver los datos limpios al frontend
    return {
      statusCode: respuesta.status || 200,
      headers,
      body: JSON.stringify(datos),
    };
  } catch (error) {
    console.error('Error en función escaner:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ exito: false, error: error.message }),
    };
  }
};
