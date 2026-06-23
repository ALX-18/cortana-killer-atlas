/* ============================================================
   Atlas — Assistant Bureau Windows — Frontend Logic
   ============================================================ */

const API_BASE = '/api';
let conversationHistory = [];
let isProcessing = false;
let _typingStartTime = null;       // Track when typing indicator appeared
let _typingInterval = null;        // Interval for progress messages

// ---- DOM refs ----
const messagesEl = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const btnSend = document.getElementById('btn-send');
const btnContext = document.getElementById('btn-context');
const btnDiagnostics = document.getElementById('btn-diagnostics');
const statusDot = document.getElementById('status-indicator');
const contextPanel = document.getElementById('context-panel');
const contextContent = document.getElementById('context-content');

// ============================================================
//  Startup
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    checkBridgeStatus();
    setInterval(checkHealth, 15000);   // health check toutes les 15s
    setInterval(checkBridgeStatus, 5000); // bridge check toutes les 5s
});

// ============================================================
//  Health check
// ============================================================

async function checkHealth() {
    try {
        const res = await fetch('/health');
        if (res.ok) {
            statusDot.className = 'status-dot online';
            statusDot.title = 'Connecté';
        } else {
            throw new Error();
        }
    } catch {
        statusDot.className = 'status-dot offline';
        statusDot.title = 'Hors ligne';
    }
}

// ============================================================
//  Bridge status check
// ============================================================

async function checkBridgeStatus() {
    const bridgeDot = document.getElementById('bridge-indicator');
    if (!bridgeDot) return;
    try {
        const res = await fetch(`${API_BASE}/bridge/status`);
        if (res.ok) {
            const data = await res.json();
            if (data.connected) {
                bridgeDot.className = 'status-dot online';
                bridgeDot.title = `Extension navigateur : connectée (${data.clients} client${data.clients > 1 ? 's' : ''})`;
            } else {
                bridgeDot.className = 'status-dot offline';
                bridgeDot.title = 'Extension navigateur : non connectée — installer l\'extension Atlas';
            }
        }
    } catch {
        bridgeDot.className = 'status-dot offline';
        bridgeDot.title = 'Bridge indisponible';
    }
}

// ============================================================
//  Send message
// ============================================================

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text || isProcessing) return;

    isProcessing = true;
    btnSend.disabled = true;
    userInput.value = '';
    autoResize();

    // Add user message
    appendMessage('user', text);
    conversationHistory.push({ role: 'user', content: text });

    // Show typing indicator
    const typingEl = showTyping();

    try {
        const response = await fetch(`${API_BASE}/chat/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                history: conversationHistory.slice(-20),  // last 20 messages
            }),
        });

        if (!response.ok) {
            throw new Error(`Erreur serveur : ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let assistantText = '';
        let toolResults = [];
        let msgEl = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const data = line.slice(6).trim();

                if (data === '[DONE]') continue;

                try {
                    const parsed = JSON.parse(data);

                    if (parsed.type === 'keepalive') {
                        // Keepalive from server — ignore silently
                        continue;
                    }

                    if (parsed.type === 'token') {
                        // Remove typing indicator on first token
                        if (!msgEl) {
                            removeTyping(typingEl);
                            msgEl = appendMessage('assistant', '', true);
                        }
                        assistantText += parsed.content;
                        updateMessageContent(msgEl, assistantText);
                    }

                    if (parsed.type === 'thinking') {
                        // Atlas détecte un tool-call JSON — afficher un indicateur
                        if (!msgEl) {
                            removeTyping(typingEl);
                            msgEl = appendMessage('assistant', '', true);
                        }
                        updateMessageContent(msgEl, parsed.content || '⏳ Exécution en cours...');
                    }

                    if (parsed.type === 'step') {
                        // Sequence step feedback — display step progress
                        if (!msgEl) {
                            removeTyping(typingEl);
                            msgEl = appendMessage('assistant', '', true);
                        }
                        appendStepResult(msgEl, parsed);
                    }

                    if (parsed.type === 'error') {
                        // Timeout or other server error — show message + retry button
                        removeTyping(typingEl);
                        const errorMsg = parsed.message || 'Erreur inconnue.';
                        msgEl = appendMessage('assistant', '', true);
                        const retryId = 'retry-' + Date.now();
                        msgEl.innerHTML = `
                            <div style="color: var(--danger, #e74c3c)">⚠️ ${formatMarkdown(errorMsg).replace(/<\/?p>/g, '')}</div>
                            <div id="${retryId}" style="margin-top: 8px">
                                <button class="btn-confirm" onclick="retryLastMessage('${retryId}')">🔄 Réessayer</button>
                            </div>
                        `;
                        isProcessing = false;
                        btnSend.disabled = false;
                        return; // Stop processing this stream
                    }

                    if (parsed.type === 'result') {
                        const result = parsed.content;
                        if (!msgEl) {
                            removeTyping(typingEl);
                            msgEl = appendMessage('assistant', '', true);
                        }

                        // Nettoyer le JSON brut affiché pendant le streaming
                        // et remplacer par le message propre du résultat
                        if (result.tool_results && result.tool_results.length > 0) {
                            // Remplacer le contenu de la bulle par le message nettoyé
                            const cleanMsg = result.message || '';
                            if (cleanMsg) {
                                updateMessageContent(msgEl, cleanMsg);
                                assistantText = cleanMsg;
                            } else {
                                // Pas de message texte — vider les tokens JSON bruts
                                msgEl.innerHTML = '';
                                assistantText = '';
                            }
                            toolResults = result.tool_results;
                            appendToolResults(msgEl, toolResults);
                        } else if (result.message) {
                            updateMessageContent(msgEl, result.message);
                            assistantText = result.message;
                        }
                    }
                } catch (e) {
                    // Skip malformed chunks
                }
            }
        }

        // Save assistant response
        if (assistantText) {
            conversationHistory.push({ role: 'assistant', content: assistantText });
        }

    } catch (err) {
        removeTyping(typingEl);
        appendMessage('assistant', `❌ Erreur : ${err.message}. Vérifie qu'Ollama est lancé et que le serveur fonctionne.`);
    }

    isProcessing = false;
    btnSend.disabled = false;
    userInput.focus();
}

// ============================================================
//  Confirmation handling
// ============================================================

async function handleConfirmation(confirmationId, accepted) {
    const btnContainer = document.getElementById(`confirm-${confirmationId}`);
    if (btnContainer) {
        btnContainer.innerHTML = accepted
            ? '<span style="color: var(--success)">✅ Confirmé — exécution en cours...</span>'
            : '<span style="color: var(--text-muted)">❌ Action annulée.</span>';
    }

    try {
        const res = await fetch(`${API_BASE}/confirm`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmation_id: confirmationId, accepted }),
        });

        const result = await res.json();

        if (btnContainer) {
            if (result.status === 'success') {
                const r = result.result || {};
                btnContainer.innerHTML = `<span style="color: var(--success)">✅ ${r.message || 'Action exécutée.'}</span>`;
            } else if (result.status === 'cancelled') {
                btnContainer.innerHTML = `<span style="color: var(--text-muted)">↩️ ${result.message}</span>`;
            } else {
                btnContainer.innerHTML = `<span style="color: var(--danger)">❌ ${result.message || 'Erreur.'}</span>`;
            }
        }
    } catch (err) {
        if (btnContainer) {
            btnContainer.innerHTML = `<span style="color: var(--danger)">❌ Erreur réseau : ${err.message}</span>`;
        }
    }
}

// ============================================================
//  DOM helpers
// ============================================================

function appendMessage(role, content, returnEl = false) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'assistant' ? '⚡' : '👤';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = formatMarkdown(content);

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    messagesEl.appendChild(msgDiv);
    scrollToBottom();

    if (returnEl) return contentDiv;
}

function updateMessageContent(el, text) {
    if (el) {
        el.innerHTML = formatMarkdown(text);
        scrollToBottom();
    }
}

function appendToolResults(parentEl, results) {
    for (const tr of results) {
        const div = document.createElement('div');

        if (tr.status === 'confirmation_required') {
            div.className = 'tool-result confirmation';
            div.innerHTML = `
                <div class="tool-result-header confirmation">⚠️ Confirmation requise — ${tr.tool}</div>
                <div>${tr.reason || ''}</div>
                ${tr.suggestion ? `<div class="muted" style="margin-top:4px">${tr.suggestion}</div>` : ''}
                <div class="confirmation-buttons" id="confirm-${tr.confirmation_id}">
                    <button class="btn-confirm" onclick="handleConfirmation('${tr.confirmation_id}', true)">✅ Oui</button>
                    <button class="btn-reject" onclick="handleConfirmation('${tr.confirmation_id}', false)">❌ Non</button>
                </div>
            `;
        } else if (tr.status === 'success') {
            div.className = 'tool-result success';
            const result = tr.result || {};
            div.innerHTML = `
                <div class="tool-result-header success">✅ ${tr.tool}</div>
                <div>${result.message || JSON.stringify(result, null, 2)}</div>
            `;
        } else {
            div.className = 'tool-result error';
            div.innerHTML = `
                <div class="tool-result-header error">❌ ${tr.tool}</div>
                <div>${tr.message || 'Erreur inconnue'}</div>
            `;
        }

        parentEl.appendChild(div);
    }
    scrollToBottom();
}

function appendStepResult(parentEl, stepData) {
    // stepData: {type: "step", step: 1, total: 2, status: "done"|"running"|"error"|"confirmation", message: "..."}
    const div = document.createElement('div');
    div.className = 'tool-result step';
    div.style.marginBottom = '4px';

    let icon = '⏳';
    let color = 'var(--text-muted, #888)';
    if (stepData.status === 'done') {
        icon = '✅';
        color = 'var(--success, #27ae60)';
    } else if (stepData.status === 'error') {
        icon = '❌';
        color = 'var(--danger, #e74c3c)';
    } else if (stepData.status === 'confirmation') {
        icon = '⚠️';
        color = 'var(--warning, #f39c12)';
    } else if (stepData.status === 'running') {
        icon = '⏳';
        color = 'var(--accent, #3498db)';
    }

    div.innerHTML = `
        <div style="color: ${color}; font-size: 0.9em;">
            ${icon} <strong>Étape ${stepData.step}/${stepData.total}</strong> — ${stepData.message || ''}
        </div>
    `;
    parentEl.appendChild(div);
    scrollToBottom();
}

function showTyping() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML = `
        <div class="message-avatar">⚡</div>
        <div class="message-content">
            <div class="typing-indicator">
                <span></span><span></span><span></span>
            </div>
            <div class="typing-status" style="font-size:0.85em; color:var(--text-muted,#888); margin-top:4px;"></div>
        </div>
    `;
    messagesEl.appendChild(div);
    scrollToBottom();

    // Start progressive status messages
    _typingStartTime = Date.now();
    const statusEl = div.querySelector('.typing-status');
    _typingInterval = setInterval(() => {
        const elapsed = (Date.now() - _typingStartTime) / 1000;
        if (elapsed > 15) {
            statusEl.textContent = 'Opération en cours, ça peut prendre un moment…';
        } else if (elapsed > 5) {
            statusEl.textContent = 'Atlas réfléchit…';
        }
    }, 1000);

    return div;
}

function removeTyping(el) {
    if (_typingInterval) {
        clearInterval(_typingInterval);
        _typingInterval = null;
    }
    _typingStartTime = null;
    if (el && el.parentNode) {
        el.parentNode.removeChild(el);
    }
}

function scrollToBottom() {
    const chat = document.getElementById('chat-container');
    chat.scrollTop = chat.scrollHeight;
}

// ============================================================
//  Markdown-ish formatting
// ============================================================

function formatMarkdown(text) {
    if (!text) return '';

    let html = text
        // Escape HTML
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        // Code blocks
        .replace(/```(\w*)\n?([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
        // Inline code
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        // Bold
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // Italic
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        // Lists
        .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
        // Paragraphs
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    // Wrap loose <li> in <ul>
    html = html.replace(/(<li>.*?<\/li>)/gs, '<ul>$1</ul>');
    // Clean double <ul>
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    return `<p>${html}</p>`;
}

// ============================================================
//  Context & Diagnostics panels
// ============================================================

async function togglePanel(panelId) {
    const panel = document.getElementById(panelId);
    panel.classList.toggle('hidden');

    if (!panel.classList.contains('hidden') && panelId === 'context-panel') {
        await loadContext();
    }
}

async function loadContext() {
    try {
        const res = await fetch(`${API_BASE}/context`);
        const ctx = await res.json();
        contextContent.textContent = JSON.stringify(ctx, null, 2);
    } catch {
        contextContent.textContent = 'Erreur de chargement du contexte.';
    }
}

async function loadDiagnostics() {
    try {
        const res = await fetch(`${API_BASE}/diagnostics`);
        const diag = await res.json();

        // Format nice output
        let html = '';
        if (diag.cpu) {
            html += `<strong>CPU:</strong> ${diag.cpu.usage_percent}% — ${diag.cpu.logical_cores} cœurs\n`;
        }
        if (diag.ram) {
            html += `<strong>RAM:</strong> ${diag.ram.percent}% — ${diag.ram.available_gb} Go libres / ${diag.ram.total_gb} Go\n`;
        }
        if (diag.gpu && diag.gpu.available) {
            html += `<strong>GPU:</strong> ${diag.gpu.name} — ${diag.gpu.usage_percent}% — ${diag.gpu.temperature_c}°C\n`;
        }
        if (diag.disks) {
            html += `<strong>Disques:</strong>\n`;
            for (const d of diag.disks) {
                html += `  ${d.mountpoint} → ${d.percent}% (${d.free_gb} Go libres)\n`;
            }
        }

        appendMessage('assistant', `📊 **Diagnostics système**\n\`\`\`\n${html}\`\`\``);
    } catch {
        appendMessage('assistant', '❌ Erreur lors du chargement des diagnostics.');
    }
}

// ============================================================
//  Auto-resize textarea
// ============================================================

function autoResize() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 120) + 'px';
}

// ============================================================
//  Event listeners
// ============================================================

btnSend.addEventListener('click', sendMessage);

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

userInput.addEventListener('input', autoResize);

btnContext.addEventListener('click', () => togglePanel('context-panel'));

btnDiagnostics.addEventListener('click', loadDiagnostics);

// ============================================================
//  Retry last message
// ============================================================

function retryLastMessage(retryBtnId) {
    // Disable the retry button
    const container = document.getElementById(retryBtnId);
    if (container) container.innerHTML = '<span style="color: var(--text-muted)">🔄 Nouvelle tentative…</span>';

    // Find the last user message in history
    const lastUserMsg = conversationHistory.filter(m => m.role === 'user').pop();
    if (lastUserMsg) {
        // Remove the last assistant error from history if present
        if (conversationHistory.length > 0 && conversationHistory[conversationHistory.length - 1].role === 'assistant') {
            conversationHistory.pop();
        }
        userInput.value = lastUserMsg.content;
        sendMessage();
    }
}
