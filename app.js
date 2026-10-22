// ==========================================
// 1. LÓGICA PARA SELECCIONAR OBJETIVOS (Usando tu clase goal-btn)
// ==========================================
const botonesObjetivo = document.querySelectorAll('.goal-btn'); 
let objetivoSeleccionado = 'Ganar masa muscular'; // Por defecto

botonesObjetivo.forEach(boton => {
    boton.addEventListener('click', function() {
        // 1. Apagamos todas las tarjetas
        botonesObjetivo.forEach(b => {
            b.style.border = '1px solid #2c3e50'; 
            b.style.backgroundColor = 'transparent';
        });
        
        // 2. Iluminamos de naranja solo la que tocaste
        this.style.border = '2px solid #e67e22'; 
        this.style.backgroundColor = 'rgba(230, 126, 34, 0.1)';
        
        // 3. Guardamos el texto del objetivo (Perder grasa o Ganar masa)
        const label = this.querySelector('.goal-label');
        if (label) {
            objetivoSeleccionado = label.innerText; 
        }
    });
});

// ==========================================
// 2. LÓGICA DEL CHATBOX Y LA CÁMARA
// ==========================================
const btnChat = document.getElementById('btn-enviar-chat');
const inputChat = document.getElementById('chat-input');
const historialChat = document.getElementById('chat-historial');
const inputFoto = document.getElementById('chat-foto');
const btnFoto = document.getElementById('btn-foto');
const previewImg = document.getElementById('vista-previa-imagen');
const nombreArchivo = document.getElementById('nombre-archivo-img');
const btnQuitarImg = document.getElementById('quitar-img');

let base64Image = null;
let imageMimeType = null;

// Cuando presionas el botón 📷
if (btnFoto && inputFoto) {
    btnFoto.addEventListener('click', () => inputFoto.click());

    // Al seleccionar una foto
    inputFoto.addEventListener('change', function() {
        const file = this.files[0];
        if (file) {
            nombreArchivo.textContent = file.name;
            previewImg.style.display = 'flex';
            
            const reader = new FileReader();
            reader.onload = function(e) {
                base64Image = e.target.result.split(',')[1];
                imageMimeType = file.type;
            };
            reader.readAsDataURL(file);
        }
    });

    // Botón para cancelar la foto (la X roja)
    btnQuitarImg.addEventListener('click', () => {
        inputFoto.value = '';
        base64Image = null;
        imageMimeType = null;
        previewImg.style.display = 'none';
    });
}

// Al presionar "Enviar" en el chat
if (btnChat) {
    btnChat.addEventListener('click', async () => {
        const mensaje = inputChat.value.trim();
        if (!mensaje && !base64Image) return;

        let mensajeHTML = `<p style="color: #2980b9; margin: 10px 0;"><strong>Tú:</strong> ${mensaje}`;
        if (base64Image) mensajeHTML += `<br><span style="color: #f39c12; font-size: 0.85rem;">📸 [Enviando foto del plato...]</span>`;
        mensajeHTML += `</p>`;
        
        historialChat.innerHTML += mensajeHTML;
        inputChat.value = ''; 
        historialChat.scrollTop = historialChat.scrollHeight;

        const idCarga = "carga-" + Date.now();
        historialChat.innerHTML += `<p id="${idCarga}" style="color: #7f8c8d; margin: 10px 0; font-style: italic;">La IA está analizando...</p>`;
        historialChat.scrollTop = historialChat.scrollHeight;

        const payload = { pregunta: mensaje, imagen: base64Image, mime_type: imageMimeType };
        if (btnQuitarImg) btnQuitarImg.click(); // Limpia la foto

        try {
            const respuesta = await fetch('/.netlify/functions/chat', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            const datos = await respuesta.json();
            document.getElementById(idCarga).remove();
            
            if (datos.exito) {
                historialChat.innerHTML += `<p style="color: #27ae60; margin: 10px 0;"><strong>Nutricionista IA:</strong> ${datos.respuesta}</p>`;
            } else {
                historialChat.innerHTML += `<p style="color: #e74c3c; margin: 10px 0;"><strong>Error:</strong> ${datos.error}</p>`;
            }
            historialChat.scrollTop = historialChat.scrollHeight;
            
        } catch (error) {
            if (document.getElementById(idCarga)) document.getElementById(idCarga).remove();
            historialChat.innerHTML += `<p style="color: #e74c3c; margin: 10px 0;"><strong>Error de conexión.</strong></p>`;
        }
    });
}
// ==========================================
// 3. LÓGICA DEL BOTÓN: GENERAR PLAN NUTRICIONAL
// ==========================================
// Buscamos automáticamente el botón naranja que genera el plan
const botones = document.querySelectorAll('button');
let btnGenerarPlan = null;
botones.forEach(b => {
    if (b.innerText.includes('Generar Plan')) {
        btnGenerarPlan = b;
    }
});

if (btnGenerarPlan) {
    btnGenerarPlan.addEventListener('click', async (e) => {
        e.preventDefault(); // Evita que la página se recargue de golpe
        
        // Recuperamos el peso y la región (busca por ID o agarra el primer input numérico)
        const inputPeso = document.getElementById('peso') || document.getElementById('weight') || document.querySelector('input[type="number"]');
        const selectRegion = document.getElementById('region') || document.querySelector('select:last-of-type');
        
        const peso = inputPeso ? inputPeso.value : 70;
        const region = selectRegion ? selectRegion.value : 'Costa';
        
        // Efecto visual de que está cargando
        const textoOriginal = btnGenerarPlan.innerText;
        btnGenerarPlan.innerText = "Calculando tu dieta, espera... ⏳";
        btnGenerarPlan.style.opacity = "0.7";
        btnGenerarPlan.disabled = true;
        
        try {
            // (Si lo vas a probar en el celular, recuerda cambiar 127.0.0.1 por la IP de tu laptop)
            const respuesta = await fetch('/.netlify/functions/escaner', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    peso: peso,
                    region: region,
                    objetivo: objetivoSeleccionado // Esta variable viene de la tarjeta que seleccionaste arriba
                })
            });
            
            const datos = await respuesta.json();
            
            if (datos.exito) {
                // Creamos un cuadro bonito debajo del botón para mostrar la dieta
                let divResultado = document.getElementById('resultado-dieta');
                if (!divResultado) {
                    divResultado = document.createElement('div');
                    divResultado.id = 'resultado-dieta';
                    divResultado.style.marginTop = '20px';
                    divResultado.style.padding = '20px';
                    divResultado.style.backgroundColor = '#1a2639';
                    divResultado.style.border = '2px solid #27ae60';
                    divResultado.style.borderRadius = '8px';
                    divResultado.style.color = '#ecf0f1';
                    divResultado.style.lineHeight = '1.6';
                    
                    // Lo insertamos justo debajo del botón naranja
                    btnGenerarPlan.parentNode.insertBefore(divResultado, btnGenerarPlan.nextSibling);
                }
                divResultado.innerHTML = `<h3 style="color: #f39c12; margin-top:0;">🍽️ Tu Plan Nutricional MIKHUCHIYNCA</h3>` + datos.html;
            } else {
                alert("Error de la IA: " + datos.error);
            }
        } catch (error) {
            alert("Error de conexión. Asegúrate de que tu servidor Python esté corriendo.");
        } finally {
            // Restauramos el botón
            btnGenerarPlan.innerText = textoOriginal;
            btnGenerarPlan.style.opacity = "1";
            btnGenerarPlan.disabled = false;
        }
    });
}
