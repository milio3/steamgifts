// app/web/static/js/app.js

document.addEventListener('DOMContentLoaded', () => {
    initPasswordToggle();
    initRunBotForm();
    initConfigCategorySorting();
    initConsoleAutoScroll();
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
 * Añade confirmación y estado visual al lanzar el bot desde el Dashboard
 */
function initRunBotForm() {
    const form = document.getElementById('run-bot-form');
    if (form) {
        form.addEventListener('htmx:confirm', (e) => {
            e.preventDefault();
            if (confirm('¿Estás seguro de que quieres iniciar la ejecución del bot?')) {
                e.detail.issueRequest();
            }
        });

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
                    btn.classList.remove('btn-primary');
                    btn.classList.add('btn-warning');
                } else {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-play-fill fs-4 me-1"></i> Iniciar Ejecución';
                    alert('Error al iniciar el bot.');
                }
            }
        });
    }
}

/**
 * Reordenación de categorías con Drag & Drop en la página de Configuración
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
 * Preservación del estado abierto/cerrado de las sesiones de ejecución
 */
function initAccordionStatePreservation() {
    let accordionState = { open: new Set(), closed: new Set() };

    document.body.addEventListener('htmx:beforeSwap', (evt) => {
        if (evt.detail.target.id === 'sessions-container') {
            accordionState = { open: new Set(), closed: new Set() };
            document.querySelectorAll('#sessions-container .accordion-collapse').forEach((el) => {
                if (el.classList.contains('show')) {
                    accordionState.open.add(el.id);
                } else {
                    accordionState.closed.add(el.id);
                }
            });
        }
    });

    document.body.addEventListener('htmx:afterSwap', (evt) => {
        if (evt.detail.target.id === 'sessions-container') {
            // Aplicar estado previo a los acordeones
            accordionState.closed.forEach((id) => {
                const el = document.getElementById(id);
                if (el) {
                    el.classList.remove('show');
                    const btn = document.querySelector(`[data-bs-target="#${id}"]`);
                    if (btn) {
                        btn.classList.add('collapsed');
                        btn.setAttribute('aria-expanded', 'false');
                    }
                }
            });

            accordionState.open.forEach((id) => {
                const el = document.getElementById(id);
                if (el) {
                    el.classList.add('show');
                    const btn = document.querySelector(`[data-bs-target="#${id}"]`);
                    if (btn) {
                        btn.classList.remove('collapsed');
                        btn.setAttribute('aria-expanded', 'true');
                    }
                }
            });
        }
    });
}

/**
 * Auto-scroll hacia abajo de la consola web en el Dashboard
 */
function initConsoleAutoScroll() {
    const consoleBody = document.getElementById('console-body');
    if (!consoleBody) return;

    // Escuchar el evento de HTMX después de actualizar los logs de la consola
    document.body.addEventListener('htmx:afterSwap', (evt) => {
        if (evt.detail.target.id === 'console-logs') {
            consoleBody.scrollTop = consoleBody.scrollHeight;
        }
    });
}

// Inicialización de la preservación de acordeones
initAccordionStatePreservation();

// HTMX Events Globales
document.body.addEventListener('htmx:afterSwap', function(evt) {
    // Si se actualizó el status a 'running', actualizar el botón de ejecución y el badge de la consola
    if (evt.detail.target.id === 'bot-status-container') {
        const isRunning = evt.detail.target.innerHTML.includes('status-pill-running') || 
                          evt.detail.target.innerHTML.includes('Bot en ejecución');
        const btnRun = document.getElementById('btn-run-bot');
        const liveBadge = document.getElementById('console-live-badge');

        if (liveBadge) {
            if (isRunning) {
                liveBadge.className = 'badge bg-success-subtle border border-success-subtle text-success small';
                liveBadge.innerHTML = '<span class="spinner-border spinner-border-sm me-1" style="width: 10px; height: 10px;"></span> Ejecución en curso';
            } else {
                liveBadge.className = 'badge bg-dark border border-secondary text-info small';
                liveBadge.innerHTML = '<i class="bi bi-terminal me-1"></i> Salida de consola';
            }
        }

        if (btnRun) {
            if (isRunning) {
                btnRun.disabled = true;
                btnRun.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> Bot en ejecución...';
                btnRun.classList.remove('btn-primary');
                btnRun.classList.add('btn-warning');
            } else if (!btnRun.innerHTML.includes('Iniciando')) {
                btnRun.disabled = false;
                btnRun.innerHTML = '<svg class="tailwind-svg-icon me-2" xmlns="http://www.w3.org/2000/svg" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" d="M4.5 5.653c0-1.427 1.529-2.33 2.779-1.643l11.54 6.347c1.295.712 1.295 2.573 0 3.286L7.28 19.99c-1.25.687-2.779-.217-2.779-1.643V5.653Z" clip-rule="evenodd" /></svg> Iniciar Ejecución';
                btnRun.classList.add('btn-primary');
                btnRun.classList.remove('btn-warning', 'btn-success');
            }
        }
    }
});
