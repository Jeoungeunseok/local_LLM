const chatBox = document.getElementById('chat-box');
const chatForm = document.getElementById('chat-form');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const uploadStatus = document.getElementById('upload-status');
const modeToggle = document.getElementById('rag-mode-toggle');
const modeLabel = document.getElementById('mode-label');
const modeDesc = document.getElementById('mode-desc');
const chatTitle = document.getElementById('chat-title');
const docList = document.getElementById('doc-list');

let chatHistory = [];
let isRagMode = false;

// Auto-resize textarea
messageInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = (this.scrollHeight) + 'px';
    sendBtn.disabled = this.value.trim() === '';
});

messageInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) chatForm.dispatchEvent(new Event('submit'));
    }
});

// Mode Toggle
modeToggle.addEventListener('change', (e) => {
    isRagMode = e.target.checked;
    if (isRagMode) {
        modeLabel.textContent = 'RAG (문서 기반)';
        modeLabel.style.color = '#10b981';
        modeDesc.textContent = '업로드된 문서 내에서 답변을 찾습니다.';
        chatTitle.textContent = 'RAG 문서 기반 대화 모드';
    } else {
        modeLabel.textContent = '일반 대화';
        modeLabel.style.color = 'inherit';
        modeDesc.textContent = 'LLM 모델의 기본 지식으로 답변합니다.';
        chatTitle.textContent = '일반 대화 모드';
    }
});

// Add message to UI
function appendMessage(role, content, sources = null) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    let html = `
        <div class="avatar">${role === 'user' ? 'ME' : 'AI'}</div>
        <div class="bubble">
            <div class="text">${formatText(content)}</div>
    `;

    if (sources && sources.length > 0) {
        html += `
            <div class="sources-box">
                <div class="sources-title">참조된 문서 출처</div>
                ${sources.map(s => `
                    <div class="source-item">
                        <strong>${s.filename}</strong> (유사도: ${(s.score).toFixed(2)})<br>
                        ${s.text.substring(0, 100)}...
                    </div>
                `).join('')}
            </div>
        `;
    }

    html += `</div>`;
    msgDiv.innerHTML = html;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function appendLoading() {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message assistant loading`;
    msgDiv.innerHTML = `
        <div class="avatar">AI</div>
        <div class="bubble">
            <div class="loading-dots"><span></span><span></span><span></span></div>
        </div>
    `;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    return msgDiv;
}

function formatText(text) {
    // Simple line break formatting
    return text.replace(/\n/g, '<br>');
}

// Chat Submit
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = messageInput.value.trim();
    if (!message) return;

    // Reset input
    messageInput.value = '';
    messageInput.style.height = 'auto';
    sendBtn.disabled = true;

    appendMessage('user', message);
    const loadingDiv = appendLoading();

    try {
        let response;
        if (isRagMode) {
            response = await fetch('/rag/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: message })
            });
        } else {
            response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message, history: chatHistory })
            });
        }

        const data = await response.json();
        loadingDiv.remove();

        if (response.ok) {
            appendMessage('assistant', data.answer, data.sources);
            if (!isRagMode) {
                chatHistory.push({ role: 'user', content: message });
                chatHistory.push({ role: 'assistant', content: data.answer });
            }
        } else {
            appendMessage('assistant', `오류 발생: ${data.detail || '알 수 없는 오류'}`);
        }

    } catch (err) {
        loadingDiv.remove();
        appendMessage('assistant', `서버 통신 오류: ${err.message}`);
    }
});

// File Upload
dropZone.addEventListener('click', () => fileInput.click());

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
});

['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
});

dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFiles(files);
});

fileInput.addEventListener('change', function () {
    handleFiles(this.files);
});

async function handleFiles(files) {
    if (files.length === 0) return;
    const file = files[0];

    uploadStatus.style.display = 'block';
    uploadStatus.className = 'status-msg';
    uploadStatus.textContent = `${file.name} 업로드 및 벡터화 진행 중...`;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/documents/upload', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (response.ok) {
            uploadStatus.textContent = `✅ ${file.name} 업로드 완료! (${data.chunks_count}개 청크 저장됨)`;
            await loadDocumentList();
        } else {
            uploadStatus.className = 'status-msg error';
            uploadStatus.textContent = `❌ 업로드 실패: ${data.detail}`;
        }
    } catch (err) {
        uploadStatus.className = 'status-msg error';
        uploadStatus.textContent = `❌ 네트워크 오류: ${err.message}`;
    }
}

// Load and render document list
async function loadDocumentList() {
    try {
        const response = await fetch('/documents');
        const data = await response.json();
        const docs = data.documents;

        if (!docs || docs.length === 0) {
            docList.innerHTML = '<p class="no-docs">문서가 없습니다.</p>';
            return;
        }

        docList.innerHTML = docs.map(doc => `
            <div class="doc-item" id="doc-item-${doc.id}">
                <div class="doc-item-info">
                    <div class="doc-item-name" title="${doc.filename}">${doc.filename}</div>
                    <div class="doc-item-meta">${doc.chunk_count}개 청크</div>
                </div>
                <button class="delete-btn" onclick="deleteDocument('${doc.filename}', ${doc.id})" title="문서 삭제">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="3 6 5 6 21 6"></polyline>
                        <path d="M19 6l-1 14H6L5 6"></path>
                        <path d="M10 11v6"></path><path d="M14 11v6"></path>
                        <path d="M9 6V4h6v2"></path>
                    </svg>
                </button>
            </div>
        `).join('');
    } catch (err) {
        docList.innerHTML = '<p class="no-docs">목록 로드 실패</p>';
    }
}

// Delete document
async function deleteDocument(filename, id) {
    if (!confirm(`'${filename}' 문서를 삭제하시겠습니까?\n\n벡터 DB에서 해당 문서의 모든 데이터가 영구 삭제됩니다.`)) return;

    const btn = document.querySelector(`#doc-item-${id} .delete-btn`);
    if (btn) btn.disabled = true;

    try {
        const response = await fetch(`/documents/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (response.ok) {
            await loadDocumentList();
        } else {
            alert(`삭제 실패: ${data.detail}`);
            if (btn) btn.disabled = false;
        }
    } catch (err) {
        alert(`네트워크 오류: ${err.message}`);
        if (btn) btn.disabled = false;
    }
}

// Initial load
loadDocumentList();
