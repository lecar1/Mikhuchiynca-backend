// ==========================================
// 1. SELECCIÓN DE OBJETIVO (goal-btn)
// ==========================================
const botonesObjetivo = document.querySelectorAll('.goal-btn');
let objetivoSeleccionado = 'Mantener peso'; // valor por defecto

botonesObjetivo.forEach(boton => {
    boton.addEventListener('click', function () {
        botonesObjetivo.forEach(b => {
            b.style.border = '';
            b.style.backgroundColor = '';
            b.setAttribute('aria-checked', 'false');
        });
        this.style.border = '2px solid #f97316';
        this.style.backgroundColor = 'rgba(249, 115, 22, 0.1)';
        this.setAttribute('aria-checked', 'true');
        const label = this.querySelector('.goal-label');
        if (label) objetivoSeleccionado = label.innerText.trim();
        // Sincronizar input hidden del formulario
        const hiddenGoal = document.getElementById('goal');
        if (hiddenGoal) hiddenGoal.value = objetivoSeleccionado;
    });
});

// ==========================================
// 2. CHAT MULTIMODAL (texto + foto)
// ==========================================
const btnChat       = document.getElementById('btn-enviar-chat');
const inputChat     = document.getElementById('chat-input');
const historialChat = document.getElementById('chat-historial');
const inputFoto     = document.getElementById('chat-foto');
const btnFoto       = document.getElementById('btn-foto');
const previewImg    = document.getElementById('vista-previa-imagen');
const nombreArchivo = document.getElementById('nombre-archivo-img');
const btnQuitarImg  = document.getElementById('quitar-img');

let base64Image   = null;
let imageMimeType = null;

function mostrarIndicadorEscribiendo() {
    const idCarga = 'carga-' + Date.now();
    const indicador = document.createElement('p');
    indicador.id = idCarga;
    indicador.style.cssText = 'color:#7f8c8d;margin:10px 0;font-style:italic;';
    indicador.innerText = 'Nutricionista IA está escribiendo...';
    historialChat.appendChild(indicador);
    historialChat.scrollTop = historialChat.scrollHeight;
    return idCarga;
}

function removerIndicadorEscribiendo(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

if (btnFoto && inputFoto) {
    btnFoto.addEventListener('click', () => inputFoto.click());

    inputFoto.addEventListener('change', function () {
        const file = this.files[0];
        if (file) {
            nombreArchivo.textContent = file.name;
            previewImg.style.display = 'flex';
            const reader = new FileReader();
            reader.onload = e => {
                base64Image   = e.target.result.split(',')[1];
                imageMimeType = file.type;
            };
            reader.readAsDataURL(file);
        }
    });

    if (btnQuitarImg) {
        btnQuitarImg.addEventListener('click', () => {
            inputFoto.value = '';
            base64Image     = null;
            imageMimeType   = null;
            previewImg.style.display = 'none';
        });
    }
}

// Función para enviar mensajes al chat (también usada por quick-replies)
async function enviarMensajeChat(mensajeTexto) {
    const mensaje = mensajeTexto !== undefined ? mensajeTexto : inputChat.value.trim();
    if (!mensaje && !base64Image) return;

    let mensajeHTML = `<p style="color:#2980b9;margin:10px 0;"><strong>Tú:</strong> ${mensaje}`;
    if (base64Image) mensajeHTML += `<br><span style="color:#f39c12;font-size:0.85rem;">📸 [Enviando foto del plato...]</span>`;
    mensajeHTML += '</p>';

    historialChat.innerHTML += mensajeHTML;
    inputChat.value = '';
    historialChat.scrollTop = historialChat.scrollHeight;

    const idCarga = mostrarIndicadorEscribiendo();
    const payload = { pregunta: mensaje, imagen: base64Image, mime_type: imageMimeType };
    if (btnQuitarImg) btnQuitarImg.click();

    try {
        const respuesta = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const datos = await respuesta.json();
        removerIndicadorEscribiendo(idCarga);

        if (datos.exito) {
            historialChat.innerHTML += `<p style="color:#27ae60;margin:10px 0;"><strong>Nutricionista IA:</strong> ${datos.respuesta}</p>`;
        } else {
            historialChat.innerHTML += `<p style="color:#e74c3c;margin:10px 0;"><strong>Error:</strong> ${datos.error}</p>`;
        }
        historialChat.scrollTop = historialChat.scrollHeight;
    } catch (error) {
        removerIndicadorEscribiendo(idCarga);
        historialChat.innerHTML += `<p style="color:#e74c3c;margin:10px 0;"><strong>Error de conexión.</strong></p>`;
        historialChat.scrollTop = historialChat.scrollHeight;
    }
}

if (btnChat) {
    btnChat.addEventListener('click', () => enviarMensajeChat());
}

if (inputChat) {
    inputChat.addEventListener('keypress', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            enviarMensajeChat();
        }
    });
}

function enviarSugerencia(texto) {
    if (inputChat) inputChat.value = texto;
    enviarMensajeChat(texto);
}

// ==========================================
// 3. FORMULARIO: GENERAR PLAN NUTRICIONAL INDIVIDUAL
// ==========================================
const nutritionForm = document.getElementById('nutritionForm');
const generateBtn   = document.getElementById('generateBtn');
const resultDiv     = document.getElementById('result');

if (nutritionForm) {
    nutritionForm.addEventListener('submit', async function (event) {
        // Garantizar que NUNCA recargue la página ni modifique la URL
        event.preventDefault();
        event.stopPropagation();

        const peso           = parseFloat(document.getElementById('weight')?.value) || 0;
        const estatura       = parseFloat(document.getElementById('height')?.value) || 0;
        const region         = document.getElementById('region')?.value || 'Costa';
        const health_history = document.getElementById('health_history')?.value || 'Ninguno';

        // IMC calculado en frontend
        const imc = estatura > 0 ? (peso / Math.pow(estatura / 100, 2)).toFixed(1) : 0;

        // Estado del botón: spinner y deshabilitar
        const textoOriginal = generateBtn ? generateBtn.innerHTML : '';
        if (generateBtn) {
            generateBtn.innerHTML = `
                <span class="btn-text">Generando plan...</span>
                <svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round"
                     style="animation:spin 1s linear infinite;width:20px;height:20px;">
                    <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
                </svg>`;
            generateBtn.disabled = true;
        }

        try {
            const respuesta = await fetch('/generar-plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    peso:           peso,
                    region:         region,
                    objetivo:       objetivoSeleccionado,
                    health_history: health_history,
                    imc:            parseFloat(imc)
                })
            });

            const datos = await respuesta.json();

            if (resultDiv) {
                resultDiv.classList.remove('hidden');

                if (datos.exito) {
                    resultDiv.innerHTML = `
                        <div class="result-header">
                            <h2>
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                    <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                                    <path d="M2 17l10 5 10-5"/>
                                    <path d="M2 12l10 5 10-5"/>
                                </svg>
                                Tu Plan Nutricional Personalizado
                            </h2>
                            <p class="result-meta" id="resultMeta">
                                📍 Región: <strong>${region}</strong> &nbsp;|&nbsp;
                                🎯 Objetivo: <strong>${objetivoSeleccionado}</strong> &nbsp;|&nbsp;
                                📊 IMC: <strong>${imc}</strong> ${health_history !== 'Ninguno' ? `&nbsp;|&nbsp; ⚠️ Condición: <strong>${health_history}</strong>` : ''}
                            </p>
                        </div>
                        <div class="plan-card" style="margin-top: 1rem;">
                            ${datos.html}
                        </div>
                    `;
                } else {
                    const esSaturacion = respuesta.status === 503 || (datos.error || '').toLowerCase().includes('503');
                    resultDiv.innerHTML = `
                        <div class="plan-card" style="border-color:var(--danger);margin-top:1rem;">
                            <p style="color:#e74c3c;">
                                <strong>${esSaturacion ? '🚦 IA en alto tráfico:' : 'Error:'}</strong>
                                ${esSaturacion ? 'Nuestra IA está muy solicitada en este momento. Intenta de nuevo en unos segundos.' : datos.error}
                            </p>
                        </div>
                    `;
                }

                // Scroll suave al div#result
                resultDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        } catch (error) {
            if (resultDiv) {
                resultDiv.classList.remove('hidden');
                resultDiv.innerHTML = `
                    <div class="plan-card" style="border-color:var(--danger);margin-top:1rem;">
                        <p style="color:#e74c3c;"><strong>Error de conexión:</strong> No se pudo conectar con el servidor.</p>
                    </div>
                `;
                resultDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        } finally {
            if (generateBtn) {
                generateBtn.innerHTML = textoOriginal;
                generateBtn.disabled  = false;
            }
        }
    });
}

// ==========================================
// 4. MODO FAMILIAR — LÓGICA COMPLETA
// ==========================================
let contadorMiembros = 0;

// Toast elegante sin alert()
function mostrarToast(mensaje, tipo = 'error') {
    let toast = document.getElementById('toast-notif');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast-notif';
        toast.className = 'toast';
        document.body.appendChild(toast);
    }
    toast.textContent = mensaje;
    toast.className = 'toast' + (tipo === 'success' ? ' toast-success' : '');
    void toast.offsetWidth; // reiniciar animación
    toast.classList.add('show');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 4500);
}

// Genera tarjeta HTML de un miembro
function crearTarjetaMiembro(n) {
    const card = document.createElement('div');
    card.className = 'miembro-card';
    card.dataset.id = n;
    card.innerHTML = `
        <div class="miembro-card-header">
            <span class="miembro-numero">Miembro ${n}</span>
            <button type="button" class="btn-eliminar-miembro" title="Eliminar miembro" onclick="eliminarMiembro(this)">×</button>
        </div>
        <div class="miembro-campos">
            <div class="miembro-campo">
                <label>Nombre</label>
                <input type="text" name="nombre" placeholder="Ej. Mamá, Pedro..." maxlength="40">
            </div>
            <div class="miembro-row">
                <div class="miembro-campo">
                    <label>Edad</label>
                    <input type="number" name="edad" min="1" max="110" placeholder="Años">
                </div>
                <div class="miembro-campo">
                    <label>Peso (kg)</label>
                    <input type="number" name="peso" min="5" max="300" placeholder="kg">
                </div>
            </div>
            <div class="miembro-campo">
                <label>Estatura (cm)</label>
                <input type="number" name="estatura" min="50" max="250" placeholder="cm">
            </div>
            <div class="miembro-campo">
                <label>Antecedentes de Salud</label>
                <select name="antecedentes">
                    <option value="Ninguno">Ninguno</option>
                    <option value="Diabetes">Diabetes</option>
                    <option value="Hipertensión">Hipertensión</option>
                    <option value="Obesidad">Obesidad</option>
                </select>
            </div>
        </div>`;
    return card;
}

// Eliminar miembro con transición
function eliminarMiembro(btn) {
    const card = btn.closest('.miembro-card');
    card.style.transition = 'opacity 0.25s, transform 0.25s';
    card.style.opacity    = '0';
    card.style.transform  = 'scale(0.95)';
    setTimeout(() => {
        card.remove();
        actualizarNumerosMiembros();
        actualizarBotonGenerar();
    }, 250);
}

function actualizarNumerosMiembros() {
    document.querySelectorAll('.miembro-card').forEach((card, i) => {
        const badge = card.querySelector('.miembro-numero');
        if (badge) badge.textContent = `Miembro ${i + 1}`;
    });
}

function actualizarBotonGenerar() {
    const btnGenerar = document.getElementById('btn-generar-familiar');
    const total = document.querySelectorAll('.miembro-card').length;
    if (btnGenerar) btnGenerar.style.display = total > 0 ? 'flex' : 'none';
}

// Botón "Añadir Miembro"
const btnAgregarMiembro = document.getElementById('btn-agregar-miembro');
if (btnAgregarMiembro) {
    btnAgregarMiembro.addEventListener('click', () => {
        contadorMiembros++;
        const contenedor = document.getElementById('familiar-miembros');
        const tarjeta = crearTarjetaMiembro(contadorMiembros);
        contenedor.appendChild(tarjeta);
        tarjeta.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        actualizarBotonGenerar();
    });
}

// Recopila datos de todas las tarjetas familiares
function recopilarMiembros() {
    const cards   = document.querySelectorAll('.miembro-card');
    const miembros = [];
    const errores  = [];

    cards.forEach((card, i) => {
        const nombre       = card.querySelector('[name="nombre"]').value.trim() || `Miembro ${i + 1}`;
        const edad         = parseFloat(card.querySelector('[name="edad"]').value);
        const peso         = parseFloat(card.querySelector('[name="peso"]').value);
        const estatura     = parseFloat(card.querySelector('[name="estatura"]').value);
        const antecedentes = card.querySelector('[name="antecedentes"]').value;

        if (!peso || peso <= 0)  errores.push(`${nombre}: ingresa un peso válido.`);
        if (!edad || edad <= 0)  errores.push(`${nombre}: ingresa una edad válida.`);

        miembros.push({ nombre, edad: edad || 0, peso: peso || 0, estatura: estatura || 0, antecedentes });
    });

    return { miembros, errores };
}

function setEstadoBotonFamiliar(cargando) {
    const btn         = document.getElementById('btn-generar-familiar');
    const textSpan    = btn.querySelector('.btn-familiar-text');
    const spinnerSpan = btn.querySelector('.btn-familiar-spinner');
    btn.disabled              = cargando;
    textSpan.style.display    = cargando ? 'none' : 'flex';
    spinnerSpan.style.display = cargando ? 'flex' : 'none';
}

// Botón "Generar Plan Familiar"
const btnGenerarFamiliar = document.getElementById('btn-generar-familiar');
if (btnGenerarFamiliar) {
    btnGenerarFamiliar.addEventListener('click', async () => {
        const { miembros, errores } = recopilarMiembros();

        if (miembros.length === 0) { mostrarToast('⚠️ Agrega al menos un miembro familiar.'); return; }
        if (errores.length > 0)   { mostrarToast('⚠️ ' + errores[0]); return; }

        setEstadoBotonFamiliar(true);

        try {
            const respuesta = await fetch('/generar-plan-familiar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ miembros })
            });

            if (respuesta.status === 503) {
                mostrarToast('🚦 Nuestra IA está en alto tráfico, intenta pronto.');
                return;
            }

            const datos = await respuesta.json();

            if (datos.exito) {
                renderizarResultadoFamiliar(datos, miembros);
            } else {
                const msg = datos.error || 'Error desconocido';
                if (msg.includes('503') || msg.toLowerCase().includes('quota') || msg.toLowerCase().includes('overloaded')) {
                    mostrarToast('🚦 Nuestra IA está en alto tráfico, intenta pronto.');
                } else {
                    mostrarToast('❌ Error: ' + msg);
                }
            }
        } catch (err) {
            mostrarToast('❌ Error de conexión. Verifica que el servidor esté activo.');
        } finally {
            setEstadoBotonFamiliar(false);
        }
    });
}

// Renderiza el resultado del plan familiar
function renderizarResultadoFamiliar(datos, miembros) {
    const seccionForm   = document.getElementById('seccion-familiar');
    const seccionResult = document.getElementById('resultado-familiar');

    seccionForm.style.transition = 'opacity 0.4s';
    seccionForm.style.opacity    = '0';
    setTimeout(() => {
        seccionForm.style.display = 'none';
        seccionResult.classList.remove('hidden');

        const avatares = ['👨', '👩', '👦', '👧', '👴', '👵', '🧑'];
        let html = `
            <div class="familiar-result-header">
                <h2>🍽️ Plan Nutricional Familiar</h2>
                <p>${miembros.length} integrante${miembros.length > 1 ? 's' : ''} • Generado por Comité Médico IA de MIKHUCHIYNCA</p>
            </div>`;

        if (datos.lista_compras) {
            html += `
                <div class="lista-compras">
                    <h3>🛒 Lista de Compras Consolidada</h3>
                    <div class="plan-miembro-content">${datos.lista_compras}</div>
                </div>`;
        }

        if (datos.planes && Array.isArray(datos.planes) && datos.planes.length > 0) {
            datos.planes.forEach((plan, i) => {
                const miembro    = miembros[i] || {};
                const avatar     = avatares[i % avatares.length];
                const tieneSalud = miembro.antecedentes && miembro.antecedentes !== 'Ninguno';
                html += `
                    <div class="plan-miembro-card">
                        <div class="plan-miembro-header">
                            <div class="plan-miembro-avatar">${avatar}</div>
                            <div class="plan-miembro-info">
                                <h3>${plan.nombre || miembro.nombre || 'Miembro ' + (i + 1)}</h3>
                                <span>${miembro.peso ? miembro.peso + ' kg' : ''} ${miembro.edad ? '• ' + miembro.edad + ' años' : ''} ${tieneSalud ? '• ⚠️ ' + miembro.antecedentes : ''}</span>
                            </div>
                        </div>
                        ${tieneSalud ? `<div class="alerta-salud">⚠️ Plan adaptado para: <strong>${miembro.antecedentes}</strong>. Prioriza ingredientes andinos con bajo índice glucémico.</div>` : ''}
                        <div class="plan-miembro-content">${plan.html || ''}</div>
                    </div>`;
            });
        } else if (datos.html) {
            html += `<div class="plan-miembro-card"><div class="plan-miembro-content">${datos.html}</div></div>`;
        }

        html += `
            <button type="button" class="btn-volver-familiar" onclick="volverFormularioFamiliar()">
                ← Modificar el plan familiar
            </button>`;

        seccionResult.innerHTML = html;
        seccionResult.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 400);
}

// Volver al formulario familiar
function volverFormularioFamiliar() {
    const seccionForm   = document.getElementById('seccion-familiar');
    const seccionResult = document.getElementById('resultado-familiar');
    seccionResult.classList.add('hidden');
    seccionForm.style.display = '';
    seccionForm.style.opacity = '1';
    seccionForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
