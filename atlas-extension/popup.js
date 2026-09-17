/**
 * Atlas Browser Bridge — Popup Script
 *
 * Affiche le statut de connexion WebSocket et permet la reconnexion.
 */

const statusDot = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const wsUrlEl = document.getElementById("ws-url");
const btnReconnect = document.getElementById("btn-reconnect");

function updateUI(status) {
  if (status.connected) {
    statusDot.className = "dot green";
    statusLabel.textContent = "Connecté";
  } else {
    statusDot.className = "dot red";
    statusLabel.textContent = "Déconnecté";
  }
  if (status.wsUrl) {
    wsUrlEl.textContent = status.wsUrl;
  }
}

// Charger le statut au démarrage
chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
  if (response) updateUI(response);
});

// Bouton reconnexion
btnReconnect.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "reconnect" }, () => {
    statusLabel.textContent = "Connexion...";
    // Rafraîchir le statut après un court délai
    setTimeout(() => {
      chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
        if (response) updateUI(response);
      });
    }, 1500);
  });
});

// Rafraîchir toutes les 2 secondes quand la popup est ouverte
setInterval(() => {
  chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
    if (response) updateUI(response);
  });
}, 2000);
