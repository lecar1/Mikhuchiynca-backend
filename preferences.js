// ==========================================
// preferences.js — Memoria local del usuario
// Guarda peso, estatura, edad y preferencias de plan
// en localStorage. Los antecedentes de salud solo se
// guardan si el usuario lo autoriza explícitamente.
// ==========================================
(function () {
    'use strict';

    const CLAVE = 'mikhuchiynca_perfil_v1';
    const CLAVE_SALUD_OPTIN = 'mikhuchiynca_salud_optin_v1';
    const CLAVE_AVISO = 'mikhuchiynca_aviso_recordado';
    const VERSION = 1;

    const REGIONES = ['Costa', 'Sierra', 'Selva'];
    const GENEROS = ['male', 'female'];
    const ACTIVIDADES = [1.2, 1.375, 1.55, 1.725, 1.9];
    const OBJETIVOS = ['Ganar masa muscular', 'Perder grasa', 'Mantener peso'];
    const ANTECEDENTES = ['Ninguno', 'Diabetes', 'Hipertensión', 'Obesidad'];

    let aplicadoEnEstaCarga = false;

    // ---------- Utilidades ----------

    function numeroEnRango(valor, minimo, maximo) {
        if (valor === null || valor === undefined || valor === '') return undefined;
        const n = Number(valor);
        return Number.isFinite(n) && n >= minimo && n <= maximo ? n : undefined;
    }

    function sanear(datos) {
        const limpio = {};
        if (!datos || typeof datos !== 'object') return limpio;

        const peso = numeroEnRango(datos.peso, 30, 250);
        if (peso !== undefined) limpio.peso = peso;

        const estatura = numeroEnRango(datos.estatura, 100, 250);
        if (estatura !== undefined) limpio.estatura = estatura;

        const edad = numeroEnRango(datos.edad, 15, 100);
        if (edad !== undefined) limpio.edad = Math.round(edad);

        if (typeof datos.genero === 'string' && GENEROS.includes(datos.genero)) {
            limpio.genero = datos.genero;
        }

        if (typeof datos.objetivo === 'string' && OBJETIVOS.includes(datos.objetivo)) {
            limpio.objetivo = datos.objetivo;
        }

        const actividad = Number(datos.actividad);
        if (ACTIVIDADES.includes(actividad)) limpio.actividad = actividad;

        if (typeof datos.region === 'string' && REGIONES.includes(datos.region)) {
            limpio.region = datos.region;
        }

        if (typeof datos.health_history === 'string' && ANTECEDENTES.includes(datos.health_history)) {
            limpio.health_history = datos.health_history;
        }

        return limpio;
    }

    function saludOptInActivo() {
        try {
            return localStorage.getItem(CLAVE_SALUD_OPTIN) === '1';
        } catch (error) {
            return false;
        }
    }

    function escribir(datos) {
        try {
            localStorage.setItem(CLAVE, JSON.stringify({
                version: VERSION,
                actualizadoEn: new Date().toISOString(),
                datos: datos
            }));
            return true;
        } catch (error) {
            console.warn('[preferencias] No se pudo guardar en localStorage:', error);
            return false;
        }
    }

    // ---------- API de almacenamiento ----------

    function cargar() {
        try {
            const bruto = localStorage.getItem(CLAVE);
            if (!bruto) return null;

            const guardado = JSON.parse(bruto);
            if (!guardado || typeof guardado !== 'object') return null;
            if (Number(guardado.version) !== VERSION) return null;

            const datos = sanear(guardado.datos || guardado);
            return Object.keys(datos).length ? datos : null;
        } catch (error) {
            console.warn('[preferencias] No se pudo leer localStorage:', error);
            return null;
        }
    }

    function guardar(parcial) {
        const actuales = cargar() || {};
        const limpioParcial = {};

        // Ignorar valores vacíos para no borrar preferencias ya guardadas
        Object.keys(parcial || {}).forEach((clave) => {
            const valor = parcial[clave];
            if (valor !== '' && valor !== null && valor !== undefined) {
                limpioParcial[clave] = valor;
            }
        });

        const fusionados = sanear(Object.assign({}, actuales, limpioParcial));
        return escribir(fusionados);
    }

    function eliminarCampo(nombre) {
        const actuales = cargar() || {};
        delete actuales[nombre];
        return escribir(actuales);
    }

    function limpiar() {
        try {
            localStorage.removeItem(CLAVE);
            localStorage.removeItem(CLAVE_SALUD_OPTIN);
        } catch (error) {
            console.warn('[preferencias] No se pudo limpiar localStorage:', error);
        }
    }

    // ---------- Lectura y aplicación del formulario ----------

    function valor(id) {
        const el = document.getElementById(id);
        return el ? el.value : '';
    }

    function leerFormulario() {
        const datos = {
            peso: valor('weight'),
            estatura: valor('height'),
            edad: valor('age'),
            genero: valor('gender'),
            objetivo: valor('goal'),
            actividad: valor('activity'),
            region: valor('region')
        };

        if (saludOptInActivo()) {
            datos.health_history = valor('health_history');
        }

        return datos;
    }

    function asignarSiVacio(id, valorDato) {
        if (valorDato === undefined || valorDato === null || valorDato === '') return false;
        const el = document.getElementById(id);
        if (!el || el.value !== '') return false;
        el.value = String(valorDato);
        return true;
    }

    function asignarSelect(id, valorDato) {
        if (valorDato === undefined || valorDato === null || valorDato === '') return false;
        const el = document.getElementById(id);
        if (!el || !el.options) return false;

        const existe = Array.prototype.some.call(el.options, (opcion) => opcion.value === String(valorDato));
        if (!existe) return false;

        el.value = String(valorDato);
        return true;
    }

    function aplicarAlFormulario() {
        if (aplicadoEnEstaCarga) return false;

        const datos = cargar();
        if (!datos) {
            aplicadoEnEstaCarga = true;
            return false;
        }

        let aplicado = false;

        if (asignarSiVacio('weight', datos.peso)) aplicado = true;
        if (asignarSiVacio('height', datos.estatura)) aplicado = true;
        if (asignarSiVacio('age', datos.edad)) aplicado = true;

        if (asignarSelect('gender', datos.genero)) aplicado = true;
        if (asignarSelect('activity', datos.actividad)) aplicado = true;
        if (asignarSelect('region', datos.region)) aplicado = true;

        if (datos.health_history) {
            const el = document.getElementById('health_history');
            if (el && el.value !== datos.health_history) {
                el.value = datos.health_history;
                aplicado = true;
            }
        }

        const objetivoInput = document.getElementById('goal');
        const yaSeleccionado = document.querySelector('.goal-btn[aria-checked="true"]');

        if (datos.objetivo && !yaSeleccionado) {
            const boton = Array.prototype.find.call(
                document.querySelectorAll('.goal-btn'),
                (b) => {
                    const etiqueta = b.querySelector('.goal-label');
                    return etiqueta && etiqueta.textContent.trim() === datos.objetivo;
                }
            );

            if (boton) {
                // Reutiliza el manejador existente de app.js
                boton.click();
                aplicado = true;
            } else if (objetivoInput && !objetivoInput.value) {
                // Caso 'Mantener peso': no existe botón, se restaura solo el valor
                objetivoInput.value = datos.objetivo;
                aplicado = true;
            }
        }

        aplicadoEnEstaCarga = true;
        if (aplicado) avisarRecordatorioUnaVez();
        return aplicado;
    }

    // ---------- Avisos ----------

    function avisar(mensaje, tipo) {
        if (typeof window.mostrarToast === 'function') {
            window.mostrarToast(mensaje, tipo);
        } else {
            console.info('[preferencias]', mensaje);
        }
    }

    function avisarRecordatorioUnaVez() {
        try {
            if (sessionStorage.getItem(CLAVE_AVISO) === '1') return;
            sessionStorage.setItem(CLAVE_AVISO, '1');
        } catch (error) {
            // Sin sessionStorage: se muestra igualmente una vez por carga
        }
        avisar('Hemos recordado tus datos anteriores. Puedes editarlos.', 'info');
    }

    // ---------- Botón "Olvidar mis datos" ----------

    function actualizarBotonOlvidar() {
        const boton = document.getElementById('btn-olvidar-datos');
        if (!boton) return;
        if (cargar()) boton.classList.remove('hidden');
        else boton.classList.add('hidden');
    }

    function conectarBotonOlvidar() {
        const boton = document.getElementById('btn-olvidar-datos');
        if (!boton) return;

        boton.addEventListener('click', () => {
            limpiar();

            ['weight', 'height', 'age'].forEach((id) => {
                const el = document.getElementById(id);
                if (el) el.value = '';
            });

            const genero = document.getElementById('gender');
            if (genero) genero.value = '';

            const actividad = document.getElementById('activity');
            if (actividad) actividad.value = '1.55';

            const region = document.getElementById('region');
            if (region) region.value = 'Costa';

            const antecedentes = document.getElementById('health_history');
            if (antecedentes) antecedentes.value = 'Ninguno';

            const objetivo = document.getElementById('goal');
            if (objetivo) objetivo.value = '';

            document.querySelectorAll('.goal-btn').forEach((b) => {
                b.style.border = '';
                b.style.backgroundColor = '';
                b.setAttribute('aria-checked', 'false');
            });

            const optin = document.getElementById('optin-salud');
            if (optin) optin.checked = false;

            actualizarBotonOlvidar();
            avisar('Hemos olvidado tus datos guardados en este dispositivo.', 'success');
        });
    }

    // ---------- Auto-guardado ----------

    function activarAutoGuardado() {
        const guardarFormulario = () => guardar(leerFormulario());

        ['gender', 'activity', 'region', 'health_history'].forEach((id) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('change', guardarFormulario);
        });

        let temporizador = null;
        ['weight', 'height', 'age'].forEach((id) => {
            const el = document.getElementById(id);
            if (!el) return;
            el.addEventListener('input', () => {
                clearTimeout(temporizador);
                temporizador = setTimeout(guardarFormulario, 500);
            });
        });

        document.querySelectorAll('.goal-btn').forEach((boton) => {
            boton.addEventListener('click', guardarFormulario);
        });

        // Consentimiento explícito para guardar antecedentes de salud
        const optin = document.getElementById('optin-salud');
        if (optin) {
            optin.checked = saludOptInActivo();
            optin.addEventListener('change', () => {
                try {
                    if (optin.checked) {
                        localStorage.setItem(CLAVE_SALUD_OPTIN, '1');
                    } else {
                        localStorage.removeItem(CLAVE_SALUD_OPTIN);
                        eliminarCampo('health_history');
                    }
                } catch (error) {
                    console.warn('[preferencias] No se pudo actualizar el consentimiento:', error);
                }

                if (optin.checked) guardar(leerFormulario());
                actualizarBotonOlvidar();
            });
        }

        // Mantener sincronizadas otras pestañas
        window.addEventListener('storage', (evento) => {
            if (evento.key === CLAVE || evento.key === CLAVE_SALUD_OPTIN) {
                actualizarBotonOlvidar();
            }
        });

        actualizarBotonOlvidar();
    }

    // ---------- API pública ----------

    window.PreferenciasLocales = {
        CLAVE: CLAVE,
        cargar: cargar,
        guardar: guardar,
        limpiar: limpiar,
        eliminarCampo: eliminarCampo,
        leerFormulario: leerFormulario,
        aplicarAlFormulario: aplicarAlFormulario,
        saludOptInActivo: saludOptInActivo
    };

    document.addEventListener('DOMContentLoaded', () => {
        activarAutoGuardado();
        conectarBotonOlvidar();
    });
})();
