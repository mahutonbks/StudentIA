"""
Cache d'embeddings persistant sur disque.

Le cache precedent vivait uniquement en memoire : chaque redemarrage du
processus (et `--reload` d'uvicorn en redemarre souvent) obligeait a
recalculer tous les embeddings des documents.

Ici, chaque vecteur est ecrit dans .cache/embeddings/<empreinte>.json.
L'empreinte est un hash du texte ET du nom du modele : modifier un
document ou changer de modele d'embedding invalide automatiquement
l'entree, sans manipulation manuelle.
"""

import hashlib
import json
import logging

import config


logger = logging.getLogger(__name__)

DOSSIER_CACHE = config.DOSSIER_CACHE / "embeddings"

_MEMOIRE = {}


def _empreinte(texte, modele):
    donnees = f"{modele}\u0000{texte}".encode("utf-8")
    return hashlib.sha256(donnees).hexdigest()


def _chemin(empreinte):
    return DOSSIER_CACHE / f"{empreinte}.json"


def lire(texte, modele):
    """Retourne le vecteur en cache, ou None."""

    empreinte = _empreinte(texte, modele)

    if empreinte in _MEMOIRE:
        return _MEMOIRE[empreinte]

    chemin = _chemin(empreinte)

    if not chemin.exists():
        return None

    try:
        vecteur = json.loads(chemin.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Un fichier de cache corrompu ne doit jamais bloquer l'appli :
        # on l'ignore, il sera reecrit au prochain calcul.
        logger.warning("Entree de cache illisible ignoree : %s", chemin.name)
        return None

    _MEMOIRE[empreinte] = vecteur

    return vecteur


def ecrire(texte, modele, vecteur):
    """Enregistre un vecteur en memoire et sur disque."""

    empreinte = _empreinte(texte, modele)
    _MEMOIRE[empreinte] = vecteur

    try:
        DOSSIER_CACHE.mkdir(parents=True, exist_ok=True)
        _chemin(empreinte).write_text(
            json.dumps(vecteur),
            encoding="utf-8",
        )
    except OSError as erreur:
        # Disque plein ou droits insuffisants : le cache memoire suffit.
        logger.warning("Ecriture du cache impossible : %s", erreur)


def statistiques():
    fichiers = (
        list(DOSSIER_CACHE.glob("*.json"))
        if DOSSIER_CACHE.exists()
        else []
    )

    return {
        "entrees_memoire": len(_MEMOIRE),
        "entrees_disque": len(fichiers),
        "dossier": str(DOSSIER_CACHE),
    }


def vider():
    """Supprime le cache disque. Utile apres un changement de modele."""

    _MEMOIRE.clear()

    if not DOSSIER_CACHE.exists():
        return 0

    supprimes = 0

    for fichier in DOSSIER_CACHE.glob("*.json"):
        fichier.unlink()
        supprimes += 1

    return supprimes
