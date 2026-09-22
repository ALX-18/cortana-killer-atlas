"""
Inventaire de la mémoire : doublons exacts et artefacts de test (sprint D / D5 et D7).

Cet outil ne supprime RIEN et n'écrit rien dans la base. Il produit un rapport Markdown
destiné à une décision humaine : pour chaque groupe de doublons, la règle de conservation
proposée ; pour chaque artefact présumé, la raison de le croire tel.

    python scripts/memory_inventory.py --out docs/rapports/INVENTAIRE_MEMOIRE_D.md
"""

import argparse
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import chromadb

COLLECTIONS = ["atlas_memory_e5", "atlas_memory", "atlas_documents", "atlas_conversations",
               "atlas_errors"]

# Motifs d'artefact de test, avec la raison affichée dans le rapport.
ARTEFACT_RULES = [
    (re.compile(r"DOCUMENT_ONLY_MARKER|CONVERSATION_ONLY|ISOLATION_MARKER", re.I),
     "marqueur d'isolation écrit par la suite de tests"),
    (re.compile(r"\b(Atlas|projet Atlas)\s+[0-9a-f]{6}\b"),
     "identifiant hexadécimal aléatoire accolé au nom : fixture de test"),
    (re.compile(r"cible=jeu_[0-9a-f]{6}|cible=t_[0-9a-f]{6}|intent=x\b|app=a\b"),
     "signature d'erreur fabriquée par un test (cible et app générées)"),
    (re.compile(r"\bpytest\b|pytest-of-|\btest_[a-z_]+\b|tmp_path|conftest", re.I),
     "référence explicite à l'outillage de tests"),
    (re.compile(r"\b(foo|bar|baz|lorem ipsum|dummy|placeholder)\b", re.I),
     "texte de remplissage"),
    (re.compile(r"^(test|essai)\b", re.I),
     "texte commençant par « test »"),
]


def classify_artefact(text: str):
    for rule, reason in ARTEFACT_RULES:
        if rule.search(text or ""):
            return reason
    return None


def keep_choice(entries):
    """Règle de conservation proposée : la plus ANCIENNE, à métadonnées égales.

    Justification : la première occurrence porte la date réelle du souvenir. Les copies
    suivantes sont des réécritures de la même information, sans valeur ajoutée. À date
    identique, on garde celle qui porte le plus de métadonnées.
    """
    return sorted(entries, key=lambda e: (e["created_at"], -len(e["meta"])))[0]


def load(client, name):
    try:
        coll = client.get_collection(name)
    except Exception:
        return None
    data = coll.get(include=["documents", "metadatas"])
    metas = data["metadatas"] or [{} for _ in data["ids"]]
    return [
        {"id": i, "text": d or "", "meta": m or {},
         "created_at": (m or {}).get("created_at") or (m or {}).get("timestamp") or 0,
         "category": (m or {}).get("category", "")}
        for i, d, m in zip(data["ids"], data["documents"], metas)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/rapports/INVENTAIRE_MEMOIRE_D.md")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    client = chromadb.HttpClient(host=args.host, port=args.port)
    client.heartbeat()
    lines = ["# Inventaire de la mémoire — sprint D",
             "",
             "Produit par `scripts/memory_inventory.py`. **Aucune suppression n'a été faite.**",
             "Ce document sert de base de décision : Alexis tranche, ligne par ligne si besoin.",
             ""]

    for name in COLLECTIONS:
        items = load(client, name)
        if items is None:
            continue
        lines += [f"## {name} — {len(items)} éléments", ""]

        # --- D5 : doublons exacts
        groups = collections.defaultdict(list)
        for it in items:
            groups[(it["category"], it["text"])].append(it)
        dups = {k: v for k, v in groups.items() if len(v) > 1}
        copies = sum(len(v) - 1 for v in dups.values())
        lines += [f"### Doublons exacts : {len(dups)} groupe(s), {copies} copie(s) en trop", ""]
        if dups:
            lines += ["| Copies | Catégorie | À conserver (proposition) | Texte |",
                      "|---|---|---|---|"]
            for (cat, text), entries in sorted(dups.items(), key=lambda kv: -len(kv[1])):
                keep = keep_choice(entries)
                extrait = text.replace("|", "\\|").replace("\n", " ")[:110]
                lines.append(f"| {len(entries)} | {cat or '—'} | `{keep['id']}` | {extrait} |")
            lines.append("")

        # --- D7 : artefacts de test
        artefacts = [(it, classify_artefact(it["text"])) for it in items]
        artefacts = [(it, why) for it, why in artefacts if why]
        lines += [f"### Artefacts de test présumés : {len(artefacts)}", ""]
        if artefacts:
            lines += ["| Identifiant | Raison | Texte |", "|---|---|---|"]
            for it, why in artefacts:
                extrait = it["text"].replace("|", "\\|").replace("\n", " ")[:90]
                lines.append(f"| `{it['id']}` | {why} | {extrait} |")
            lines.append("")

    lines += ["## Règle de conservation proposée pour les doublons", "",
              "Garder la **plus ancienne** occurrence : elle porte la date réelle du souvenir, "
              "les copies suivantes n'ajoutent rien. À date égale, garder celle qui a le plus "
              "de métadonnées.", "",
              "La cause a été traitée : depuis le sprint D, `MemoryManager.save()` refuse "
              "d'écrire un texte déjà présent dans la même catégorie (empreinte `content_hash`). "
              "Les doublons listés ici sont **historiques** et ne s'aggravent plus.", ""]

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Inventaire écrit : {out} ({len(lines)} lignes). Aucune suppression effectuée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
