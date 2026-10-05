// app/web/static/js/app.js

document.addEventListener('DOMContentLoaded', () => {
    initPasswordToggle();
    initRunBotForm();
    initConfigCategorySorting();
    initConsoleAutoScroll();
    initAutocheck();
    initGlobalStateWatcher();
});

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
 * Añade estado visual al lanzar el bot desde el Dashboard sin diálogos de confirmación
 */
function initRunBotForm() {
    const form = document.getElementById('run-bot-form');
    if (form) {
        form.addEventListener('htmx:beforeRequest', () => {
            const btn = document.getElementById('btn-run-bot');
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Iniciando...';
            }
        });
        
        form.addEventListener('htmx:afterRequest', (e) => {
            const btn = document.getElementById('btn-run-bot');
            if (btn) {
                if (e.detail.successful) {
                    btn.innerHTML = '<i class="bi bi-arrow-repeat spin me-2"></i> Ejecución en curso';
                    btn.classList.add('btn-warning');
                    // Refrescar paneles de dashboard
                    triggerAllRefreshes();
                } else {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-play-fill fs-5 me-1"></i> Iniciar Ejecución';
                    btn.classList.remove('btn-warning');
                    alert('Error al iniciar el bot.');
                }
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
    let wasBotRunning = false;
    let lastSeenCheckHash = '';

    document.body.addEventListener('htmx:afterSwap', (evt) => {
        if (evt.detail.target.id === 'console-logs') {
            const content = evt.detail.target.innerHTML || '';
            const isCurrentlyRunning = content.includes('Ejecutando bot en segundo plano') || 
                                       content.includes('INICIANDO EJECUCIÓN') ||
                                       content.includes('Ejecución en curso');

            // Detectar fin de ejecución (pasó de corriendo a finalizado)
            if (wasBotRunning && !isCurrentlyRunning) {
                wasBotRunning = false;
                triggerAllRefreshes();

                // Restaurar botón de ejecución
                const btnRun = document.getElementById('btn-run-bot');
                if (btnRun) {
                    btnRun.disabled = false;
                    btnRun.innerHTML = '<i class="bi bi-play-fill fs-5" style="line-height: 1;"></i><span>Iniciar Ejecución</span>';
                    btnRun.classList.remove('btn-warning');
                }
            } else if (isCurrentlyRunning) {
                wasBotRunning = true;
            }

            // Detectar si terminó una ronda o hubo éxito
            if (content.includes('Ronda terminada:') && wasBotRunning) {
                wasBotRunning = false;
                triggerAllRefreshes();
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

    // Si se actualizó el status del bot
    if (evt.detail.target.id === 'bot-status-container') {
        const isRunning = evt.detail.target.innerHTML.includes('status-pill-running') || 
                          evt.detail.target.innerHTML.includes('Bot en ejecución');
        const btnRun = document.getElementById('btn-run-bot');

        if (btnRun) {
            if (isRunning) {
                btnRun.disabled = true;
                btnRun.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Bot en ejecución...';
                btnRun.classList.remove('btn-primary');
                btnRun.classList.add('btn-warning');
            } else if (!btnRun.innerHTML.includes('Iniciando')) {
                btnRun.disabled = false;
                btnRun.innerHTML = '<i class="bi bi-play-fill fs-5" style="line-height: 1;"></i><span>Iniciar Ejecución</span>';
                btnRun.classList.remove('btn-warning');
            }
        }
    }
});

/**
 * Inicializa los controles del autochecker si el panel existe en el DOM
 */
function initAutocheck() {
    const container = document.getElementById('autocheck-container');
    if (!container) return;
}
