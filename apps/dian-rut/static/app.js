document.addEventListener('DOMContentLoaded', () => {
    const dropArea = document.getElementById('file-drop-area');
    const fileInput = document.getElementById('file-input');
    const startBtn = document.getElementById('start-btn');
    const uploadSection = document.getElementById('upload-section');
    const progressSection = document.getElementById('progress-section');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    const statusMessage = document.getElementById('status-message');
    const logTerminal = document.getElementById('log-terminal');
    const downloadBtn = document.getElementById('download-btn');
    const partialDownloadBtn = document.getElementById('partial-download-btn');
    const newTaskBtn = document.getElementById('new-task-btn');
    
    let selectedFile = null;
    let clientId = crypto.randomUUID();
    let ws = null;

    // Browser Mode Elements
    const checkConnectionBtn = document.getElementById('check-connection-btn');
    const modeStatusBadge = document.getElementById('mode-status-badge');
    const copyCommandBtn = document.getElementById('copy-command-btn');
    const commandText = document.getElementById('terminal-command');

    // Copy to Clipboard
    if (copyCommandBtn) {
        copyCommandBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(commandText.innerText).then(() => {
                const originalSvg = copyCommandBtn.innerHTML;
                copyCommandBtn.innerHTML = '<span style="font-size: 0.7rem; color: var(--success-color);">¡Copiado!</span>';
                setTimeout(() => {
                    copyCommandBtn.innerHTML = originalSvg;
                }, 2000);
            });
        });
    }

    // Check Browser Connection Status
    async function checkBrowserMode() {
        checkConnectionBtn.disabled = true;
        checkConnectionBtn.innerText = 'Verificando...';
        try {
            const res = await fetch('/browser-mode-status');
            const data = await res.json();
            
            if (data.status === 'human_connected') {
                modeStatusBadge.className = 'status-badge status-human';
                modeStatusBadge.innerText = '🟢 Conectado a Chrome real';
                checkConnectionBtn.innerText = 'Conectado Exitosamente';
                checkConnectionBtn.classList.replace('secondary-btn', 'success-btn');
            } else {
                modeStatusBadge.className = 'status-badge status-auto';
                modeStatusBadge.innerText = '🔴 Modo Automático (Fallback)';
                checkConnectionBtn.innerText = 'Reintentar Conexión';
                checkConnectionBtn.classList.replace('success-btn', 'secondary-btn');
                checkConnectionBtn.disabled = false;
            }
        } catch (err) {
            modeStatusBadge.className = 'status-badge status-auto';
            modeStatusBadge.innerText = '🔴 Modo Automático (Error)';
            checkConnectionBtn.innerText = 'Verificar Conexión';
            checkConnectionBtn.disabled = false;
        }
    }

    if (checkConnectionBtn) {
        checkConnectionBtn.addEventListener('click', checkBrowserMode);
        // Initial check on load
        checkBrowserMode();
    }

    // File Drop Handling
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => dropArea.classList.remove('dragover'), false);
    });

    dropArea.addEventListener('drop', handleDrop, false);
    dropArea.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

    function handleDrop(e) {
        let dt = e.dataTransfer;
        let files = dt.files;
        handleFiles(files);
    }

    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];
            if (file.name.endsWith('.xlsx')) {
                selectedFile = file;
                dropArea.querySelector('p').innerHTML = `Archivo cargado: <span>${file.name}</span>`;
                startBtn.disabled = false;
            } else {
                alert('Por favor, selecciona un archivo Excel (.xlsx)');
            }
        }
    }

    // Start Process
    startBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        // Switch UI
        uploadSection.classList.add('hidden');
        progressSection.classList.remove('hidden');
        
        setupWebSocket();

        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('client_id', clientId);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();
            
            if (!response.ok) {
                appendLog('error', data.error || 'Error al subir el archivo');
                statusMessage.innerText = 'Error';
            } else {
                // Configurar descarga parcial inmediata
                if (data.file_id) {
                    partialDownloadBtn.href = `/download/current/${data.file_id}`;
                    partialDownloadBtn.classList.remove('hidden');
                }
            }
        } catch (error) {
            appendLog('error', 'Error de red al intentar subir el archivo.');
            statusMessage.innerText = 'Error';
        }
    });

    function setupWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        ws = new WebSocket(`${protocol}//${window.location.host}/ws/${clientId}`);

        ws.onopen = () => {
            appendLog('info', 'Conexión establecida con el servidor.');
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            handleServerMessage(msg.type, msg.data);
        };

        ws.onerror = (error) => {
            console.error('WebSocket Error:', error);
        };
        
        ws.onclose = () => {
            appendLog('info', 'Conexión cerrada.');
        }
    }

    function handleServerMessage(type, data) {
        if (data.message) {
            appendLog(type, data.message);
            statusMessage.innerText = data.message;
        }

        if (type === 'progress' && data.percent !== undefined) {
            progressFill.style.width = `${data.percent}%`;
            progressText.innerText = `${data.percent}%`;
        }

        if (type === 'done') {
            progressFill.style.width = `100%`;
            progressText.innerText = `100%`;
            downloadBtn.href = data.download_url;
            downloadBtn.classList.remove('hidden');
            partialDownloadBtn.classList.add('hidden'); // Ocultar parcial al terminar
            newTaskBtn.classList.remove('hidden');
            if (ws) ws.close();
        }
    }

    function appendLog(type, message) {
        const time = new Date().toLocaleTimeString('es-CO', { hour12: false });
        const entry = document.createElement('div');
        entry.className = `log-entry log-${type}`;
        entry.innerHTML = `<span class="log-time">[${time}]</span> ${message}`;
        logTerminal.appendChild(entry);
        logTerminal.scrollTop = logTerminal.scrollHeight;
    }

    newTaskBtn.addEventListener('click', () => {
        window.location.reload();
    });
});
