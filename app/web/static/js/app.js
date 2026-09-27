// app/web/static/js/app.js

// Funcionalidad modular principal
document.addEventListener('DOMContentLoaded', () => {
    initPasswordToggle();
    initRunBotForm();
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
 * Añade una confirmación antes de lanzar el bot manualmente
 * y gestiona el estado visual del botón
 */
function initRunBotForm() {
    const form = document.getElementById('run-bot-form');
    if (form) {
        form.addEventListener('htmx:confirm', (e) => {
            e.preventDefault();
            if (confirm('¿Estás seguro de que quieres iniciar la ejecución del bot con las categorías seleccionadas?')) {
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
                    btn.innerHTML = '<i class="bi bi-check-lg fs-5"></i> ¡Iniciado!';
                    btn.classList.remove('btn-primary');
                    btn.classList.add('btn-success');
                } else {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-play-fill fs-5"></i> Ejecutar Bot';
                    alert('Error al iniciar el bot.');
                }
            }
        });
    }
}

// HTMX Events
document.body.addEventListener('htmx:afterSwap', function(evt) {
    // Si se actualizó el status a 'running', deshabilitar el botón de ejecutar
    if (evt.detail.target.id === 'bot-status-container') {
        const isRunning = evt.detail.target.innerHTML.includes('BOT EJECUTÁNDOSE');
        const btnRun = document.getElementById('btn-run-bot');
        if (btnRun && !btnRun.disabled && isRunning) {
            btnRun.disabled = true;
            btnRun.innerHTML = '<i class="bi bi-lock-fill"></i> Bot en uso';
        } else if (btnRun && btnRun.disabled && !isRunning && !btnRun.innerHTML.includes('Iniciando')) {
            btnRun.disabled = false;
            btnRun.innerHTML = '<i class="bi bi-play-fill fs-5"></i> Ejecutar Bot';
            btnRun.classList.add('btn-primary');
            btnRun.classList.remove('btn-success');
        }
    }
});
