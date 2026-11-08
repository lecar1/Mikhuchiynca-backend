// ==========================================
// history.js — Historial de planes guardados por usuario
// El backend solo devuelve planes del usuario autenticado.
// ==========================================
(function () {
    'use strict';

    const SECCION_ID = 'seccion-historial';
    const LISTA_ID = 'historial-lista';
    const BTN_MAS_ID = 'historial-cargar-mas';

    let paginaActual = 1;
    let hayMas = false;
    let usuarioActivo = false;
    let cargando = false;

    function elemento(id) {
        return document.getElementById(id);
    }

    function mostrarSeccion(autenticado) {
        const seccion = elemento(SECCION_ID);
        if (seccion) seccion.classList.toggle('hidden', !autenticado);
    }

    function formatearFecha(iso) {
        if (!iso) return '';
        const fecha = new Date(iso);
        if (Number.isNaN(fecha.getTime())) return '';
        return fecha.toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit', year: 'numeric' });
    }

    function crearItemHistorial(plan) {
        const item = document.createElement('div');
        item.className = 'historial-item';
        item.dataset.id = plan.id;

        const tope = document.createElement('div');
        tope.className = 'historial-item-top';

        const titulo = document.createElement('h3');
        titulo.className = 'historial-item-titulo';
        titulo.textContent = plan.titulo || 'Plan nutricional';

        const fecha = document.createElement('span');
        fecha.className = 'historial-item-fecha';
        fecha.textContent = formatearFecha(plan.creado_en);

        tope.appendChild(titulo);
        tope.appendChild(fecha);
        item.appendChild(tope);

        if (plan.resumen) {
            const resumen = document.createElement('p');
            resumen.className = 'historial-item-resumen';
            resumen.textContent = plan.resumen;
            item.appendChild(resumen);
        }

        const acciones = document.createElement('div');
        acciones.className = 'historial-item-acciones';

        const botonVer = document.createElement('button');
        botonVer.type = 'button';
        botonVer.className = 'historial-btn historial-btn-ver';
        botonVer.textContent = 'Ver plan';
        botonVer.addEventListener('click', () => window.verPlanHistorial(plan.id));

        const botonEliminar = document.createElement('button');
        botonEliminar.type = 'button';
        botonEliminar.className = 'historial-btn historial-btn-eliminar';
        botonEliminar.textContent = 'Eliminar';
        botonEliminar.addEventListener('click', () => window.eliminarPlanHistorial(plan.id));

        acciones.appendChild(botonVer);
        acciones.appendChild(botonEliminar);
        item.appendChild(acciones);

        return item;
    }

    function renderizarLista(planes, hayMas) {
        const contenedor = elemento(LISTA_ID);
        if (!contenedor) return;

        contenedor.innerHTML = '';

        if (!planes || !planes.length) {
            const mensaje = document.createElement('p');
            mensaje.className = 'historial-vacio';
            mensaje.textContent = 'Aún no tienes planes guardados. Genera tu primer plan nutricional.';
            contenedor.appendChild(mensaje);
            return;
        }

        const fragmento = document.createDocumentFragment();
        planes.forEach((plan) => fragmento.appendChild(crearItemHistorial(plan)));
        contenedor.appendChild(fragmento);

        hayMas = Boolean(hayMas);
        if (hayMas) {
            const botonMas = document.createElement('button');
            botonMas.type = 'button';
            botonMas.id = BTN_MAS_ID;
            botonMas.className = 'historial-btn historial-btn-mas';
            botonMas.textContent = 'Cargar más planes';
            botonMas.addEventListener('click', async () => {
                botonMas.remove();
                paginaActual += 1;
                await cargarHistorialPlanes();
            });
            contenedor.appendChild(botonMas);
        }
    }

    async function cargarHistorialPlanes() {
        const contenedor = elemento(LISTA_ID);
        if (!contenedor) return;

        if (!usuarioActivo) {
            renderizarLista([], false);
            return;
        }

        if (cargando) return;
        cargando = true;

        try {
            const respuesta = await fetch('/api/historial?page=' + encodeURIComponent(String(paginaActual)));
            const datos = await respuesta.json();

            if (respuesta.ok && datos.exito) {
                renderizarLista(datos.planes || [], Boolean(datos.hay_mas));
                hayMas = Boolean(datos.hay_mas);
                const botonMas = elemento(BTN_MAS_ID);
                if (botonMas) {
                    botonMas.addEventListener('click', async () => {
                        paginaActual += 1;
                        await cargarHistorialPlanes();
                    });
                }
            } else if (respuesta.status === 401) {
                usuarioActivo = false;
                mostrarSeccion(false);
                renderizarLista([], false);
            }
        } catch (error) {
            const mensaje = document.createElement('p');
            mensaje.className = 'historial-vacio';
            mensaje.textContent = 'No pudimos cargar tu historial. Intenta de nuevo en unos minutos.';
            elemento(LISTA_ID).appendChild(mensaje);
        } finally {
            cargando = false;
        }
    }

    window.verPlanHistorial = async function (id) {
        try {
            const respuesta = await fetch('/api/historial/' + encodeURIComponent(String(id)));
            const datos = await respuesta.json();

            if (!respuesta.ok || !datos.exito) {
                mostrarToast('No pudimos abrir ese plan. Intenta de nuevo.');
                return;
            }

            const plan = datos.plan;
            const resultDiv = document.getElementById('result');
            const menuDiv = document.getElementById('menuSections');
            const resultMeta = document.getElementById('resultMeta');

            if (resultDiv && menuDiv) {
                document.getElementById('resultado-familiar').classList.add('hidden');
                resultDiv.classList.remove('hidden');
                menuDiv.innerHTML = plan.html || '';
                if (resultMeta) {
                    resultMeta.textContent = (plan.tipo === 'familiar' ? '📚 Plan familiar · ' : '📚 Plan personalizado · ')
                        + (plan.titulo || '')
                        + ' · '
                        + formatearFecha(plan.creado_en);
                }
                resultDiv.scrollIntoView({ behavior: 'smooth' });
            }
        } catch (error) {
            mostrarToast('Error al abrir el plan.');
        }
    };

    window.eliminarPlanHistorial = async function (id) {
        const confirmado = window.confirm('¿Seguro que quieres eliminar este plan de tu historial?');
        if (!confirmado) return;

        try {
            const respuesta = await fetch('/api/historial/' + encodeURIComponent(String(id)), { method: 'DELETE' });
            const datos = await respuesta.json();

            if (respuesta.ok && datos.exito) {
                mostrarToast('Plan eliminado correctamente.', 'success');
                await cargarHistorialPlanes();
            } else if (respuesta.status === 401) {
                usuarioActivo = false;
                mostrarSeccion(false);
            } else {
                mostrarToast(datos.error || 'No se pudo eliminar el plan.');
            }
        } catch (error) {
            mostrarToast('Error al eliminar el plan.');
        }
    };

    function mostrarToast(mensaje, tipo) {
        if (typeof window.mostrarToast === 'function') {
            window.mostrarToast(mensaje, tipo);
        }
    }

    function manejarCambioUsuario(perfil) {
        usuarioActivo = Boolean(perfil && perfil.id);
        mostrarSeccion(usuarioActivo);

        const lista = elemento(LISTA_ID);
        if (lista) lista.innerHTML = '';

        if (usuarioActivo) {
            paginaActual = 1;
            hayMas = false;
            cargarHistorialPlanes();
        }
    }

    document.addEventListener('DOMContentLoaded', () => {
        const btnRecargar = elemento('btn-recargar-historial');
        if (btnRecargar) {
            btnRecargar.addEventListener('click', async () => {
                if (!usuarioActivo) return;
                paginaActual = 1;
                hayMas = false;
                await cargarHistorialPlanes();
            });
        }

        window.addEventListener('usuario-actualizada', (evento) => {
            manejarCambioUsuario((evento.detail) || null);
        });

        window.addEventListener('historial-actualizada', () => {
            if (usuarioActivo) {
                paginaActual = 1;
                hayMas = false;
                cargarHistorialPlanes();
            }
        });
    });
})();
