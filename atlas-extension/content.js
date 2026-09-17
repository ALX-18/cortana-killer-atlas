/**
 * Atlas Browser Bridge — Content Script
 *
 * Injecté dans chaque page web. Reçoit les commandes du background script
 * et effectue les interactions DOM (click, type, scroll, get_content).
 */

// Éviter la double injection
if (typeof window.__atlas_content_loaded === "undefined") {
  window.__atlas_content_loaded = true;

  // -------------------------------------------------------------------------- //
  //  Message handler
  // -------------------------------------------------------------------------- //

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    const { action, params } = message;

    switch (action) {
      case "click":
        sendResponse(handleClick(params));
        break;
      case "type":
        sendResponse(handleType(params));
        break;
      case "scroll":
        sendResponse(handleScroll(params));
        break;
      case "get_content":
        sendResponse(handleGetContent(params));
        break;
      default:
        sendResponse({ success: false, error: `Action inconnue: ${action}` });
    }

    return true; // Keep channel open for async
  });

  // -------------------------------------------------------------------------- //
  //  Click
  // -------------------------------------------------------------------------- //

  function handleClick(params) {
    const { selector } = params;
    if (!selector) return { success: false, error: "Sélecteur CSS manquant" };

    try {
      const el = document.querySelector(selector);
      if (!el) return { success: false, error: `Élément non trouvé: ${selector}` };

      // Scroll into view si nécessaire
      el.scrollIntoView({ behavior: "smooth", block: "center" });

      // Simuler un vrai clic
      el.focus();
      el.click();

      return {
        success: true,
        message: `Clic sur '${selector}'`,
        tag: el.tagName.toLowerCase(),
        text: (el.textContent || "").substring(0, 100),
      };
    } catch (err) {
      return { success: false, error: `Erreur clic: ${err.message}` };
    }
  }

  // -------------------------------------------------------------------------- //
  //  Type
  // -------------------------------------------------------------------------- //

  function handleType(params) {
    const { selector, text } = params;
    if (!selector) return { success: false, error: "Sélecteur CSS manquant" };
    if (text === undefined) return { success: false, error: "Texte manquant" };

    try {
      const el = document.querySelector(selector);
      if (!el) return { success: false, error: `Élément non trouvé: ${selector}` };

      // Focus l'élément
      el.focus();
      el.scrollIntoView({ behavior: "smooth", block: "center" });

      // Simuler la saisie caractère par caractère pour déclencher les événements
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable) {
        // Vider le champ d'abord
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
          el.value = "";
        } else {
          el.textContent = "";
        }

        // Insérer le texte
        if (el.tagName === "INPUT" || el.tagName === "TEXTAREA") {
          el.value = text;
        } else {
          el.textContent = text;
        }

        // Déclencher les événements pour les frameworks réactifs (React, Vue, etc.)
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true }));
        el.dispatchEvent(new KeyboardEvent("keyup", { bubbles: true }));

        return {
          success: true,
          message: `Texte saisi dans '${selector}' (${text.length} caractères)`,
        };
      }

      return { success: false, error: `L'élément '${selector}' n'est pas un champ de saisie` };
    } catch (err) {
      return { success: false, error: `Erreur saisie: ${err.message}` };
    }
  }

  // -------------------------------------------------------------------------- //
  //  Scroll
  // -------------------------------------------------------------------------- //

  function handleScroll(params) {
    const { direction = "down", amount = 500 } = params;

    try {
      const scrollAmount = direction === "up" ? -amount : amount;
      window.scrollBy({
        top: scrollAmount,
        behavior: "smooth",
      });

      return {
        success: true,
        message: `Scroll ${direction} de ${amount}px`,
        scrollY: window.scrollY,
      };
    } catch (err) {
      return { success: false, error: `Erreur scroll: ${err.message}` };
    }
  }

  // -------------------------------------------------------------------------- //
  //  Get Content
  // -------------------------------------------------------------------------- //

  function handleGetContent(params) {
    const { selector = "body" } = params;

    try {
      const el = document.querySelector(selector);
      if (!el) return { success: false, error: `Élément non trouvé: ${selector}` };

      // Extraire le texte proprement
      const text = el.innerText || el.textContent || "";
      const truncated = text.substring(0, 5000);

      return {
        success: true,
        content: truncated,
        length: text.length,
        truncated: text.length > 5000,
        url: window.location.href,
        title: document.title,
      };
    } catch (err) {
      return { success: false, error: `Erreur extraction: ${err.message}` };
    }
  }

  console.log("[Atlas Bridge] Content script chargé sur", window.location.href);
}
