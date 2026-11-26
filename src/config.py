"""
Configuration centrale du projet.

Tout ce qui dependait d'une valeur ecrite en dur dans le code est
regroupe ici et surchargeable par variable d'environnement. Cela
permet de lancer le projet sur la machine qui heberge les modeles
sans modifier une seule ligne de code.

Exemple (PowerShell) :

    $env:OLLAMA_HOST = "http://192.168.1.42:11434"
    $env:STUDENTIA_CORS_ORIGINS = "http://127.0.0.1:5500,http://192.168.1.42:5500"
    python -m uvicorn api:app --app-dir src
"""

import os
from pathlib import Path


def _env_texte(nom, defaut):
    valeur = os.environ.get(nom, "").strip()
    return valeur if valeur else defaut


def _env_nombre(nom, defaut):
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        return defaut
    try:
        return float(valeur)
    except ValueError:
        return defaut


def _env_booleen(nom, defaut):
    valeur = os.environ.get(nom, "").strip().lower()
    if not valeur:
        return defaut
    return valeur in {"1", "true", "yes", "oui", "on"}


# --- Chemins -------------------------------------------------------------

DOSSIER_PROJET = Path(__file__).resolve().parent.parent
DOSSIER_DATA = DOSSIER_PROJET / "data"
DOSSIER_CACHE = DOSSIER_PROJET / ".cache"


# --- Ollama --------------------------------------------------------------

OLLAMA_HOST = _env_texte("OLLAMA_HOST", "http://localhost:11434")

URL_EMBEDDING = f"{OLLAMA_HOST}/api/embed"
URL_GENERATION = f"{OLLAMA_HOST}/api/generate"
URL_CHAT = f"{OLLAMA_HOST}/api/chat"
URL_TAGS = f"{OLLAMA_HOST}/api/tags"

MODELE_EMBEDDING = _env_texte("STUDENTIA_MODELE_EMBEDDING", "nomic-embed-text")
MODELE_GENERATION = _env_texte("STUDENTIA_MODELE_GENERATION", "qwen2.5:3b")

TIMEOUT_EMBEDDING = int(_env_nombre("STUDENTIA_TIMEOUT_EMBEDDING", 120))
TIMEOUT_GENERATION = int(_env_nombre("STUDENTIA_TIMEOUT_GENERATION", 300))


# --- Recherche hybride ---------------------------------------------------

POIDS_SEMANTIQUE = _env_nombre("STUDENTIA_POIDS_SEMANTIQUE", 0.85)
POIDS_LEXICAL = _env_nombre("STUDENTIA_POIDS_LEXICAL", 0.15)

# --- Seuils d'acceptation ------------------------------------------------
#
# Le score final (moyenne ponderee) sert a CLASSER les passages. Il ne
# sert pas a decider d'accepter ou de s'abstenir : melanger deux
# signaux d'echelles differentes donne un nombre difficile a
# interpreter et donc a calibrer. La decision repose sur la similarite
# semantique seule, qui est une valeur lisible (cosinus).
#
# Passage AVEC mot-cle : garde-fou bas. Il n'existe que pour bloquer le
# cas "mot-cle trompeur dans une question sans rapport" (limitation
# identifiee dans le README precedent).
SEUIL_SEMANTIQUE_AVEC_LEXICAL = _env_nombre(
    "STUDENTIA_SEUIL_AVEC_LEXICAL", 0.35
)

# Passage SANS mot-cle : seuil haut. C'est ce qui permet de repondre a
# une reformulation valide qui n'emploie aucun mot-cle prevu.
#
# ATTENTION : ces deux valeurs par defaut sont prudentes et n'ont PAS
# ete calibrees sur les modeles reels. Lancez
# evaluation/calibrer_seuils.py sur la machine qui heberge Ollama.
SEUIL_SEMANTIQUE_SANS_LEXICAL = _env_nombre(
    "STUDENTIA_SEUIL_SANS_LEXICAL", 0.72
)

# Nombre de passages transmis au modele de generation.
NOMBRE_PASSAGES = int(_env_nombre("STUDENTIA_NOMBRE_PASSAGES", 2))

# Un second passage n'est ajoute au contexte que s'il vient d'un autre
# document ET que son score reste proche du meilleur.
ECART_MAX_SECOND_PASSAGE = _env_nombre("STUDENTIA_ECART_SECOND_PASSAGE", 0.08)


# --- Decoupage des documents --------------------------------------------

TAILLE_CHUNK_MOTS = int(_env_nombre("STUDENTIA_TAILLE_CHUNK", 120))
CHEVAUCHEMENT_MOTS = int(_env_nombre("STUDENTIA_CHEVAUCHEMENT", 25))


# --- Generation ----------------------------------------------------------

TEMPERATURE = _env_nombre("STUDENTIA_TEMPERATURE", 0)
NOMBRE_TOKENS_MAX = int(_env_nombre("STUDENTIA_NUM_PREDICT", 800))

# Fenetre de contexte demandee a Ollama. Le prompt systeme, les
# passages et l'historique de conversation doivent y tenir : la valeur
# par defaut d'Ollama (2048 ou 4096 selon la version) est trop juste.
TAILLE_CONTEXTE = int(_env_nombre("STUDENTIA_NUM_CTX", 8192))

# Reponses pre-ecrites pour certains scenarios de demonstration.
# Desactivees par defaut : elles court-circuitent le modele et
# masquent la qualite reelle du systeme. Voir docs/note_ai_researcher.md.
REPONSES_CONTROLEES_ACTIVES = _env_booleen(
    "STUDENTIA_REPONSES_CONTROLEES", False
)

# Reformulations appliquees apres generation. Palliatif documente :
# ce n'est pas un systeme de verification factuelle.
REFORMULATIONS = [
    (
        "at least 4 months and at most 2 months before",
        "between 4 and 2 months before",
    ),
]


# --- API -----------------------------------------------------------------

CORS_ORIGINS = [
    origine.strip()
    for origine in _env_texte(
        "STUDENTIA_CORS_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500",
    ).split(",")
    if origine.strip()
]

# Precharge les embeddings des documents au demarrage de l'API pour que
# la premiere question de la demonstration ne soit pas la plus lente.
PRECHARGER_AU_DEMARRAGE = _env_booleen("STUDENTIA_PRECHARGE", True)


# --- Sessions de conversation --------------------------------------------

# Duree de vie d'une session inactive, en secondes (30 minutes).
TTL_SESSION = int(_env_nombre("STUDENTIA_TTL_SESSION", 30 * 60))

# Garde-fou : nombre maximal de messages d'historique conserves par
# session. Au-dela, les plus anciens sont oublies pour que le prompt
# tienne dans TAILLE_CONTEXTE.
HISTORIQUE_MAX = int(_env_nombre("STUDENTIA_HISTORIQUE_MAX", 40))


# --- Journalisation ------------------------------------------------------

NIVEAU_LOG = _env_texte("STUDENTIA_LOG", "INFO").upper()
