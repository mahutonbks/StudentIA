"""
Sessions de conversation, en memoire, avec expiration.

Une session regroupe ce qu'il faut pour ne pas tout redemander a
chaque question : le profil de l'etudiant et l'historique des
echanges. Elle expire apres config.TTL_SESSION secondes d'inactivite.

Stockage volontairement en memoire : rien n'est ecrit sur disque, et
un redemarrage de l'API vide toutes les sessions. Le frontend envoie
l'historique courant a chaque question, ce qui permet de reconstruire
une session perdue.

Limite connue : le stockage n'est pas partage entre plusieurs
processus (uvicorn --workers N). Pour le prototype, un seul processus.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field

import config


ROLES_AUTORISES = {"user", "assistant"}


@dataclass
class Session:
    identifiant: str
    profil: dict = field(default_factory=dict)
    historique: list = field(default_factory=list)
    derniere_activite: float = field(default_factory=time.monotonic)

    def toucher(self):
        self.derniere_activite = time.monotonic()

    def expiree(self, maintenant=None):
        maintenant = time.monotonic() if maintenant is None else maintenant
        return maintenant - self.derniere_activite > config.TTL_SESSION

    def ajouter_message(self, role, contenu):
        if role not in ROLES_AUTORISES:
            raise ValueError(f"Role inconnu : {role}")

        self.historique.append({"role": role, "content": contenu})

        if config.HISTORIQUE_MAX > 0:
            del self.historique[: -config.HISTORIQUE_MAX]

    def remplacer_historique(self, messages):
        self.historique = []
        for message in messages:
            self.ajouter_message(message["role"], message["content"])

    def fusionner_profil(self, profil):
        """Met a jour le profil sans effacer les champs deja connus."""

        for cle, valeur in (profil or {}).items():
            if valeur not in (None, ""):
                self.profil[cle] = valeur

    def exporter(self):
        return {
            "session_id": self.identifiant,
            "profil": dict(self.profil),
            "historique": [dict(message) for message in self.historique],
        }


_SESSIONS = {}
_VERROU = threading.Lock()


def _purger(maintenant):
    for identifiant in [
        identifiant
        for identifiant, session in _SESSIONS.items()
        if session.expiree(maintenant)
    ]:
        del _SESSIONS[identifiant]


def creer():
    with _VERROU:
        _purger(time.monotonic())
        session = Session(identifiant=str(uuid.uuid4()))
        _SESSIONS[session.identifiant] = session
        return session


def obtenir(identifiant):
    """Retourne la session active, ou None si inconnue ou expiree."""

    if not identifiant:
        return None

    with _VERROU:
        _purger(time.monotonic())
        session = _SESSIONS.get(identifiant)

        if session is not None:
            session.toucher()

        return session


def obtenir_ou_creer(identifiant):
    """Session existante, sinon une nouvelle (avec un nouvel UUID).

    Un identifiant inconnu n'est jamais repris tel quel : le client ne
    choisit pas les identifiants de session.
    """

    return obtenir(identifiant) or creer()


def nombre_actives():
    with _VERROU:
        _purger(time.monotonic())
        return len(_SESSIONS)


def vider():
    """Supprime toutes les sessions (tests)."""

    with _VERROU:
        _SESSIONS.clear()
