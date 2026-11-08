// ==========================================
// catalog.js — Catálogo de superalimentos peruanos
// Carga superalimentos_peru.json y lo muestra con
// búsqueda, filtros por región/categoría y ficha.
// ==========================================
(function () {
    'use strict';

    const RUTA_DATOS = '/superalimentos_peru.json';
    const CONTENEDOR_ID = 'contenedor-superalimentos';
    const MODAL_ID = 'catalogo-modal';

    const REGIONES = ['Todas', 'Costa', 'Sierra', 'Selva'];
    const CATEGORIAS = ['Todas', 'Alimento', 'Bebida'];

    let items = [];
    let filtros = { region: 'Todas', categoria: 'Todas', texto: '' };
    let ultimoFoco = null;

    // ---------- Utilidades ----------

    function normalizar(texto) {
        return String(texto || '')
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '')
            .toLowerCase()
            .trim();
    }

    function escaparHtml(texto) {
        return String(texto == null ? '' : texto)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function iconoSuperalimento(item) {
        const nombre = normalizar(item.nombre);

        const mapa = [
            ['maiz', '🌽'], ['quinua', '🌾'], ['kiwicha', '🌾'], ['cañihua', '🌾'],
            ['canihua', '🌾'], ['trigo', '🌾'], ['cebada', '🌾'], ['arroz', '🍚'],
            ['papa', '🥔'], ['camote', '🍠'], ['oca', '🥔'], ['olluco', '🥔'],
            ['mashua', '🥔'], ['yuca', '🥔'],
            ['cacao', '🍫'], ['cafe', '☕'], ['pisco', '🍇'], ['vino', '🍷'],
            ['chicha', '🥤'], ['maca', '🌱'], ['sacha inchi', '🌰'],
            ['aguaje', '🌴'], ['camu camu', '🫐'], ['lucuma', '🟠'],
            ['granadilla', '🍈'], ['chirimoya', '🍈'], ['palta', '🥑'],
            ['aguacate', '🥑'], ['tarwi', '🫘'], ['chocho', '🫘'],
            ['frejol', '🫘'], ['frijol', '🫘'], ['lenteja', '🫘'],
            ['pallar', '🫘'], ['uva', '🍇'], ['maracuya', '🍈'],
            ['aguaymanto', '🍒'], ['cebada', '🌾'], ['tomate', '🍅'],
            ['platano', '🍌'], ['piña', '🍍'], ['pina', '🍍'], ['mango', '🥭'],
            ['papaya', '🍈'], ['cocona', '🍅'], ['aji', '🌶️'], ['rocoto', '🌶️'],
            ['pescado', '🐟'], ['bonito', '🐟'], ['jurel', '🐟'], ['cuy', '🍖'],
            ['alpaca', '🍖'], ['leche', '🥛'], ['queso', '🧀'], ['huevo', '🥚'],
            ['miel', '🍯'], ['alga', '🌿'], ['pollo', '🍗'], ['arandano', '🫐']
        ];

        for (const [clave, emoji] of mapa) {
            if (nombre.includes(clave)) return emoji;
        }

        return item.categoria === 'Bebida' ? '🥤' : '🌿';
    }

    function claseRegion(region) {
        const r = normalizar(region);
        if (r === 'costa') return 'region-costa';
        if (r === 'sierra') return 'region-sierra';
        if (r === 'selva') return 'region-selva';
        return '';
    }

    function formatoNumero(valor) {
        const n = Number(valor);
        if (!Number.isFinite(n)) return '—';
        return n % 1 === 0 ? String(n) : n.toFixed(1);
    }

    // ---------- Render de la sección ----------

    function montarEstructura() {
        const contenedor = document.getElementById(CONTENEDOR_ID);
        if (!contenedor) return null;

        contenedor.innerHTML = `
            <div class="catalog-header">
                <div class="catalog-titulo-bloque">
                    <h2 class="catalog-titulo">
                        <span aria-hidden="true">🌿</span> Superalimentos del Perú
                    </h2>
                    <p class="catalog-subtitulo">
                        Explora alimentos y bebidas de la costa, sierra y selva. Toca una tarjeta para ver su información nutricional.
                    </p>
                </div>
                <div class="catalog-buscador">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <circle cx="11" cy="11" r="8"></circle>
                        <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                    </svg>
                    <input type="search" id="catalogo-busqueda" placeholder="Buscar por nombre, beneficio o departamento…" autocomplete="off" aria-label="Buscar superalimentos">
                </div>
            </div>

            <div class="catalog-filtros" role="group" aria-label="Filtrar por región">
                ${REGIONES.map((region) => `
                    <button type="button" class="catalog-chip${region === 'Todas' ? ' active' : ''}" data-filtro="region" data-valor="${region}">
                        ${region === 'Todas' ? 'Todas las regiones' : region}
                    </button>`).join('')}
            </div>

            <div class="catalog-filtros" role="group" aria-label="Filtrar por categoría">
                ${CATEGORIAS.map((categoria) => `
                    <button type="button" class="catalog-chip${categoria === 'Todas' ? ' active' : ''}" data-filtro="categoria" data-valor="${categoria}">
                        ${categoria === 'Todas' ? 'Todas las categorías' : categoria}
                    </button>`).join('')}
            </div>

            <p class="catalog-contador" id="catalogo-contador" aria-live="polite"></p>
            <div class="catalog-grid" id="catalogo-grid"></div>`;

        return contenedor;
    }

    function montarModal() {
        if (document.getElementById(MODAL_ID)) return;

        const modal = document.createElement('div');
        modal.id = MODAL_ID;
        modal.className = 'catalog-modal hidden';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', 'catalogo-modal-title');

        modal.innerHTML = `
            <div class="catalog-modal-backdrop" data-cerrar-catalogo></div>
            <div class="catalog-modal-card" role="document">
                <button type="button" class="catalog-modal-close" data-cerrar-catalogo aria-label="Cerrar detalles">&times;</button>
                <div id="catalogo-modal-body"></div>
            </div>`;

        document.body.appendChild(modal);
    }

    // ---------- Tarjetas ----------

    function crearTarjeta(item) {
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'catalog-card';
        boton.dataset.id = item.id;
        boton.setAttribute('aria-label', `Ver detalles de ${item.nombre}`);

        const nutricion = item.nutricion_100g || {};
        const beneficio = (item.beneficios && item.beneficios[0]) || item.descripcion || '';

        boton.innerHTML = `
            <div class="catalog-card-top">
                <span class="catalog-icon" aria-hidden="true">${iconoSuperalimento(item)}</span>
                <span class="catalog-region ${claseRegion(item.region)}">${escaparHtml(item.region)}</span>
            </div>
            <h3 class="catalog-card-nombre">${escaparHtml(item.nombre)}</h3>
            <p class="catalog-card-desc">${escaparHtml(beneficio)}</p>
            <div class="catalog-card-macros">
                <span><strong>${formatoNumero(nutricion.calorias)}</strong> kcal</span>
                <span><strong>${formatoNumero(nutricion.proteinas)}</strong> g prot.</span>
            </div>
            <span class="catalog-card-ver">Ver detalles <span aria-hidden="true">→</span></span>`;

        boton.addEventListener('click', () => abrirDetalle(item.id));
        return boton;
    }

    // ---------- Filtrado y render ----------

    function coincide(item) {
        if (filtros.region !== 'Todas' && item.region !== filtros.region) return false;
        if (filtros.categoria !== 'Todas' && item.categoria !== filtros.categoria) return false;

        if (!filtros.texto) return true;

        const texto = normalizar(filtros.texto);
        const campos = [
            item.nombre,
            item.descripcion,
            item.region,
            item.categoria,
            (item.departamentos || []).join(' '),
            (item.beneficios || []).join(' ')
        ];

        return campos.some((campo) => normalizar(campo).includes(texto));
    }

    function renderizar() {
        const grid = document.getElementById('catalogo-grid');
        const contador = document.getElementById('catalogo-contador');
        if (!grid) return;

        const visibles = items.filter(coincide);

        grid.innerHTML = '';

        if (!visibles.length) {
            grid.innerHTML = `
                <div class="catalog-vacio">
                    <span aria-hidden="true">🔎</span>
                    <p>No encontramos superalimentos con esos filtros.</p>
                    <button type="button" class="catalog-chip" id="catalogo-limpiar">Limpiar filtros</button>
                </div>`;

            const limpiar = document.getElementById('catalogo-limpiar');
            if (limpiar) limpiar.addEventListener('click', limpiarFiltros);
        } else {
            const fragmento = document.createDocumentFragment();
            visibles.forEach((item) => fragmento.appendChild(crearTarjeta(item)));
            grid.appendChild(fragmento);
        }

        if (contador) {
            contador.textContent = `Mostrando ${visibles.length} de ${items.length} superalimentos`;
        }
    }

    function limpiarFiltros() {
        filtros = { region: 'Todas', categoria: 'Todas', texto: '' };

        const buscador = document.getElementById('catalogo-busqueda');
        if (buscador) buscador.value = '';

        document.querySelectorAll('.catalog-chip[data-filtro]').forEach((chip) => {
            const esTodos = chip.dataset.valor === 'Todas';
            chip.classList.toggle('active', esTodos);
        });

        renderizar();
    }

    function activarFiltros() {
        let temporizador = null;

        const buscador = document.getElementById('catalogo-busqueda');
        if (buscador) {
            buscador.addEventListener('input', () => {
                clearTimeout(temporizador);
                temporizador = setTimeout(() => {
                    filtros.texto = buscador.value;
                    renderizar();
                }, 200);
            });
        }

        document.querySelectorAll('.catalog-chip[data-filtro]').forEach((chip) => {
            chip.addEventListener('click', () => {
                const tipo = chip.dataset.filtro;
                filtros[tipo] = chip.dataset.valor;

                document.querySelectorAll(`.catalog-chip[data-filtro="${tipo}"]`).forEach((otro) => {
                    otro.classList.toggle('active', otro === chip);
                });

                renderizar();
            });
        });
    }

    // ---------- Ficha de detalle ----------

    function abrirDetalle(id) {
        const item = items.find((x) => String(x.id) === String(id));
        if (!item) return;

        const modal = document.getElementById(MODAL_ID);
        const cuerpo = document.getElementById('catalogo-modal-body');
        if (!modal || !cuerpo) return;

        const nutricion = item.nutricion_100g || {};
        const departamentos = (item.departamentos || []).join(', ');
        const beneficios = (item.beneficios || [])
            .map((beneficio) => `<li>${escaparHtml(beneficio)}</li>`)
            .join('');

        cuerpo.innerHTML = `
            <div class="catalog-detalle-cabecera">
                <span class="catalog-detalle-icono" aria-hidden="true">${iconoSuperalimento(item)}</span>
                <div>
                    <h3 id="catalogo-modal-title">${escaparHtml(item.nombre)}</h3>
                    <p class="catalog-detalle-meta">
                        <span class="catalog-region ${claseRegion(item.region)}">${escaparHtml(item.region)}</span>
                        <span>${escaparHtml(item.categoria)}</span>
                        ${departamentos ? `<span>· ${escaparHtml(departamentos)}</span>` : ''}
                    </p>
                </div>
            </div>

            <p class="catalog-detalle-descripcion">${escaparHtml(item.descripcion)}</p>

            <h4 class="catalog-detalle-subtitulo">Beneficios</h4>
            <ul class="catalog-detalle-beneficios">${beneficios || '<li>Información no disponible.</li>'}</ul>

            <h4 class="catalog-detalle-subtitulo">Información nutricional <span>(por 100 g)</span></h4>
            <div class="catalog-nutricion">
                <div><strong>${formatoNumero(nutricion.calorias)}</strong><span>kcal</span></div>
                <div><strong>${formatoNumero(nutricion.proteinas)}</strong><span>Proteínas (g)</span></div>
                <div><strong>${formatoNumero(nutricion.carbohidratos)}</strong><span>Carbohidratos (g)</span></div>
                <div><strong>${formatoNumero(nutricion.grasas)}</strong><span>Grasas (g)</span></div>
            </div>

            <p class="catalog-detalle-aviso">
                Valores aproximados por 100 g. La información es referencial y no sustituye la asesoría de un profesional de la salud.
            </p>`;

        ultimoFoco = document.activeElement;
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        const cerrar = modal.querySelector('.catalog-modal-close');
        if (cerrar) cerrar.focus();
    }

    function cerrarDetalle() {
        const modal = document.getElementById(MODAL_ID);
        if (!modal || modal.classList.contains('hidden')) return;

        modal.classList.add('hidden');
        document.body.style.overflow = '';

        if (ultimoFoco && typeof ultimoFoco.focus === 'function') {
            ultimoFoco.focus();
        }
        ultimoFoco = null;
    }

    function activarModal() {
        const modal = document.getElementById(MODAL_ID);
        if (!modal) return;

        modal.addEventListener('click', (evento) => {
            if (evento.target.closest('[data-cerrar-catalogo]')) cerrarDetalle();
        });

        document.addEventListener('keydown', (evento) => {
            if (evento.key === 'Escape') cerrarDetalle();
        });
    }

    // ---------- Carga de datos ----------

    async function cargarCatalogo() {
        const contenedor = document.getElementById(CONTENEDOR_ID);
        if (!contenedor) return;

        montarModal();

        try {
            const respuesta = await fetch(RUTA_DATOS);
            if (!respuesta.ok) throw new Error('HTTP ' + respuesta.status);

            const datos = await respuesta.json();
            if (!Array.isArray(datos) || !datos.length) throw new Error('Datos vacíos');

            items = datos;
            montarEstructura();
            activarFiltros();
            activarModal();
            renderizar();
        } catch (error) {
            console.error('[catalogo] No se pudo cargar:', error);
            contenedor.innerHTML = `
                <div class="catalog-error">
                    <span aria-hidden="true">⚠️</span>
                    <p>No pudimos cargar el catálogo de superalimentos.</p>
                    <button type="button" class="catalog-chip" id="catalogo-reintentar">Reintentar</button>
                </div>`;

            const reintentar = document.getElementById('catalogo-reintentar');
            if (reintentar) reintentar.addEventListener('click', cargarCatalogo);
        }
    }

    document.addEventListener('DOMContentLoaded', cargarCatalogo);
})();
