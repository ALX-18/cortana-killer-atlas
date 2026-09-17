"""
Diagnostic v2.2 — Circuit interaction bout en bout.
Teste chaque maillon : Ollama → parser → routage → exécution.
"""

import asyncio
import json
import os
import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent  # scripts/manual/ -> racine
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


async def test_a_ollama_raw_responses():
    """Test A — Ollama génère-t-il le bon tool-call JSON ?"""
    print("=" * 70)
    print("  TEST A — Réponses RAW Ollama (3 requêtes)")
    print("=" * 70)

    from core.ollama_client import chat_full, build_system_prompt
    from core.context_monitor import collect_context
    from core.intent_engine import parse_model_response, extract_tool_calls

    context = collect_context()

    queries = [
        "Lance YouTube sur Opera GX",
        "Tape bonjour dans le bloc-notes",
        "Cherche Half-Life sur Steam",
    ]

    for i, query in enumerate(queries, 1):
        print(f"\n--- Requête {i}: \"{query}\" ---")
        try:
            raw = await chat_full(query, context, history=[], memories=[])
            print(f"  [RAW]    {raw[:500]}")

            parsed = parse_model_response(raw)
            print(f"  [PARSED] type={type(parsed).__name__}")
            if isinstance(parsed, dict):
                print(f"           tool={parsed.get('tool', 'N/A')}, args={parsed.get('args', {})}")
            elif isinstance(parsed, list):
                for step in parsed:
                    print(f"           step: tool={step.get('tool', 'N/A')}, args={step.get('args', {})}")
            else:
                print(f"           texte libre (pas de tool-call détecté)")
                print(f"           contenu: {str(parsed)[:200]}")

            tool_calls = extract_tool_calls(raw)
            print(f"  [TOOLS]  {len(tool_calls)} tool-call(s) extrait(s)")
            for tc in tool_calls:
                print(f"           → {tc.get('tool', '?')}({tc.get('args', {})})")

        except Exception as e:
            print(f"  [ERREUR] {e}")

    print()


def test_b_system_prompt_size():
    """Test B — Taille du system prompt."""
    print("=" * 70)
    print("  TEST B — Taille du system prompt")
    print("=" * 70)

    from core.ollama_client import build_system_prompt, SYSTEM_PROMPT_TEMPLATE
    from core.context_monitor import collect_context

    context = collect_context()

    # Template seul (sans contexte injecté)
    template_words = len(SYSTEM_PROMPT_TEMPLATE.split())
    template_chars = len(SYSTEM_PROMPT_TEMPLATE)
    template_tokens_est = int(template_words * 1.3)
    print(f"\n  Template seul:")
    print(f"    Caractères : {template_chars}")
    print(f"    Mots       : {template_words}")
    print(f"    Tokens est. : ~{template_tokens_est}")

    # Prompt complet avec contexte
    full_prompt = build_system_prompt(context, memories=["souvenir test 1", "souvenir test 2"])
    full_words = len(full_prompt.split())
    full_chars = len(full_prompt)
    full_tokens_est = int(full_words * 1.3)
    print(f"\n  Prompt complet (avec contexte + mémoires):")
    print(f"    Caractères : {full_chars}")
    print(f"    Mots       : {full_words}")
    print(f"    Tokens est. : ~{full_tokens_est}")

    if full_tokens_est > 4000:
        print(f"\n  ⚠️ ALERTE: {full_tokens_est} tokens > 4000 — Mistral 7B en difficulté!")
        print(f"     Mistral context window = 8192 tokens.")
        print(f"     Prompt consomme ~{int(full_tokens_est / 8192 * 100)}% du context window.")
        print(f"     Reste ~{8192 - full_tokens_est} tokens pour user message + history + réponse.")
    elif full_tokens_est > 3000:
        print(f"\n  ⚠️ WARNING: {full_tokens_est} tokens — limite haute pour Mistral 7B")
    else:
        print(f"\n  ✅ Taille OK ({full_tokens_est} tokens)")

    print()


def test_c_bridge_status():
    """Test C — Extension navigateur connectée ?"""
    print("=" * 70)
    print("  TEST C — Statut Browser Bridge")
    print("=" * 70)

    from tools.browser_bridge import browser_bridge_status, get_bridge

    status = browser_bridge_status()
    print(f"\n  Résultat : {json.dumps(status, indent=2)}")

    if status.get("connected"):
        print(f"  ✅ Extension connectée — {status.get('clients', 0)} client(s)")
    else:
        print(f"  ❌ Aucune extension connectée")
        print(f"     Le bridge écoute-t-il ? → voir Test D")
        print(f"     L'extension est-elle installée dans le navigateur ?")

    print()


def test_d_port_listening():
    """Test D — Port 9999 en écoute ?"""
    print("=" * 70)
    print("  TEST D — Port 9999 (WebSocket bridge)")
    print("=" * 70)

    import socket

    port = 9999
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()

    if result == 0:
        print(f"\n  ✅ Port {port} OUVERT — le bridge écoute")
    else:
        print(f"\n  ❌ Port {port} FERMÉ — le bridge ne tourne pas")
        print(f"     Le serveur FastAPI a-t-il démarré avec lifespan ?")
        print(f"     Vérifier les logs atlas.log pour l'erreur de démarrage du bridge.")

    print()


def test_e_direct_calls():
    """Test E — Appels directs aux fonctions (sans Ollama)."""
    print("=" * 70)
    print("  TEST E — Appels directs window_controller")
    print("=" * 70)

    from tools.window_controller import window_find, window_type, window_get_active, window_focus

    # E1 — Trouver le Bloc-notes
    print("\n  E1 — Recherche fenêtre 'Notepad' / 'Bloc-notes'...")
    for name in ["Notepad", "Bloc-notes", "notepad"]:
        result = window_find(name)
        if result["success"]:
            print(f"    ✅ Trouvé avec '{name}': {[w.get('title', w) for w in result['windows']]}")
            break
    else:
        print(f"    ❌ Bloc-notes non trouvé — ouvrir manuellement avant le test")

    # E2 — Fenêtre active
    print("\n  E2 — Fenêtre active...")
    active = window_get_active()
    if active["success"]:
        print(f"    ✅ Fenêtre active : '{active['title']}'")
    else:
        print(f"    ❌ Pas de fenêtre active")

    # E3 — Test window_type direct (DANGEREUX — tape réellement du texte)
    print("\n  E3 — window_type direct sur Notepad...")
    print("    ⚠️  Ce test va RÉELLEMENT taper du texte.")
    print("    ⚠️  Assurez-vous que le Bloc-notes est ouvert.")

    # Essayer de focaliser le bloc-notes d'abord
    focus_result = None
    for name in ["Notepad", "Bloc-notes", "Sans titre - Bloc-notes", "Untitled - Notepad"]:
        focus_result = window_focus(name)
        if focus_result["success"]:
            print(f"    Focus OK: {focus_result['message']}")
            break

    if focus_result and focus_result["success"]:
        import time
        time.sleep(0.5)
        type_result = window_type("Hello Atlas v2.2 - diagnostic", target=None)
        print(f"    Résultat type: {json.dumps(type_result, ensure_ascii=False)}")
        if type_result["success"]:
            print(f"    ✅ Texte tapé avec succès — VÉRIFIER VISUELLEMENT dans le Bloc-notes")
        else:
            print(f"    ❌ Échec saisie: {type_result['message']}")
    else:
        print(f"    ⏭️  Bloc-notes non trouvé / focus échoué — test E3 sauté")
        if focus_result:
            print(f"    Détail: {focus_result.get('message', '')}")

    print()


def test_f_route_interaction():
    """Test F — route_interaction() fonctionne-t-elle ?"""
    print("=" * 70)
    print("  TEST F — Routage interaction (intent_engine)")
    print("=" * 70)

    from core.intent_engine import route_interaction, TOOL_HANDLERS
    from core.context_monitor import collect_context

    context = collect_context()
    route = route_interaction(context)
    fg = context.get("foreground_window", {})

    print(f"\n  Fenêtre active : process='{fg.get('process', '?')}', title='{fg.get('title', '?')}'")
    print(f"  Route choisie  : {route}")

    print(f"\n  Vérification TOOL_HANDLERS async vs sync :")
    async_tools = []
    sync_tools = []
    for name, handler in TOOL_HANDLERS.items():
        if "browser_ext" in name or "browser_navigate" in name or "browser_new_tab" in name:
            # Ces handlers appellent des coroutines
            async_tools.append(name)
        elif "window_" in name or "browser_bridge" in name:
            sync_tools.append(name)

    print(f"    Outils async (browser_bridge) : {len(async_tools)} → {async_tools}")
    print(f"    Outils sync  (window_*)       : {len(sync_tools)} → {sync_tools}")

    # Vérifier que execute_tool gère bien l'awaitable
    print(f"\n  Vérification inspect.isawaitable dans execute_tool :")
    import inspect
    for tool_name in ["browser_navigate", "window_find"]:
        handler = TOOL_HANDLERS.get(tool_name)
        if handler:
            test_result = handler({"url": "", "title": ""})
            is_awaitable = inspect.isawaitable(test_result)
            print(f"    {tool_name}: retour={type(test_result).__name__}, awaitable={is_awaitable}")

    print()


def test_g_route_not_called():
    """Test G — route_interaction() est-elle appelée dans execute_tool ?"""
    print("=" * 70)
    print("  TEST G — route_interaction() appelée dans le pipeline ?")
    print("=" * 70)

    import inspect
    from core import intent_engine

    # Lire le source de execute_tool
    source = inspect.getsource(intent_engine.execute_tool)
    uses_route = "route_interaction" in source
    print(f"\n  execute_tool() contient 'route_interaction' : {uses_route}")

    if not uses_route:
        print(f"  ℹ️  route_interaction() existe mais n'est PAS appelée dans execute_tool.")
        print(f"     Elle est probablement prévue pour un usage futur ou dans le prompt Ollama.")
        print(f"     Le routage dépend donc ENTIÈREMENT du choix d'outil par Ollama.")

    # Vérifier process_ai_response
    source2 = inspect.getsource(intent_engine.process_ai_response)
    uses_route2 = "route_interaction" in source2
    print(f"  process_ai_response() contient 'route_interaction' : {uses_route2}")

    print()


async def main():
    print("\n" + "=" * 70)
    print("  DIAGNOSTIC v2.2 — Circuit Interaction Bout en Bout")
    print("  " + "=" * 66)
    print()

    # Tests synchrones
    test_b_system_prompt_size()
    test_c_bridge_status()
    test_d_port_listening()
    test_e_direct_calls()
    test_f_route_interaction()
    test_g_route_not_called()

    # Test async (Ollama)
    await test_a_ollama_raw_responses()

    print("=" * 70)
    print("  DIAGNOSTIC TERMINÉ")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
