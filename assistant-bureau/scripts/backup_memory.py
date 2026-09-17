"""
Sprint M — Sauvegarde et vérification de restauration de la mémoire long terme (ChromaDB).

Contexte : jusqu'au sprint M-bis, l'image `chromadb/chroma` persistait dans `/data` à
l'intérieur du conteneur `assistant_chromadb` (risque L21). Depuis M-bis, `/data` est le volume
nommé `atlas_chromadb_data`, monté dans `atlas_chromadb` (projet compose `atlas`). Ce script
copie `/data` hors du conteneur, quel que soit le montage, et prouve que la copie est restaurable.

Garanties :
- sur le conteneur de production, UNIQUEMENT des lectures : `docker inspect`,
  `docker exec` (sha256sum, find, cat) et `docker cp` depuis le conteneur, plus des requêtes
  HTTP de lecture (list, count, get) ;
- aucune commande `docker rm`, `stop`, `restart`, `compose` sur la production ;
- la vérification tourne dans un conteneur jetable (`atlas_memcheck_*`, autre port, même
  image par identifiant, `--pull never`) sur une COPIE de la sauvegarde, puis le supprime.

Usage (depuis assistant-bureau/) :
    python scripts/backup_memory.py backup  [--dest C:\\Users\\<vous>\\Atlas_backups\\memoire]
    python scripts/backup_memory.py verify  <dossier_de_sauvegarde> [--port 8101] [--samples 25]
    python scripts/backup_memory.py verify  <dossier> --target-url http://127.0.0.1:8011   # serveur déjà démarré
    python scripts/backup_memory.py check-volume <dossier> --volume atlas_chromadb_data

Le conteneur de production est détecté automatiquement (`atlas_chromadb`, sinon
`assistant_chromadb`) ; `--container` force le choix.

Codes de retour : 0 = succès vérifié ; 1 = erreur d'exécution ; 2 = sauvegarde ou
restauration NON conforme (voir le rapport JSON écrit dans le dossier de sauvegarde).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

PROD_CONTAINERS = ("atlas_chromadb", "assistant_chromadb")  # nouveau (M-bis), ancien (conservé arrêté)
PROD_VOLUME = "atlas_chromadb_data"
PROTECTED = PROD_CONTAINERS + (PROD_VOLUME,)
CHECK_PREFIX = "atlas_memcheck_"
DATA_DIR = "/data"
API = "/api/v2/tenants/default_tenant/databases/default_database"
DEFAULT_DEST = Path.home() / "Atlas_backups" / "memoire"


# --------------------------------------------------------------------------- #
#  Utilitaires
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def docker(*args: str, check: bool = True, timeout: float = 300) -> str:
    # Garde-fou : aucune commande mutante ne doit viser la production.
    mutating = {"rm", "stop", "kill", "restart", "pause", "unpause", "update", "rename", "compose", "volume"}
    if args and args[0] in mutating and any(p == a or f"{p}:" in a for p in PROTECTED for a in args[1:]):
        raise RuntimeError(f"Refus : commande mutante sur une ressource protégée : docker {' '.join(args)}")
    proc = subprocess.run(["docker", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)
    if check and proc.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} → {proc.returncode}: {proc.stderr.strip()}")
    return proc.stdout


def http(base: str, path: str, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def container_hashes(container: str) -> dict[str, str]:
    out = docker("exec", container, "sh", "-c", f"find {DATA_DIR} -type f -exec sha256sum {{}} +")
    hashes = {}
    for line in out.splitlines():
        digest, _, path = line.partition("  ")
        hashes[path.strip()[len(DATA_DIR) + 1:]] = digest.strip()
    return hashes


def host_hashes(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha256_file(p) for p in sorted(root.rglob("*")) if p.is_file()}


# --------------------------------------------------------------------------- #
#  Lecture de la mémoire (API HTTP, lecture seule)
# --------------------------------------------------------------------------- #

def list_collections(base: str) -> list[dict]:
    return http(base, f"{API}/collections?limit=1000")


def all_items(base: str, cid: str, include: list[str], page: int = 300) -> dict:
    out = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    offset = 0
    while True:
        res = http(base, f"{API}/collections/{cid}/get",
                   {"limit": page, "offset": offset, "include": include}, timeout=120)
        ids = res.get("ids") or []
        if not ids:
            break
        out["ids"] += ids
        for key in ("documents", "metadatas", "embeddings"):
            if key in include:
                out[key] += res.get(key) or []
        offset += len(ids)
    return out


def summarize(base: str) -> dict:
    """Résumé de la mémoire : collections, volumes, dimensions, dates extrêmes."""
    summary = {"version": http(base, "/api/v2/version"), "collections": {}}
    for c in list_collections(base):
        items = all_items(base, c["id"], ["metadatas"])
        dates = []
        for m in items["metadatas"]:
            for k in ("timestamp", "created_at", "date", "ts", "time"):
                v = (m or {}).get(k)
                if isinstance(v, str) and v[:4].isdigit():
                    dates.append(v)
                    break
                if isinstance(v, (int, float)) and v > 1e9:
                    dates.append(dt.datetime.fromtimestamp(v / (1000 if v > 1e12 else 1)).isoformat())
                    break
        meta_keys = sorted({k for m in items["metadatas"] for k in (m or {})})
        summary["collections"][c["name"]] = {
            "id": c["id"],
            "count": http(base, f"{API}/collections/{c['id']}/count"),
            "dimension": c.get("dimension"),
            "metadata": c.get("metadata"),
            "embedding_function": (c.get("configuration_json") or {}).get("embedding_function"),
            "oldest": min(dates) if dates else None,
            "newest": max(dates) if dates else None,
            "dated_items": len(dates),
            "metadata_keys": meta_keys,
        }
    return summary


# --------------------------------------------------------------------------- #
#  backup
# --------------------------------------------------------------------------- #

def resolve_container(name: str | None) -> str:
    """Conteneur de production : celui demandé, sinon le premier démarré parmi PROD_CONTAINERS."""
    if name:
        return name
    running = docker("ps", "--format", "{{.Names}}").split()
    for candidate in PROD_CONTAINERS:
        if candidate in running:
            return candidate
    raise RuntimeError(f"aucun conteneur ChromaDB démarré parmi {PROD_CONTAINERS}")


def data_mount(state: dict) -> str:
    for m in state.get("Mounts", []):
        if m.get("Destination") == DATA_DIR:
            return f"{m.get('Type')}:{m.get('Name') or m.get('Source')}"
    return "couche du conteneur (non persisté)"


def cmd_backup(args) -> int:
    container = resolve_container(args.container)
    state = json.loads(docker("inspect", container))[0]
    if not state["State"]["Running"]:
        log(f"ERREUR : {container} n'est pas démarré.")
        return 1
    image_id = state["Image"]
    config = docker("exec", container, "sh", "-c", "cat /config.yaml 2>/dev/null; chroma --version 2>/dev/null")
    log(f"Conteneur {container} — image {image_id[:19]} — {config.strip().splitlines()[-1]} — /data : {data_mount(state)}")
    if f'persist_path: "{DATA_DIR}"' not in config:
        log(f"ERREUR : persist_path inattendu, ce script ne sait sauvegarder que {DATA_DIR} :\n{config}")
        return 1

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    target = Path(args.dest) / f"chromadb_{stamp}"
    data_dir = target / "data"
    target.mkdir(parents=True, exist_ok=False)

    # Le résumé passe AVANT les empreintes : au premier accès après démarrage, le serveur
    # Chroma 1.x recharge ses index HNSW et les réécrit (constaté au sprint M). On attend
    # ensuite que /data soit stable avant de copier.
    log("Résumé de la mémoire via l'API (lecture seule)…")
    summary = summarize(args.url)
    log("Attente de stabilité de /data (empreintes identiques à 10 s d'intervalle)…")
    before = container_hashes(container)
    for attempt in range(12):
        time.sleep(10)
        again = container_hashes(container)
        if again == before:
            break
        log(f"  encore en écriture (essai {attempt + 1})")
        before = again
    else:
        log("ERREUR : /data ne se stabilise pas, copie annulée.")
        shutil.rmtree(target, ignore_errors=True)
        return 2
    log(f"  stable : {len(before)} fichiers")

    log(f"docker cp {container}:{DATA_DIR} → {data_dir}")
    docker("cp", f"{container}:{DATA_DIR}", str(data_dir))

    log("Empreintes côté hôte…")
    copied = host_hashes(data_dir)
    log("Empreintes dans le conteneur (après copie)…")
    after = container_hashes(container)

    quiescent = before == after
    identical = copied == before
    problems = []
    if not quiescent:
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        problems.append(f"la base a changé pendant la copie : {changed[:10]}")
    if not identical:
        diff = sorted(k for k in set(before) | set(copied) if before.get(k) != copied.get(k))
        problems.append(f"copie différente de l'original : {diff[:10]}")

    # Archive unique, pour une empreinte globale et un transport simple.
    archive = target / f"chromadb_data_{stamp}.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(data_dir, arcname="data")
    archive_sha = sha256_file(archive)

    files = [{"path": p, "size": (data_dir / p).stat().st_size, "sha256": h} for p, h in sorted(copied.items())]
    manifest = {
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "source": {"container": container, "image_id": image_id,
                   "image": state["Config"]["Image"], "persist_path": DATA_DIR,
                   "server": config.strip().splitlines()[-1], "api_url": args.url,
                   "data_mount": data_mount(state)},
        "quiescent_during_copy": quiescent,
        "copy_identical_to_source": identical,
        "problems": problems,
        "file_count": len(files),
        "total_bytes": sum(f["size"] for f in files),
        "archive": {"name": archive.name, "bytes": archive.stat().st_size, "sha256": archive_sha},
        "files": files,
        "memory_summary": summary,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    sums = "".join(f"{f['sha256']}  data/{f['path']}\n" for f in files) + f"{archive_sha}  {archive.name}\n"
    (target / "SHA256SUMS").write_text(sums, encoding="utf-8")
    manifest_sha = sha256_file(target / "manifest.json")
    (target / "manifest.json.sha256").write_text(f"{manifest_sha}  manifest.json\n", encoding="utf-8")

    log(f"Sauvegarde : {target}")
    log(f"  {len(files)} fichiers, {manifest['total_bytes']} octets ; archive {archive.name} sha256={archive_sha}")
    for name, c in summary["collections"].items():
        log(f"  {name:22} {c['count']:>6} éléments  dim={c['dimension']}  {c['oldest']} → {c['newest']}")
    if problems:
        for p in problems:
            log(f"NON CONFORME : {p}")
        return 2
    log("Copie conforme : base inchangée pendant la copie, empreintes identiques.")
    log(f"Étape suivante obligatoire : python scripts/backup_memory.py verify \"{target}\"")
    return 0


# --------------------------------------------------------------------------- #
#  verify
# --------------------------------------------------------------------------- #

def _same_embedding(a, b, tol=0.0) -> bool:
    if a is None or b is None:
        return a is b
    return len(a) == len(b) and all(math.isclose(x, y, rel_tol=0, abs_tol=tol) for x, y in zip(a, b))


def compare_collection(live: str, restored: str, lc: dict, rc: dict, samples: int) -> dict:
    res = {"name": lc["name"], "problems": []}
    a = all_items(live, lc["id"], ["documents", "metadatas"])
    b = all_items(restored, rc["id"], ["documents", "metadatas"])
    res["count_live"], res["count_restored"] = len(a["ids"]), len(b["ids"])
    ia = dict(zip(a["ids"], zip(a["documents"], a["metadatas"])))
    ib = dict(zip(b["ids"], zip(b["documents"], b["metadatas"])))
    if set(ia) != set(ib):
        res["problems"].append(f"ids différents : {len(set(ia) ^ set(ib))} en écart")
    diff_docs = [i for i in ia if i in ib and ia[i] != ib[i]]
    res["documents_metadatas_compared"] = len(set(ia) & set(ib))
    if diff_docs:
        res["problems"].append(f"{len(diff_docs)} documents/métadonnées différents, ex. {diff_docs[:3]}")
    res["dimension_live"], res["dimension_restored"] = lc.get("dimension"), rc.get("dimension")
    if lc.get("dimension") != rc.get("dimension"):
        res["problems"].append("dimension différente")

    ids = sorted(set(ia) & set(ib))
    step = max(1, len(ids) // samples) if ids else 1
    sample = ids[::step][:samples]
    res["embeddings_compared"] = len(sample)
    if sample:
        ea = http(live, f"{API}/collections/{lc['id']}/get", {"ids": sample, "include": ["embeddings", "documents"]})
        eb = http(restored, f"{API}/collections/{rc['id']}/get", {"ids": sample, "include": ["embeddings", "documents"]})
        ma = dict(zip(ea["ids"], ea["embeddings"]))
        mb = dict(zip(eb["ids"], eb["embeddings"]))
        bad = [i for i in sample if not _same_embedding(ma.get(i), mb.get(i))]
        if bad:
            res["problems"].append(f"{len(bad)} embeddings différents sur {len(sample)}")
        res["sample_excerpts"] = [
            {"id": i, "document": (d or "")[:120]} for i, d in list(zip(eb["ids"], eb["documents"]))[:3]
        ]
        # Recherche vectorielle de bout en bout : la même requête doit donner le même résultat
        # sur la production et sur la copie restaurée. On ne teste pas « l'élément sonde est
        # premier » : plusieurs éléments peuvent partager exactement le même embedding
        # (souvenirs répétés), et l'ordre entre ex æquo n'est pas garanti.
        n = min(5, len(ids))
        probes = sample[:: max(1, len(sample) // 5)][:5]
        mismatches, self_found, dup_ties = 0, 0, 0
        for pid in probes:
            body = {"query_embeddings": [mb[pid]], "n_results": n, "include": ["distances"]}
            ql = http(live, f"{API}/collections/{lc['id']}/query", body)
            qr = http(restored, f"{API}/collections/{rc['id']}/query", body)
            dl = [round(x, 5) for x in ql["distances"][0]]
            dr = [round(x, 5) for x in qr["distances"][0]]
            if dl != dr:
                mismatches += 1
            if pid in qr["ids"][0]:
                self_found += 1
            elif dr and dr[0] <= 1e-5:
                dup_ties += 1  # un autre élément à distance nulle occupe les places : doublon exact
        res["query_probes"] = len(probes)
        res["query_same_distances_live_vs_restored"] = len(probes) - mismatches
        res["query_probe_in_top_n"] = self_found
        res["query_probe_hidden_by_exact_duplicates"] = dup_ties
        if mismatches:
            res["problems"].append(f"requêtes vectorielles différentes entre production et restauration ({mismatches}/{len(probes)})")
        if len(probes) - self_found - dup_ties:
            res["problems"].append("une requête ne retrouve ni l'élément sonde ni un doublon exact")
    return res


def cmd_verify(args) -> int:
    backup = Path(args.backup).resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    report = {"backup": str(backup), "started": dt.datetime.now().isoformat(timespec="seconds"),
              "problems": [], "collections": []}

    log("1/5 Contrôle des empreintes de la sauvegarde…")
    expected_manifest = (backup / "manifest.json.sha256").read_text(encoding="utf-8").split()[0]
    if sha256_file(backup / "manifest.json") != expected_manifest:
        report["problems"].append("manifest.json altéré")
    current = host_hashes(backup / "data")
    expected = {f["path"]: f["sha256"] for f in manifest["files"]}
    if current != expected:
        report["problems"].append("fichiers de la sauvegarde différents du manifeste")
    if sha256_file(backup / manifest["archive"]["name"]) != manifest["archive"]["sha256"]:
        report["problems"].append("archive tar altérée")
    report["hashes_ok"] = not report["problems"]
    log(f"  empreintes {'OK' if report['hashes_ok'] else 'EN ÉCART'} ({len(current)} fichiers)")

    # Mode --target-url : on vérifie un serveur déjà démarré (ex. nouveau conteneur de migration),
    # sans créer de conteneur jetable.
    external = bool(args.target_url)
    work = Path(tempfile.mkdtemp(prefix="atlas_memcheck_"))
    name = f"{CHECK_PREFIX}{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    assert name.startswith(CHECK_PREFIX) and name not in PROTECTED
    image = manifest["source"]["image_id"]
    restored = args.target_url.rstrip("/") if external else f"http://127.0.0.1:{args.port}"
    if external and restored == args.live_url.rstrip("/"):
        log("ERREUR : --target-url et --live-url désignent le même serveur.")
        return 1
    report["target"] = restored if external else f"conteneur jetable {name}"
    started = False
    try:
        if external:
            log(f"2/5 Serveur cible déjà démarré : {restored} (aucun conteneur créé)")
        else:
            # Restauration depuis l'ARCHIVE (ce qu'on transporterait réellement), dans une copie jetable.
            with tarfile.open(backup / manifest["archive"]["name"]) as tar:
                tar.extractall(work, filter="data")
            log(f"2/5 Conteneur jetable {name} (image {image[:19]}, port {args.port}, --pull never)…")
            docker("run", "-d", "--pull", "never", "--name", name, "-p", f"127.0.0.1:{args.port}:8000",
                   "-e", "ANONYMIZED_TELEMETRY=FALSE", "-v", f"{work / 'data'}:{DATA_DIR}", image)
            started = True
        for _ in range(60):
            try:
                http(restored, "/api/v2/heartbeat", timeout=2)
                break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("le conteneur jetable ne répond pas")
        report["restored_version"] = http(restored, "/api/v2/version")

        log("3/5 Comparaison avec le manifeste (collections, volumes, dimensions)…")
        restored_summary = summarize(restored)
        report["restored_summary"] = restored_summary
        ref = manifest["memory_summary"]["collections"]
        got = restored_summary["collections"]
        if set(ref) != set(got):
            report["problems"].append(f"collections différentes : {sorted(set(ref) ^ set(got))}")
        for n in sorted(set(ref) & set(got)):
            for k in ("count", "dimension"):
                if ref[n][k] != got[n][k]:
                    report["problems"].append(f"{n}.{k} : sauvegarde {ref[n][k]} / restauré {got[n][k]}")

        log("4/5 Comparaison élément par élément avec la base de production (lecture seule)…")
        try:
            live_cols = {c["name"]: c for c in list_collections(args.live_url)}
            live_counts = {n: http(args.live_url, f"{API}/collections/{c['id']}/count") for n, c in live_cols.items()}
            report["live_unchanged_since_backup"] = all(live_counts.get(n) == ref[n]["count"] for n in ref)
            rest_cols = {c["name"]: c for c in list_collections(restored)}
            for n in sorted(set(live_cols) & set(rest_cols)):
                r = compare_collection(args.live_url, restored, live_cols[n], rest_cols[n], args.samples)
                report["collections"].append(r)
                report["problems"] += [f"{n} : {p}" for p in r["problems"]]
                log(f"  {n:22} {r['count_live']:>6}/{r['count_restored']:<6} docs+méta comparés={r['documents_metadatas_compared']} "
                    f"embeddings comparés={r['embeddings_compared']} "
                    f"requêtes identiques={r.get('query_same_distances_live_vs_restored')}/{r.get('query_probes')} "
                    f"(sonde trouvée {r.get('query_probe_in_top_n')}, masquée par doublons {r.get('query_probe_hidden_by_exact_duplicates')}) "
                    f"{'OK' if not r['problems'] else r['problems']}")
        except Exception as e:
            report["problems"].append(f"comparaison avec la production impossible : {e}")
    finally:
        log("5/5 Suppression du conteneur jetable et de la copie de travail…")
        if started:
            assert name.startswith(CHECK_PREFIX)
            docker("rm", "-f", name, check=False)
        shutil.rmtree(work, ignore_errors=True)
        report["cleanup_container_absent"] = external or name not in docker("ps", "-a", "--format", "{{.Names}}").split()

    report["finished"] = dt.datetime.now().isoformat(timespec="seconds")
    report["restorable"] = not report["problems"]
    out = backup / f"verify_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Rapport : {out}")
    if report["problems"]:
        for p in report["problems"]:
            log(f"NON CONFORME : {p}")
        return 2
    log("RESTAURATION PROUVÉE : collections, volumes, dimensions, documents, métadonnées, "
        "échantillon d'embeddings et requête vectorielle identiques.")
    return 0


def cmd_check_volume(args) -> int:
    """Empreintes des fichiers d'un volume nommé (montage en lecture seule, conteneur --rm) vs manifeste."""
    backup = Path(args.backup).resolve()
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    image = manifest["source"]["image_id"]
    out = docker("run", "--rm", "--pull", "never", "--entrypoint", "sh", "-v", f"{args.volume}:{DATA_DIR}:ro",
                 image, "-c", f"find {DATA_DIR} -type f -exec sha256sum {{}} +")
    got = {}
    for line in out.splitlines():
        digest, _, path = line.partition("  ")
        got[path.strip()[len(DATA_DIR) + 1:]] = digest.strip()
    expected = {f["path"]: f["sha256"] for f in manifest["files"]}
    diff = sorted(k for k in set(got) | set(expected) if got.get(k) != expected.get(k))
    log(f"Volume {args.volume} : {len(got)} fichiers ; identiques au manifeste : "
        f"{sum(got.get(k) == v for k, v in expected.items())}/{len(expected)} ; écarts : {diff[:10]}")
    return 0 if not diff else 2


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    p = argparse.ArgumentParser(description="Sauvegarde vérifiée de la mémoire ChromaDB d'Atlas")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup", help="copier /data du conteneur, avec empreintes et manifeste")
    b.add_argument("--dest", default=str(DEFAULT_DEST))
    b.add_argument("--container", default=None, help=f"défaut : premier démarré parmi {PROD_CONTAINERS}")
    b.add_argument("--url", default="http://localhost:8001")
    v = sub.add_parser("verify", help="prouver la restauration dans un conteneur jetable")
    v.add_argument("backup")
    v.add_argument("--port", type=int, default=8101)
    v.add_argument("--live-url", default="http://localhost:8001")
    v.add_argument("--samples", type=int, default=25)
    v.add_argument("--target-url", default=None, help="vérifier un serveur déjà démarré au lieu d'un conteneur jetable")
    cv = sub.add_parser("check-volume", help="empreintes d'un volume nommé comparées au manifeste")
    cv.add_argument("backup")
    cv.add_argument("--volume", default=PROD_VOLUME)
    args = p.parse_args(argv)
    try:
        return {"backup": cmd_backup, "verify": cmd_verify, "check-volume": cmd_check_volume}[args.cmd](args)
    except Exception as e:
        log(f"ERREUR : {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
