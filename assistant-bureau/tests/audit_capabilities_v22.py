"""
=============================================================================
AUDIT COMPLET DES CAPACITÉS ATLAS v2.2
=============================================================================
Script de test exhaustif couvrant :
  1. Réponses textuelles (conversation)
  2. Lancement d'apps
  3. Interaction fenêtres (type, hotkey, click)
  4. Recherche web
  5. Navigation navigateur (bridge)
  6. Compréhension de commandes complexes / multi-step
  7. Affichage du JSON brut dans les réponses (bug UI)
  8. SearXNG fallback & limites
=============================================================================
"""
import requests
import json
import time

API = "http://localhost:8550/api/chat"
STREAM_API = "http://localhost:8550/api/chat/stream"
TIMEOUT = 90

results = []

def test_chat(prompt, test_name, expected_type=None, expected_tool=None, check_message=True):
    """Envoie un prompt à Atlas et analyse la réponse."""
    print(f"\n{'='*70}")
    print(f"TEST: {test_name}")
    print(f"PROMPT: \"{prompt}\"")
    print(f"{'='*70}")
    
    try:
        r = requests.post(API, json={"message": prompt, "history": []}, timeout=TIMEOUT)
        data = r.json()
    except Exception as e:
        result = {
            "test": test_name,
            "prompt": prompt,
            "status": "ERROR",
            "detail": str(e)
        }
        results.append(result)
        print(f"  ERREUR: {e}")
        return None
    
    resp_type = data.get("type", "")
    message = data.get("message", "")
    tool_results = data.get("tool_results", [])
    
    print(f"  Type: {resp_type}")
    print(f"  Message: {message[:200] if message else '(vide)'!r}")
    if tool_results:
        for tr in tool_results:
            tool = tr.get("tool", "?")
            status = tr.get("status", "?")
            res = tr.get("result", {})
            res_msg = res.get("message", "") if isinstance(res, dict) else str(res)[:100]
            print(f"  Tool: {tool} -> {status} : {res_msg[:120]}")
    
    # Analyse
    issues = []
    
    # Check: JSON brut visible dans le message ?
    if message and '{"action"' in message:
        issues.append("JSON brut visible dans le message")
    if message and message.startswith("}"):
        issues.append("Message commence par } (résidu JSON)")
    
    # Check: type attendu
    if expected_type and resp_type != expected_type:
        issues.append(f"Type attendu={expected_type}, obtenu={resp_type}")
    
    # Check: outil attendu
    if expected_tool and tool_results:
        actual_tools = [tr.get("tool") for tr in tool_results]
        if expected_tool not in actual_tools:
            issues.append(f"Outil attendu={expected_tool}, obtenu={actual_tools}")
    
    # Check: message vide pour un tool_execution
    if resp_type in ("tool_execution", "sequence") and not message:
        issues.append("Message vide pour une exécution d'outil")
    
    # Check: tool failed
    if tool_results:
        for tr in tool_results:
            if tr.get("status") == "error":
                issues.append(f"Tool {tr.get('tool')} en erreur: {tr.get('message', '')[:80]}")
    
    status = "PASS" if not issues else "FAIL"
    result = {
        "test": test_name,
        "prompt": prompt,
        "status": status,
        "type": resp_type,
        "message": message[:200] if message else None,
        "tools": [tr.get("tool") for tr in tool_results] if tool_results else [],
        "tool_status": [tr.get("status") for tr in tool_results] if tool_results else [],
        "issues": issues
    }
    results.append(result)
    
    if issues:
        print(f"  ⚠️  PROBLÈMES: {issues}")
    else:
        print(f"  ✅ OK")
    
    return data


def test_stream(prompt, test_name):
    """Teste le streaming SSE et vérifie si du JSON brut est visible dans les tokens."""
    print(f"\n{'='*70}")
    print(f"TEST STREAM: {test_name}")
    print(f"PROMPT: \"{prompt}\"")
    print(f"{'='*70}")
    
    try:
        r = requests.post(STREAM_API, json={"message": prompt, "history": []}, 
                          timeout=TIMEOUT, stream=True)
    except Exception as e:
        result = {
            "test": test_name + " (stream)",
            "prompt": prompt,
            "status": "ERROR",
            "detail": str(e)
        }
        results.append(result)
        print(f"  ERREUR: {e}")
        return None
    
    tokens_text = ""
    result_data = None
    json_visible_in_tokens = False
    
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if data == "[DONE]":
            break
        try:
            parsed = json.loads(data)
            if parsed.get("type") == "token":
                tokens_text += parsed.get("content", "")
            elif parsed.get("type") == "result":
                result_data = parsed.get("content", {})
        except:
            pass
    
    # Vérifier si les tokens contiennent du JSON brut
    if '{"action"' in tokens_text or '{"sequence"' in tokens_text:
        json_visible_in_tokens = True
    
    issues = []
    if json_visible_in_tokens:
        issues.append("JSON brut streamé dans les tokens (visible dans la bulle)")
    
    message = result_data.get("message", "") if result_data else ""
    if message and '{"action"' in message:
        issues.append("JSON brut dans le message final du result")
    if message and message.startswith("}"):
        issues.append("Message final commence par }")
    
    status = "PASS" if not issues else "FAIL"
    result = {
        "test": test_name + " (stream)",
        "prompt": prompt,
        "status": status,
        "tokens_preview": tokens_text[:150],
        "json_in_tokens": json_visible_in_tokens,
        "final_message": message[:150] if message else None,
        "issues": issues
    }
    results.append(result)
    
    print(f"  Tokens aperçu: {tokens_text[:150]!r}")
    print(f"  JSON dans tokens: {'OUI ⚠️' if json_visible_in_tokens else 'NON ✅'}")
    print(f"  Message final: {message[:150]!r}")
    if issues:
        print(f"  ⚠️  PROBLÈMES: {issues}")
    else:
        print(f"  ✅ OK")
    
    return result_data


# ========================================================================
# CATÉGORIE 1 : RÉPONSES TEXTUELLES
# ========================================================================
print("\n" + "★"*70)
print(" CATÉGORIE 1 : RÉPONSES TEXTUELLES (conversations)")
print("★"*70)

test_chat("Salut, comment tu vas ?", "Salut basique", expected_type="text")
test_chat("C'est quoi Python ?", "Question savoir", expected_type="text")
test_chat("Quelle heure est-il ?", "Question heure", expected_type="text")

# ========================================================================
# CATÉGORIE 2 : LANCEMENT D'APPLICATIONS
# ========================================================================
print("\n" + "★"*70)
print(" CATÉGORIE 2 : LANCEMENT D'APPLICATIONS")
print("★"*70)

test_chat("Ouvre le bloc-notes", "Lancer Notepad", expected_type="tool_execution", expected_tool="launch_app")
time.sleep(2)
test_chat("Ouvre la calculatrice", "Lancer Calculatrice", expected_type="tool_execution", expected_tool="launch_app")
time.sleep(2)

# ========================================================================
# CATÉGORIE 3 : INTERACTION FENÊTRES
# ========================================================================
print("\n" + "★"*70)
print(" CATÉGORIE 3 : INTERACTION FENÊTRES")
print("★"*70)

test_chat("Tape 'hello world' dans le bloc-notes", "Taper texte Notepad", 
          expected_type="tool_execution", expected_tool="window_type")
time.sleep(1)

test_chat("Fais Ctrl+A dans le bloc-notes", "Hotkey Ctrl+A Notepad", 
          expected_type="tool_execution", expected_tool="window_hotkey")
time.sleep(1)

test_chat("Clique à la position 400, 300 dans le bloc-notes", "Click dans Notepad",
          expected_type="tool_execution", expected_tool="window_click")
time.sleep(1)

test_chat("C'est quoi la fenêtre active ?", "Fenêtre active",
          expected_type="tool_execution", expected_tool="window_get_active")

# ========================================================================
# CATÉGORIE 4 : RECHERCHE WEB
# ========================================================================
print("\n" + "★"*70)
print(" CATÉGORIE 4 : RECHERCHE WEB")
print("★"*70)

test_chat("Cherche la météo de Paris", "Recherche météo", 
          expected_type="tool_execution", expected_tool="web_search")
time.sleep(1)

test_chat("Résume la page https://fr.wikipedia.org/wiki/Python_(langage)", "Lire URL Wikipedia", 
          expected_type="tool_execution", expected_tool="read_url")

# ========================================================================
# CATÉGORIE 5 : NAVIGATION NAVIGATEUR (BRIDGE)
# ========================================================================
print("\n" + "★"*70)
print(" CATÉGORIE 5 : NAVIGATION NAVIGATEUR (BRIDGE)")
print("★"*70)

test_chat("Ouvre un nouvel onglet sur YouTube", "Nouvel onglet YouTube",
          expected_type="tool_execution", expected_tool="browser_new_tab")
time.sleep(2)

test_chat("Va sur google.com dans le navigateur", "Naviguer Google",
          expected_type="tool_execution", expected_tool="browser_navigate")

# ========================================================================
# CATÉGORIE 6 : COMMANDES COMPLEXES / MULTI-STEP
# ========================================================================
print("\n" + "★"*70)
print(" CATÉGORIE 6 : COMMANDES COMPLEXES / MULTI-STEP")
print("★"*70)

test_chat("Ouvre le bloc-notes et écris 'test atlas'", "Séquence ouvrir+écrire")
time.sleep(2)

test_chat("Ferme le bloc-notes", "Fermer app (compréhension)",
          expected_type="tool_execution")
time.sleep(1)

test_chat("Clique sur le bouton Fichier dans le bloc-notes", "Click sémantique (impossible)",
          expected_type="tool_execution")

# ========================================================================
# CATÉGORIE 7 : STREAMING JSON BRUT (test UI)  
# ========================================================================
print("\n" + "★"*70)
print(" CATÉGORIE 7 : STREAMING (JSON brut dans les tokens)")
print("★"*70)

test_stream("Ouvre steam", "Stream lancement Steam")
time.sleep(1)

test_stream("Cherche Python sur internet", "Stream recherche web")
time.sleep(1)

test_stream("Dis moi bonjour", "Stream texte simple")

# ========================================================================
# RAPPORT FINAL
# ========================================================================
print("\n\n" + "="*70)
print(" RAPPORT FINAL")
print("="*70)

pass_count = sum(1 for r in results if r["status"] == "PASS")
fail_count = sum(1 for r in results if r["status"] == "FAIL")
error_count = sum(1 for r in results if r["status"] == "ERROR")

print(f"\n  TOTAL: {len(results)} tests")
print(f"  ✅ PASS: {pass_count}")
print(f"  ⚠️  FAIL: {fail_count}")
print(f"  ❌ ERROR: {error_count}")

if fail_count > 0 or error_count > 0:
    print(f"\n  DÉTAILS DES ÉCHECS:")
    for r in results:
        if r["status"] != "PASS":
            print(f"\n  [{r['status']}] {r['test']}")
            print(f"    Prompt: \"{r['prompt']}\"")
            if r.get("issues"):
                for i in r["issues"]:
                    print(f"    → {i}")
            if r.get("detail"):
                print(f"    → {r['detail']}")

# Sauvegarder les résultats JSON pour le rapport
with open("tests/audit_results_v22.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\n  Résultats sauvegardés dans tests/audit_results_v22.json")
