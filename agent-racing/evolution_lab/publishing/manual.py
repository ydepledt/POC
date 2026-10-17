from __future__ import annotations

import json
import hashlib
import shutil
import time
from pathlib import Path

CONNECTORS = [
    {"id": "youtube", "name": "YouTube Shorts", "state": "unconfigured", "message": "Connexion non implémentée dans cette version locale. OAuth Google, autorisation d’envoi et éventuelle validation du projet API requis. Export manuel disponible.", "docs": "https://developers.google.com/youtube/v3/docs/videos"},
    {"id": "tiktok", "name": "TikTok", "state": "unconfigured", "message": "Connexion non implémentée dans cette version locale. Application Content Posting API, OAuth et permissions approuvées requis. Export manuel disponible.", "docs": "https://developers.tiktok.com/doc/content-posting-api-get-started/"},
    {"id": "instagram", "name": "Instagram Reels", "state": "unconfigured", "message": "Connexion non implémentée dans cette version locale. Application Meta et compte professionnel éligible, authentification et permissions requis. Export manuel disponible.", "docs": "https://developers.facebook.com/docs/instagram-platform/content-publishing/"},
]


def export_bundle(run_dir: Path, destination: str) -> dict:
    """Copy a reviewable bundle only to an explicitly selected local directory."""
    base = Path(destination).expanduser()
    if not destination.strip() or not base.is_absolute():
        raise ValueError("Choisissez le chemin absolu d’un dossier d’export.")
    if str(base).startswith("\\\\"):
        raise ValueError("Utilisez un dossier local, pas un partage réseau.")
    run_dir = run_dir.resolve()
    base = base.resolve()
    # Prevent accidentally copying output recursively into its own provenance directory.
    if base == run_dir or run_dir in base.parents:
        raise ValueError("Le dossier d’export doit être extérieur à cette simulation.")
    if not (run_dir / "video.mp4").is_file():
        raise ValueError("Aucune vidéo finalisée à exporter.")
    digest = hashlib.sha256()
    with (run_dir / "video.mp4").open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    revision = digest.hexdigest()[:10]
    target = base / f"evolution-lab-{run_dir.name}-{revision}"
    if target.is_symlink():
        raise ValueError("Le dossier d’export est un lien symbolique : export refusé.")
    if target.exists() and not target.is_dir():
        raise ValueError("Le chemin d’export existe et n’est pas un dossier.")
    target.mkdir(parents=True, exist_ok=True)
    names = ["video.mp4", "thumbnail.png", "publication.json", "video_metadata.json", "metrics.json", "summary.json", "config.json", "track.json"]
    copied, skipped = [], []
    for name in names:
        source = run_dir / name
        if source.is_file():
            if source.is_symlink():
                raise ValueError("Un fichier source est un lien symbolique : export refusé.")
            output = target / name
            # Avoid overwriting files the user may have edited in a previous export.
            if output.exists():
                if output.is_symlink():
                    raise ValueError("Le dossier contient un lien symbolique.")
                skipped.append(name)
                continue
            shutil.copy2(source, output)
            copied.append(name)
    receipt = {"destination": str(target), "copied": copied, "skipped": skipped, "revision": revision,
               "message": "Les fichiers déjà présents ont été conservés." if skipped else "Dossier exporté.",
               "state": "manual_export", "exported_at": time.time(), "published": False}
    (run_dir / "export_receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt
