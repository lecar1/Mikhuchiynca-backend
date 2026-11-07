// ==========================================
// export.js — Exportación del plan a PDF
// Usa el motor de impresión nativo del navegador
// (window.print + @media print), sin dependencias.
// ==========================================
(function () {
    'use strict';

    const ID_ZONA = 'zona-impresion';
    let tituloOriginal = null;
    let limpiezaEnCurso = false;
    let sesionActual = 0;

    // Fecha legible en español para la cabecera del documento
    function fechaLarga() {
        try {
            return new Intl.DateTimeFormat('es-PE', { dateStyle: 'long' }).format(new Date());
        } catch (error) {
            return new Date().toLocaleDateString();
        }
    }

    // Fecha corta para el nombre sugerido del archivo
    function fechaArchivo() {
        const d = new Date();
        const p = (n) => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    }

    // Email del usuario solo si hay sesión visible en la interfaz
    function emailUsuario() {
        const contenedor = document.getElementById('usuario-autenticado');
        const email = document.getElementById('user-display-email');
        if (!contenedor || contenedor.classList.contains('hidden')) return '';
        return email ? email.textContent.trim() : '';
    }

    // Elimina del clon todo lo interactivo y los estilos del tema oscuro
    function limpiarNodo(raiz) {
        raiz.querySelectorAll(
            'button, svg, script, style, link, iframe, .quick-reply, ' +
            '.btn-volver-familiar, .btn-descargar-pdf, .toast'
        ).forEach((nodo) => nodo.remove());

        [raiz, ...raiz.querySelectorAll('*')].forEach((el) => {
            if (!el || el.nodeType !== 1) return;
            el.removeAttribute('id');
            el.removeAttribute('style');
            ['onclick', 'onerror', 'onload', 'onmouseover', 'onmouseout']
                .forEach((atributo) => el.removeAttribute(atributo));
        });

        return raiz;
    }

    function crearEncabezado(tipo, cantidadMiembros) {
        const header = document.createElement('header');
        header.className = 'pdf-cabecera';

        const marca = document.createElement('div');
        marca.className = 'pdf-marca';
        marca.textContent = 'MIKHUCHIYNCA';
        header.appendChild(marca);

        const subtitulo = document.createElement('p');
        subtitulo.className = 'pdf-subtitulo';
        subtitulo.textContent = tipo === 'familiar'
            ? 'Plan nutricional familiar'
            : 'Plan nutricional y rutina personalizada';
        header.appendChild(subtitulo);

        const meta = document.createElement('p');
        meta.className = 'pdf-fecha';
        const partes = [];
        const email = emailUsuario();
        if (email) partes.push(email);
        if (tipo === 'familiar' && cantidadMiembros) {
            partes.push(cantidadMiembros + ' integrante' + (cantidadMiembros > 1 ? 's' : ''));
        }
        partes.push(fechaLarga());
        meta.textContent = partes.join(' · ');
        header.appendChild(meta);

        return header;
    }

    function crearPie() {
        const footer = document.createElement('footer');
        footer.className = 'pdf-pie';
        footer.textContent = 'Este plan es orientativo y no sustituye la valoración de un profesional de la salud.';
        return footer;
    }

    // Contenido del plan individual (#result)
    function contenidoIndividual() {
        const result = document.getElementById('result');
        const menu = document.getElementById('menuSections');
        if (!result || result.classList.contains('hidden') || !menu || !menu.textContent.trim()) {
            return null;
        }

        const fragmento = document.createDocumentFragment();

        const meta = document.getElementById('resultMeta');
        if (meta && meta.textContent.trim()) {
            const parrafo = document.createElement('p');
            parrafo.className = 'pdf-meta';
            parrafo.textContent = meta.textContent.trim();
            fragmento.appendChild(parrafo);
        }

        const calorias = document.getElementById('caloriesSummary');
        if (calorias && calorias.textContent.trim()) {
            fragmento.appendChild(limpiarNodo(calorias.cloneNode(true)));
        }

        fragmento.appendChild(limpiarNodo(menu.cloneNode(true)));

        const superfoods = document.getElementById('superfoodsRecommendation');
        if (superfoods && superfoods.textContent.trim()) {
            fragmento.appendChild(limpiarNodo(superfoods.cloneNode(true)));
        }

        return { contenido: fragmento, miembros: 0 };
    }

    // Contenido del plan familiar (#resultado-familiar)
    function contenidoFamiliar() {
        const result = document.getElementById('resultado-familiar');
        if (!result || result.classList.contains('hidden') || !result.textContent.trim()) {
            return null;
        }

        const clon = result.cloneNode(true);

        // La cabecera visual se reemplaza por la cabecera del documento
        const cabeceraFamiliar = clon.querySelector('.familiar-result-header');
        if (cabeceraFamiliar) cabeceraFamiliar.remove();

        const miembros = result.querySelectorAll('.plan-miembro-card').length;
        limpiarNodo(clon);

        const fragmento = document.createDocumentFragment();
        fragmento.appendChild(clon);
        return { contenido: fragmento, miembros };
    }

    function construirDocumento(tipo) {
        const datos = tipo === 'familiar' ? contenidoFamiliar() : contenidoIndividual();
        if (!datos) return null;

        const articulo = document.createElement('article');
        articulo.className = 'pdf-documento';
        articulo.appendChild(crearEncabezado(tipo, datos.miembros));

        const cuerpo = document.createElement('section');
        cuerpo.className = 'pdf-cuerpo';
        cuerpo.appendChild(datos.contenido);
        articulo.appendChild(cuerpo);

        articulo.appendChild(crearPie());
        return articulo;
    }

    function finalizar() {
        if (limpiezaEnCurso) return;
        limpiezaEnCurso = true;

        const zona = document.getElementById(ID_ZONA);
        if (zona) zona.remove();

        document.body.classList.remove('imprimiendo-plan');

        if (tituloOriginal !== null) {
            document.title = tituloOriginal;
            tituloOriginal = null;
        }

        setTimeout(() => { limpiezaEnCurso = false; }, 400);
    }

    function avisar(mensaje, tipo) {
        if (typeof window.mostrarToast === 'function') {
            window.mostrarToast(mensaje, tipo);
        } else {
            console.warn('[export]', mensaje);
        }
    }

    function exportarPlan(tipo) {
        tipo = tipo === 'familiar' ? 'familiar' : 'individual';

        const documento = construirDocumento(tipo);
        if (!documento) {
            avisar('Genera un plan antes de descargarlo.', 'error');
            return;
        }

        const idBoton = tipo === 'familiar' ? 'btn-descargar-pdf-familiar' : 'btn-descargar-pdf';
        const boton = document.getElementById(idBoton);
        const htmlOriginal = boton ? boton.innerHTML : '';
        const sesion = ++sesionActual;

        try {
            // Zona dedicada fuera del contenedor visual
            let zona = document.getElementById(ID_ZONA);
            if (!zona) {
                zona = document.createElement('div');
                zona.id = ID_ZONA;
                document.body.appendChild(zona);
            }
            zona.innerHTML = '';
            zona.appendChild(documento);

            tituloOriginal = document.title;
            document.title = `MIKHUCHIYNCA_plan_${tipo}_${fechaArchivo()}`;
            document.body.classList.add('imprimiendo-plan');

            if (boton) {
                boton.disabled = true;
                boton.textContent = 'Preparando PDF…';
            }

            window.addEventListener('afterprint', () => {
                if (sesion === sesionActual) finalizar();
            }, { once: true });

            // Pequeña espera para que el navegador aplique los estilos de impresión
            setTimeout(() => {
                try {
                    window.print();
                } catch (error) {
                    console.error('[export] Error al imprimir:', error);
                    avisar('No se pudo abrir el diálogo de impresión.', 'error');
                    finalizar();
                }
            }, 80);

            // Red de seguridad por si afterprint no se dispara
            setTimeout(() => {
                if (sesion === sesionActual) finalizar();
            }, 60000);
        } catch (error) {
            console.error('[export] Error al preparar el PDF:', error);
            finalizar();
            avisar('No se pudo preparar el PDF.', 'error');
        } finally {
            if (boton) {
                boton.disabled = false;
                boton.innerHTML = htmlOriginal;
            }
        }
    }

    // API pública
    window.exportarPlan = exportarPlan;

    // Delegación de eventos: cubre el botón individual y el generado dinámicamente
    document.addEventListener('click', (evento) => {
        const boton = evento.target.closest('#btn-descargar-pdf, #btn-descargar-pdf-familiar');
        if (!boton) return;
        evento.preventDefault();
        exportarPlan(boton.id === 'btn-descargar-pdf-familiar' ? 'familiar' : 'individual');
    });
})();
