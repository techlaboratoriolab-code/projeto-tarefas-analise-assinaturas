// Elementos do DOM
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const processBtn = document.getElementById('processBtn');
const statusSection = document.getElementById('statusSection');
const statusText = document.getElementById('statusText');
const resultsSection = document.getElementById('resultsSection');
const resultsContent = document.getElementById('resultsContent');

// Estado da aplicação
let selectedFiles = [];

// Event Listeners
uploadArea.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', handleFileSelect);
processBtn.addEventListener('click', processFiles);

// Drag and Drop
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('drag-over');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
});

// Funções
function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    addFiles(files);
}

function addFiles(files) {
    // Validar se são arquivos XML
    const xmlFiles = files.filter(file => {
        const isXML = file.name.toLowerCase().endsWith('.xml') || 
                     file.type === 'text/xml' || 
                     file.type === 'application/xml';
        
        if (!isXML) {
            alert(`O arquivo "${file.name}" não é um arquivo XML válido.`);
        }
        
        return isXML;
    });
    
    if (xmlFiles.length === 0) return;
    
    selectedFiles = [...selectedFiles, ...xmlFiles];
    renderFileList();
    processBtn.disabled = selectedFiles.length === 0;
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
    processBtn.disabled = selectedFiles.length === 0;
}

function renderFileList() {
    if (selectedFiles.length === 0) {
        fileList.classList.remove('active');
        fileList.innerHTML = '';
        return;
    }

    fileList.classList.add('active');
    fileList.innerHTML = selectedFiles.map((file, index) => `
        <div class="file-item">
            <div class="file-info">
                <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
                    <polyline points="13 2 13 9 20 9"></polyline>
                    <text x="8" y="18" font-size="6" fill="currentColor" font-weight="bold">XML</text>
                </svg>
                <div class="file-details">
                    <h4>${file.name}</h4>
                    <p>${formatFileSize(file.size)}</p>
                </div>
            </div>
            <button class="remove-btn" onclick="removeFile(${index})">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <line x1="18" y1="6" x2="6" y2="18"></line>
                    <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
            </button>
        </div>
    `).join('');
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

async function processFiles() {
    if (selectedFiles.length === 0) return;

    // Mostrar status de processamento
    statusSection.style.display = 'block';
    resultsSection.style.display = 'none';
    processBtn.disabled = true;
    statusText.textContent = 'Enviando arquivos...';

    try {
        // Criar FormData com os arquivos
        const formData = new FormData();
        selectedFiles.forEach((file, index) => {
            formData.append('files', file);
        });

        statusText.textContent = 'Processando...';

        // Fazer requisição para o backend
        const response = await fetch('/api/process', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Erro na requisição: ${response.status}`);
        }

        const result = await response.json();

        // Mostrar resultados
        displayResults(result);
        
    } catch (error) {
        console.error('Erro ao processar arquivos:', error);
        displayError(error.message);
    } finally {
        statusSection.style.display = 'none';
        processBtn.disabled = false;
    }
}

function displayResults(result) {
    resultsSection.style.display = 'block';
    resultsSection.style.borderLeftColor = 'var(--success-green)';
    resultsSection.style.background = '#f0fff4';
    
    resultsContent.innerHTML = '';
    
    if (typeof result === 'object') {
        resultsContent.innerHTML = `<pre>${JSON.stringify(result, null, 2)}</pre>`;
    } else {
        resultsContent.textContent = result;
    }

    // Scroll suave até os resultados
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function displayError(errorMessage) {
    resultsSection.style.display = 'block';
    resultsSection.style.borderLeftColor = 'var(--error-red)';
    resultsSection.style.background = '#fff5f5';
    
    const resultsTitle = resultsSection.querySelector('h3');
    resultsTitle.textContent = 'Erro no Processamento';
    resultsTitle.style.color = 'var(--error-red)';
    
    resultsContent.textContent = errorMessage;
    
    // Scroll suave até o erro
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Expor função removeFile globalmente
window.removeFile = removeFile;

// Log de inicialização
console.log('Sistema LAB inicializado ✓');