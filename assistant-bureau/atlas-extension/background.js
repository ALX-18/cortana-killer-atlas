/**
 * Atlas Browser Bridge — Background Service Worker (Manifest V3)
 *
 * Gère la connexion WebSocket avec le serveur Atlas (port 9999)
 * et dispatche les commandes vers le content script de l'onglet actif.
 */

const ATLAS_WS_URL = "ws://127.0.0.1:9999";
const RECONNECT_DELAY_MS = 3000;
const PING_INTERVAL_MS = 15000;

let ws = null;
let isConnected = false;
let reconnectTimer = null;
let pingTimer = null;

// --------------------------------------------------------------------------- //
//  WebSocket Connection
// --------------------------------------------------------------------------- //

function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(ATLAS_WS_URL);

    ws.onopen = () => {
      isConnected = true;
      console.log("[Atlas Bridge] Connecté à", ATLAS_WS_URL);
      updateBadge("ON", "#4CAF50");

      // Heartbeat
      if (pingTimer) clearInterval(pingTimer);
      pingTimer = setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ping" }));
        }
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "command") {
          await handleCommand(data);
        } else if (data.type === "pong") {
          // Heartbeat response — nothing to do
        }
      } catch (err) {
        console.error("[Atlas Bridge] Erreur parsing message:", err);
      }
    };

    ws.onclose = () => {
      isConnected = false;
      console.log("[Atlas Bridge] Déconnecté");
      updateBadge("OFF", "#F44336");
      if (pingTimer) clearInterval(pingTimer);
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error("[Atlas Bridge] Erreur WebSocket:", err);
      isConnected = false;
      updateBadge("ERR", "#FF9800");
    };
  } catch (err) {
    console.error("[Atlas Bridge] Impossible de se connecter:", err);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    console.log("[Atlas Bridge] Tentative de reconnexion...");
    connect();
  }, RECONNECT_DELAY_MS);
}

function updateBadge(text, color) {
  try {
    chrome.action.setBadgeText({ text });
    chrome.action.setBadgeBackgroundColor({ color });
  } catch (e) {
    // Ignorer si l'API n'est pas disponible
  }
}

// --------------------------------------------------------------------------- //
//  Command dispatcher
// --------------------------------------------------------------------------- //

async function handleCommand(data) {
  const { request_id, command, params } = data;
  let result = {};

  try {
    switch (command) {
      case "navigate":
        result = await cmdNavigate(params);
        break;
      case "new_tab":
        result = await cmdNewTab(params);
        break;
      case "click":
      case "type":
      case "scroll":
      case "get_content":
        result = await cmdContentScript(command, params);
        break;
      case "get_url":
        result = await cmdGetUrl();
        break;
      default:
        result = { success: false, error: `Commande inconnue: ${command}` };
    }
  } catch (err) {
    result = { success: false, error: err.message };
  }

  // Envoyer la réponse à Atlas
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "response",
      request_id,
      result,
    }));
  }
}

// --------------------------------------------------------------------------- //
//  Command implementations
// --------------------------------------------------------------------------- //

async function cmdNavigate(params) {
  const { url } = params;
  if (!url) return { success: false, error: "URL manquante" };

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    await chrome.tabs.update(tab.id, { url });
    return { success: true, message: `Navigation vers ${url}` };
  }
  return { success: false, error: "Aucun onglet actif" };
}

async function cmdNewTab(params) {
  const { url } = params;
  const tab = await chrome.tabs.create({ url: url || "about:blank" });
  return { success: true, message: `Nouvel onglet ouvert`, tabId: tab.id };
}

async function cmdGetUrl() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab) {
    return { success: true, url: tab.url, title: tab.title };
  }
  return { success: false, error: "Aucun onglet actif" };
}

async function cmdContentScript(command, params) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return { success: false, error: "Aucun onglet actif" };

  // Vérifier que le content script peut être injecté
  if (tab.url.startsWith("chrome://") || tab.url.startsWith("chrome-extension://") ||
      tab.url.startsWith("edge://") || tab.url.startsWith("about:")) {
    return { success: false, error: "Impossible d'interagir avec les pages système du navigateur" };
  }

  try {
    const results = await chrome.tabs.sendMessage(tab.id, {
      action: command,
      params,
    });
    return results || { success: false, error: "Pas de réponse du content script" };
  } catch (err) {
    // Content script pas encore injecté — tenter l'injection
    try {
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ["content.js"],
      });
      // Réessayer après injection
      const results = await chrome.tabs.sendMessage(tab.id, {
        action: command,
        params,
      });
      return results || { success: false, error: "Pas de réponse après injection" };
    } catch (injectErr) {
      return { success: false, error: `Content script non disponible: ${injectErr.message}` };
    }
  }
}

// --------------------------------------------------------------------------- //
//  Communication avec popup
// --------------------------------------------------------------------------- //

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "get_status") {
    sendResponse({
      connected: isConnected,
      wsUrl: ATLAS_WS_URL,
    });
    return true;
  }
  if (message.type === "reconnect") {
    connect();
    sendResponse({ ok: true });
    return true;
  }
});

// --------------------------------------------------------------------------- //
//  Init
// --------------------------------------------------------------------------- //

connect();
