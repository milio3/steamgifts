// app/web/static/js/app.js

let botStatusPollingInterval = null;
let isBotCurrentlyRunning = false;

document.addEventListener('DOMContentLoaded', () => {
    initPasswordToggle();
    initRunBotForm();
    initConfigCategorySorting();
    initConsoleAutoScroll();
    initAutocheck();
    initToastListener();
    initGlobalStateWatcher();
    // Chequeo inicial de estado
    checkBotStatus();
});

/**
 * Muestra un Toast flotante moderno en la esquina inferior derecha
 */
function showToast(message, type = 'info') {
    const toastEl = document.getElementById('appToast');
    const toastMsg = document.getElementById('appToastMsg');
    const toastIcon = document.getElementById('appToastIcon');
    if (!toastEl || !toastMsg || !toastIcon) return;

    toastMsg.textContent = message;

    // Ajustar icono y color según el tipo
    toastIcon.className = 'bi fs-6';
    if (type === 'success') {
        toastIcon.classList.add('bi-check-circle-fill', 'text-success');
    } else if (type === 'warning') {
        toastIcon.classList.add('bi-exclamation-triangle-fill', 'text-warning');
    } else if (type === 'danger') {
        toastIcon.classList.add('bi-x-circle-fill', 'text-danger');
    } else {
        toastIcon.classList.add('bi-info-circle-fill', 'text-info');
    }

    if (window.bootstrap && window.bootstrap.Toast) {
        const toast = window.bootstrap.Toast.getOrCreateInstance(toastEl, { delay: 4000 });
        toast.show();
    }
}

/**
 * Escucha eventos HTMX o CustomEvents para mostrar toasts
 */
function initToastListener() {
    document.body.addEventListener('showToast', (evt) => {
        const detail = evt.detail || {};
        showToast(detail.message || 'Notificación', detail.type || 'info');
    });

    // Detectar cabecera HX-Trigger en respuestas HTMX
    document.body.addEventListener('htmx:afterOnLoad', (evt) => {
        const xhr = evt.detail.xhr;
        if (xhr) {
            const triggerHeader = xhr.getResponseHeader('HX-Trigger');
            if (triggerHeader) {
                try {
                    const parsed = JSON.parse(triggerHeader);
                    if (parsed.showToast) {
                        showToast(parsed.showToast.message, parsed.showToast.type);
                    }
                } catch (e) {
                    // Si no es JSON estándar, ignorar
                }
            }
        }
    });
}

/**
 * Permite mostrar u ocultar el valor del PHPSESSID en la configuración
 */
function initPasswordToggle() {
    const toggleBtn = document.getElementById('toggle-cookie-btn');
    const cookieInput = document.getElementById('cookie-input');
    
    if (toggleBtn && cookieInput) {
        toggleBtn.addEventListener('click', () => {
            const type = cookieInput.getAttribute('type') === 'password' ? 'text' : 'password';
            cookieInput.setAttribute('type', type);
            
            const icon = toggleBtn.querySelector('i');
            if (type === 'text') {
                icon.classList.remove('bi-eye');
                icon.classList.add('bi-eye-slash');
            } else {
                icon.classList.remove('bi-eye-slash');
                icon.classList.add('bi-eye');
            }
        });
    }
}

/**
 * Establece el estado visual del botón de lanzamiento como "En ejecución"
 */
function setBotRunningState() {
    isBotCurrentlyRunning = true;
    const btn = document.getElementById('btn-run-bot');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span><span>Ejecución en curso</span>';
        btn.classList.add('btn-warning');
    }
    startBotStatusPolling();
}

/**
 * Restablece el botón de lanzamiento a su estado original listo para ejecutar
 */
function setBotIdleState() {
    isBotCurrentlyRunning = false;
    const btn = document.getElementById('btn-run-bot');
    if (btn) {
        btn.disabled = false;
        btn.classList.remove('btn-warning');
        btn.innerHTML = '<i class="bi bi-play-fill fs-5" style="line-height: 1;"></i><span>Iniciar Ejecución</span>';
    }
    stopBotStatusPolling();
}

/**
 * Carga el modal de la última ejecución y lo abre (se cierra al pinchar fuera)
 */
async function openLatestRunModal() {
    const modalBody = document.getElementById('runDetailModalBody');
    const modalEl = document.getElementById('runDetailModal');
    if (!modalEl || !modalBody) return;

    try {
        const resp = await fetch('/partials/runs/latest/modal');
        if (resp.ok) {
            const html = await resp.text();
            modalBody.innerHTML = html;
            if (window.bootstrap && window.bootstrap.Modal) {
                const modal = window.bootstrap.Modal.getOrCreateInstance(modalEl, {
                    backdrop: true,
                    keyboard: true
                });
                modal.show();
            }
        }
    } catch (err) {
        console.error('Error al cargar el modal de detalle:', err);
    }
}

/**
 * Consulta el estado actual del bot mediante la API
 */
async function checkBotStatus() {
    try {
        const resp = await fetch('/api/v1/bot/status');
        if (resp.ok) {
            const data = await resp.json();
            if (data.status === 'running') {
                if (!isBotCurrentlyRunning) {
                    setBotRunningState();
                }
            } else {
                if (isBotCurrentlyRunning) {
                    // Ha terminado la ejecución
                    setBotIdleState();
                    triggerAllRefreshes();
                    openLatestRunModal();
                }
            }
        }
    } catch (e) {
        // En caso de fallo de red puntual
    }
}

/**
 * Inicia el polling activo mientras el bot está corriendo
 */
function startBotStatusPolling() {
    if (botStatusPollingInterval) return;
    botStatusPollingInterval = setInterval(() => {
        checkBotStatus();
    }, 1500);
}

/**
 * Detiene el polling de estado
 */
function stopBotStatusPolling() {
    if (botStatusPollingInterval) {
        clearInterval(botStatusPollingInterval);
        botStatusPollingInterval = null;
    }
}

/**
 * Añade estado visual al lanzar el bot desde el Dashboard
 */
function initRunBotForm() {
    const form = document.getElementById('run-bot-form');
    if (form) {
        form.addEventListener('htmx:beforeRequest', () => {
            setBotRunningState();
        });
        
        form.addEventListener('htmx:afterRequest', (e) => {
            if (e.detail.successful) {
                // Notificación mediante Toast
                showToast('¡Ejecución iniciada! Procesando sorteos en segundo plano...', 'success');
                triggerAllRefreshes();
            } else {
                setBotIdleState();
                showToast('Error al iniciar la ejecución del bot.', 'danger');
            }
        });
    }
}

/**
 * Reordenación de categorías con Drag & Drop en la página/modal de Configuración
 */
function initConfigCategorySorting() {
    const list = document.getElementById('config-category-list');
    if (!list) return;

    function renumberCategories() {
        const items = Array.from(list.querySelectorAll('.category-sortable-item'));
        items.forEach((item, index) => {
            const nameEl = item.querySelector('.category-display-name');
            const rawLabel = item.dataset.rawLabel || '';
            if (nameEl && rawLabel) {
                nameEl.textContent = `${index + 1}. ${rawLabel}`;
            }
        });
    }

    let draggedItem = null;

    list.addEventListener('dragstart', (e) => {
        const item = e.target.closest('.category-sortable-item');
        if (!item) return;
        draggedItem = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', item.dataset.category);
    });

    list.addEventListener('dragend', (e) => {
        const item = e.target.closest('.category-sortable-item');
        if (item) item.classList.remove('dragging');
        list.querySelectorAll('.category-sortable-item').forEach(el => el.classList.remove('drag-over'));
        draggedItem = null;
    });

    list.addEventListener('dragover', (e) => {
        e.preventDefault();
        const overItem = e.target.closest('.category-sortable-item');
        if (!overItem || overItem === draggedItem) return;

        list.querySelectorAll('.category-sortable-item').forEach(el => el.classList.remove('drag-over'));
        overItem.classList.add('drag-over');
    });

    list.addEventListener('drop', (e) => {
        e.preventDefault();
        const overItem = e.target.closest('.category-sortable-item');
        if (overItem && draggedItem && overItem !== draggedItem) {
            const items = Array.from(list.querySelectorAll('.category-sortable-item'));
            const draggedIdx = items.indexOf(draggedItem);
            const targetIdx = items.indexOf(overItem);

            if (draggedIdx < targetIdx) {
                overItem.after(draggedItem);
            } else {
                overItem.before(draggedItem);
            }

            renumberCategories();
        }
        list.querySelectorAll('.category-sortable-item').forEach(el => el.classList.remove('drag-over'));
    });
}

/**
 * Auto-scroll inteligente de la consola web:
 * Si el usuario se desplaza hacia arriba para leer logs antiguos, NO se fuerza el scroll al fondo.
 * Si el usuario está al fondo (o vuelve a bajar), se mantiene el auto-scroll activo.
 */
function initConsoleAutoScroll() {
    const consoleBody = document.getElementById('console-body');
    if (!consoleBody) return;

    let userScrolledUp = false;
    const scrollThreshold = 35; // px de margen desde el fondo

    consoleBody.addEventListener('scroll', () => {
        const distanceFromBottom = consoleBody.scrollHeight - consoleBody.scrollTop - consoleBody.clientHeight;
        userScrolledUp = distanceFromBottom > scrollThreshold;
    });

    document.body.addEventListener('htmx:afterSwap', (evt) => {
        if (evt.detail.target.id === 'console-logs') {
            if (!userScrolledUp) {
                consoleBody.scrollTop = consoleBody.scrollHeight;
            }
        }
    });

    // Si se limpia la consola, reiniciar estado de scroll al principio
    document.body.addEventListener('htmx:afterRequest', (evt) => {
        if (evt.detail.successful && evt.detail.pathInfo && evt.detail.pathInfo.requestPath.includes('clear-console')) {
            userScrolledUp = false;
            consoleBody.scrollTop = 0;
        }
    });
}

/**
 * Dispara eventos de actualización globales a todos los componentes HTMX
 */
function triggerAllRefreshes() {
    if (window.htmx) {
        window.htmx.trigger(document.body, 'refreshStats');
        window.htmx.trigger(document.body, 'refreshSessions');
        window.htmx.trigger(document.body, 'refreshAccount');
        window.htmx.trigger(document.body, 'refreshAutocheck');
    }
}

/**
 * Observador global de estado: vigila el fin de ejecuciones y chequeos para actualizar la página automáticamente
 */
function initGlobalStateWatcher() {
    let lastSeenCheckHash = '';

    document.body.addEventListener('htmx:afterSwap', (evt) => {
        if (evt.detail.target.id === 'console-logs') {
            const content = evt.detail.target.innerHTML || '';
            const isCurrentlyRunning = content.includes('Ejecutando bot en segundo plano') || 
                                       content.includes('INICIANDO EJECUCIÓN') ||
                                       content.includes('Ejecución en curso');

            // Detectar fin de ejecución desde la consola
            if (isBotCurrentlyRunning && !isCurrentlyRunning) {
                setBotIdleState();
                triggerAllRefreshes();
                openLatestRunModal();
            } else if (isCurrentlyRunning && !isBotCurrentlyRunning) {
                setBotRunningState();
            }

            if (content.includes('Ronda terminada:') && isBotCurrentlyRunning) {
                setBotIdleState();
                triggerAllRefreshes();
                openLatestRunModal();
            }

            // Detectar nuevos chequeos de puntos en la consola
            const matchChecker = content.match(/Chequeo #\d+:\s*(\d+)\s*P/gi);
            if (matchChecker && matchChecker.length > 0) {
                const latestCheck = matchChecker[matchChecker.length - 1];
                if (latestCheck !== lastSeenCheckHash) {
                    lastSeenCheckHash = latestCheck;
                    if (window.htmx) {
                        window.htmx.trigger(document.body, 'refreshAccount');
                        window.htmx.trigger(document.body, 'refreshStats');
                        window.htmx.trigger(document.body, 'refreshAutocheck');
                    }
                }
            }
        }
    });
}

// HTMX Events Globales
document.body.addEventListener('htmx:afterSwap', function(evt) {
    // Si se cargó el contenido del modal de configuración, inicializar sus controles
    if (evt.detail.target.id === 'configModalContent') {
        initPasswordToggle();
        initConfigCategorySorting();
    }
});

/**
 * Inicializa los controles del autochecker si el panel existe en el DOM
 */
function initAutocheck() {
    const container = document.getElementById('autocheck-container');
    if (!container) return;
}
