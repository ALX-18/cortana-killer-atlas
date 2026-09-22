"""
Ré-encodage de la mémoire legacy en e5 (sprint D / D6).

`atlas_memory` a été écrite sans embeddings : ChromaDB l'a vectorisée avec son modèle par
défaut (all-MiniLM-L6-v2, anglophone, 384 dimensions) alors que toutes les autres
collections utilisent intfloat/multilingual-e5-base en 768. Cet outil recalcule les
vecteurs dans une **nouvelle** collection.

Il ne supprime jamais rien : la collection d'origine reste intacte, et sert de retour
arrière tant que la nouvelle n'est pas validée.

    python scripts/reencode_memory.py plan                  # ce qui serait fait, sans écrire
    python scripts/reencode_memory.py run [--target NOM]    # écrit la nouvelle collection
    python scripts/reencode_memory.py verify [--target NOM] # compare les deux collections

Exige une sauvegarde vérifiée au préalable (scripts/backup_memory.py backup + verify).
"""

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import chromadb

from core.memory_manager import _content_hash
from core_conversational.memory_core import EMBED_DIM, embed_passages

SOURCE_DEFAULT = "atlas_memory"
TARGET_DEFAULT = "atlas_memory_e5"
BATCH = 32


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def client(host: str, port: int):
    c = chromadb.HttpClient(host=host, port=port)
    c.heartbeat()
    return c


def read_all(coll) -> dict:
    data = coll.get(include=["documents", "metadatas", "embeddings"])
    return {
        "ids": data["ids"],
        "documents": data["documents"],
        "metadatas": data["metadatas"] or [{} for _ in data["ids"]],
        "dims": {len(e) for e in (data["embeddings"] if data["embeddings"] is not None else [])},
    }


def cmd_plan(args) -> int:
    c = client(args.host, args.port)
    src = read_all(c.get_collection(args.source))
    texts = src["documents"]
    uniques = len(set(texts))
    log(f"Source '{args.source}' : {len(texts)} éléments, {uniques} textes uniques, "
        f"dimensions actuelles {sorted(src['dims'])}")
    log(f"Cible  '{args.target}' : {len(texts)} éléments à écrire en {EMBED_DIM} dimensions "
        f"(mêmes identifiants, mêmes textes, mêmes métadonnées + content_hash)")
    existing = [x.name for x in c.list_collections()]
    if args.target in existing:
        log(f"ATTENTION : '{args.target}' existe déjà ({c.get_collection(args.target).count()} éléments)")
    log("Aucun élément ne sera supprimé : la collection d'origine reste intacte.")
    return 0


def cmd_run(args) -> int:
    c = client(args.host, args.port)
    src_coll = c.get_collection(args.source)
    src = read_all(src_coll)
    total = len(src["ids"])
    if not total:
        log("Source vide — rien à faire.")
        return 1

    existing = [x.name for x in c.list_collections()]
    if args.target in existing:
        target = c.get_collection(args.target)
        if target.count() and not args.force:
            log(f"'{args.target}' existe déjà et contient {target.count()} éléments. "
                f"Utiliser --force pour compléter, ou choisir un autre nom.")
            return 1
    else:
        target = c.create_collection(name=args.target, metadata={"hnsw:space": "cosine"})

    already = set(target.get()["ids"]) if target.count() else set()
    written = 0
    for start in range(0, total, BATCH):
        ids = src["ids"][start:start + BATCH]
        docs = src["documents"][start:start + BATCH]
        metas = src["metadatas"][start:start + BATCH]
        keep = [i for i, mid in enumerate(ids) if mid not in already]
        if not keep:
            continue
        ids = [ids[i] for i in keep]
        docs = [docs[i] for i in keep]
        metas = [dict(metas[i]) for i in keep]
        vecs = embed_passages(docs)
        if vecs is None:
            log("Modèle e5 indisponible — arrêt sans écriture supplémentaire.")
            return 2
        for meta, doc in zip(metas, docs):
            meta.setdefault("content_hash", _content_hash(meta.get("category", ""), doc))
            meta["reencoded_from"] = args.source
        target.add(ids=ids, documents=docs, metadatas=metas, embeddings=vecs)
        written += len(ids)
        log(f"  {written}/{total} éléments ré-encodés")
    log(f"Terminé : {written} éléments écrits dans '{args.target}'. "
        f"'{args.source}' est inchangée ({src_coll.count()} éléments).")
    log(f"Étape suivante obligatoire : python scripts/reencode_memory.py verify --target {args.target}")
    return 0


def cmd_verify(args) -> int:
    c = client(args.host, args.port)
    src = read_all(c.get_collection(args.source))
    tgt_coll = c.get_collection(args.target)
    tgt = read_all(tgt_coll)

    problems = []
    if len(src["ids"]) != len(tgt["ids"]):
        problems.append(f"nombre d'éléments : {len(src['ids'])} → {len(tgt['ids'])}")
    if tgt["dims"] != {EMBED_DIM}:
        problems.append(f"dimensions de la cible : {sorted(tgt['dims'])}, attendu {EMBED_DIM}")

    by_id_src = dict(zip(src["ids"], zip(src["documents"], src["metadatas"])))
    by_id_tgt = dict(zip(tgt["ids"], zip(tgt["documents"], tgt["metadatas"])))
    missing = sorted(set(by_id_src) - set(by_id_tgt))
    extra = sorted(set(by_id_tgt) - set(by_id_src))
    if missing:
        problems.append(f"{len(missing)} identifiant(s) absent(s) de la cible, ex. {missing[:3]}")
    if extra:
        problems.append(f"{len(extra)} identifiant(s) en trop dans la cible, ex. {extra[:3]}")

    texte_diff, meta_diff = 0, 0
    for mid, (doc, meta) in by_id_src.items():
        if mid not in by_id_tgt:
            continue
        tdoc, tmeta = by_id_tgt[mid]
        if doc != tdoc:
            texte_diff += 1
        for k, v in (meta or {}).items():
            if tmeta.get(k) != v:
                meta_diff += 1
                break
    if texte_diff:
        problems.append(f"{texte_diff} texte(s) différent(s)")
    if meta_diff:
        problems.append(f"{meta_diff} élément(s) dont une métadonnée d'origine a changé")

    log(f"Source '{args.source}' : {len(src['ids'])} éléments, dimensions {sorted(src['dims'])}")
    log(f"Cible  '{args.target}' : {len(tgt['ids'])} éléments, dimensions {sorted(tgt['dims'])}")
    log(f"Textes comparés : {len(by_id_src)} ; métadonnées d'origine conservées : "
        f"{len(by_id_src) - meta_diff}/{len(by_id_src)}")

    report = {
        "source": args.source, "target": args.target,
        "count_source": len(src["ids"]), "count_target": len(tgt["ids"]),
        "dims_source": sorted(src["dims"]), "dims_target": sorted(tgt["dims"]),
        "problems": problems,
    }
    if args.report:
        pathlib.Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    if problems:
        for p in problems:
            log(f"PROBLÈME : {p}")
        return 1
    log("ÉQUIVALENCE PROUVÉE : mêmes identifiants, mêmes textes, mêmes métadonnées, "
        f"vecteurs en {EMBED_DIM} dimensions. La collection d'origine est intacte.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "run", "verify"])
    parser.add_argument("--source", default=SOURCE_DEFAULT)
    parser.add_argument("--target", default=TARGET_DEFAULT)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--force", action="store_true", help="compléter une cible non vide")
    parser.add_argument("--report", help="fichier JSON de rapport (verify)")
    args = parser.parse_args()
    return {"plan": cmd_plan, "run": cmd_run, "verify": cmd_verify}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
