"""
API FastAPI de Studentia.

Version 3 :

1. Memoire conversationnelle : sessions en memoire (UUID, expiration
   apres 30 minutes d'inactivite). POST /nouvelle-session,
   GET /session/{session_id}.

2. Profil etudiant (pays, zone UE/HORS_UE) stocke en
   session et reutilise aux questions suivantes. Il pilote le
   filtrage du contexte (voir profil.py).

3. POST /question repond en flux SSE (text/event-stream). Evenements :

     session        {"session_id"}                 toujours en premier
     meta           {"source", "document", ...}    passages retenus
     token          {"texte"}                      un fragment genere
     clarification  {"message", "champs_manquants"}       terminal
     done           {"reponse", "abstention", ...}         terminal
     error          {"type", "message", ...}               terminal

   Le controle d'ancrage s'execute sur la reponse complete, apres le
   flux. En cas d'echec, l'evenement final est "error" (type
   "abstention_verification") avec le message d'abstention.

Versions precedentes : Ollama arrete -> message exploitable au lieu
d'une trace Python ; CORS configurable ; /health interroge reellement
Ollama ; embeddings du corpus precalcules au demarrage.

Lancement :
    PYTHONPATH=src uvicorn src.api:app --reload
"""

import json
import logging
import urllib.error
import urllib.request
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import assistant
import cache_embeddings
import config
import corpus
import profil as profils
import sessions
from assistant import ErreurGeneration
from recherche import ErreurOllama, preparer_index


logging.basicConfig(
    level=config.NIVEAU_LOG,
    format="%(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("studentia.api")


@asynccontextmanager
async def cycle_de_vie(app):
    problemes = corpus.valider_corpus()

    for probleme in problemes:
        logger.warning("Corpus : %s", probleme)

    for doute in corpus.points_a_verifier():
        logger.warning(
            "Corpus a verifier : %s - %s", doute["document"], doute["note"]
        )

    if config.PRECHARGER_AU_DEMARRAGE:
        try:
            passages = preparer_index()
            logger.info(
                "Index pret : %d passage(s), cache %s.",
                len(passages),
                cache_embeddings.statistiques(),
            )
        except ErreurOllama as erreur:
            # L'API demarre quand meme : elle signalera l'erreur tant
            # qu'Ollama n'est pas joignable.
            logger.error("Prechargement impossible : %s", erreur)

    yield


app = FastAPI(
    title="Studentia - AI Administrative Assistant",
    description="RAG prototype API for international students in France.",
    version="3.0.0",
    lifespan=cycle_de_vie,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# --- Modeles de requete --------------------------------------------------

class MessageHistorique(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ProfilEtudiant(BaseModel):
    pays_origine: Optional[str] = Field(default=None, max_length=80)
    zone: Optional[Literal["UE", "HORS_UE"]] = None


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    session_id: Optional[str] = Field(default=None, max_length=64)
    historique: Optional[list[MessageHistorique]] = Field(
        default=None, max_length=200
    )
    profil: Optional[ProfilEtudiant] = None


ENDPOINTS = {
    "GET /": "Accueil et version de l'API.",
    "GET /health": "Etat de l'API, d'Ollama, du corpus et des sessions.",
    "POST /nouvelle-session": (
        "Cree une session de conversation. Reponse : {session_id, "
        "expire_dans_secondes}."
    ),
    "GET /session/{session_id}": (
        "Profil et historique courants de la session (404 si inconnue "
        "ou expiree)."
    ),
    "POST /question": (
        "Corps : {question, session_id?, historique?: [{role, content}], "
        "profil?: {pays_origine, zone (UE|HORS_UE)}}. "
        "Reponse en flux SSE (text/event-stream) : evenements session, "
        "meta, token, puis un evenement terminal done | error | "
        "clarification."
    ),
}


def _modeles_installes():
    requete = urllib.request.Request(config.URL_TAGS, method="GET")

    with urllib.request.urlopen(requete, timeout=10) as reponse:
        donnees = json.loads(reponse.read().decode("utf-8"))

    return {modele.get("name", "") for modele in donnees.get("models", [])}


@app.get("/")
def accueil():
    return {
        "message": "Studentia AI Administrative Assistant API",
        "status": "ok",
        "version": app.version,
    }


@app.get("/health")
def health():
    """Verifie l'etat reel des dependances, pas seulement de l'API."""

    etat = {
        "api": "ok",
        "ollama_host": config.OLLAMA_HOST,
        "corpus": {
            "documents": len(corpus.charger_documents()),
            "problemes": corpus.valider_corpus(),
            "a_verifier": corpus.points_a_verifier(),
        },
        "cache": cache_embeddings.statistiques(),
        "sessions": {
            "actives": sessions.nombre_actives(),
            "ttl_secondes": config.TTL_SESSION,
        },
        "endpoints": ENDPOINTS,
    }

    try:
        installes = _modeles_installes()

        etat["ollama"] = "ok"
        etat["modeles"] = {
            config.MODELE_EMBEDDING: any(
                nom.startswith(config.MODELE_EMBEDDING) for nom in installes
            ),
            config.MODELE_GENERATION: any(
                nom.startswith(config.MODELE_GENERATION) for nom in installes
            ),
        }

        if not all(etat["modeles"].values()):
            etat["api"] = "degraded"
            etat["detail"] = (
                "Un modele requis est absent. Lancez 'ollama pull' "
                "pour le modele manquant."
            )

    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as erreur:
        etat["api"] = "degraded"
        etat["ollama"] = "injoignable"
        etat["detail"] = str(erreur)

    return etat


# --- Sessions ------------------------------------------------------------

@app.post("/nouvelle-session")
def nouvelle_session():
    session = sessions.creer()

    return {
        "session_id": session.identifiant,
        "expire_dans_secondes": config.TTL_SESSION,
    }


@app.get("/session/{session_id}")
def lire_session(session_id: str):
    session = sessions.obtenir(session_id)

    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Session inconnue ou expiree.",
        )

    return session.exporter()


# --- POST /question en flux SSE ------------------------------------------

def evenement(type_evenement, donnees):
    """Formate un evenement Server-Sent Events.

    Les donnees sont encodees en JSON : un token contenant un saut de
    ligne ne casse pas le format SSE.
    """

    return (
        f"event: {type_evenement}\n"
        f"data: {json.dumps(donnees, ensure_ascii=False)}\n\n"
    )


MESSAGE_OLLAMA_INDISPONIBLE = (
    "L'assistant ne parvient pas à joindre ses modèles de langage "
    "locaux. Vérifie qu'Ollama est lancé, puis réessaie."
)

MESSAGE_GENERATION_INDISPONIBLE = (
    "J'ai trouvé un document officiel pertinent, mais le modèle de "
    "réponse est indisponible. Consulte directement la source officielle."
)


def traiter_question(requete):
    """Generateur d'evenements SSE pour une question.

    Separe de la route pour etre testable sans serveur HTTP.
    """

    session = sessions.obtenir_ou_creer(requete.session_id)

    yield evenement("session", {"session_id": session.identifiant})

    if requete.profil is not None:
        session.fusionner_profil(
            profils.completer(requete.profil.model_dump())
        )

    # L'historique envoye par le client fait foi : il permet aussi de
    # reconstruire une session expiree ou perdue au redemarrage.
    if requete.historique:
        session.remplacer_historique(
            [message.model_dump() for message in requete.historique]
        )

    question = requete.question.strip()

    if not question:
        yield evenement(
            "error",
            {"type": "question_vide", "message": "Merci de saisir une question."},
        )
        return

    historique = list(session.historique)
    profil = dict(session.profil)

    try:
        etape = assistant.preparer(
            assistant.question_pour_recherche(question, historique),
            profil,
            precision_demandee=assistant.precision_deja_demandee(historique),
        )

    except ErreurOllama as erreur:
        logger.error("Recherche impossible : %s", erreur)
        yield evenement(
            "error",
            {
                "type": "ollama_indisponible",
                "message": MESSAGE_OLLAMA_INDISPONIBLE,
                "detail": str(erreur),
            },
        )
        return

    if etape["type"] == "clarification":
        session.ajouter_message("user", question)
        session.ajouter_message("assistant", etape["message"])

        yield evenement(
            "clarification",
            {
                "message": etape["message"],
                "champs_manquants": etape["champs_manquants"],
            },
        )
        return

    if etape["type"] == "abstention":
        session.ajouter_message("user", question)
        session.ajouter_message("assistant", etape["message"])

        yield evenement(
            "done",
            {
                "reponse": etape["message"],
                "abstention": True,
                "source": None,
                "document": None,
            },
        )
        return

    resultat = etape["resultat"]

    yield evenement(
        "meta",
        {
            "source": resultat["source"],
            "document": resultat["nom"],
            "documents_utilises": resultat.get("documents_utilises", []),
            "verifie_le": resultat.get("verifie_le"),
            "scores": {
                "semantique": round(resultat["score_semantique"], 4),
                "lexical": round(resultat["score_lexical"], 2),
                "final": round(resultat["score"], 4),
            },
        },
    )

    messages = assistant.construire_messages(
        question, etape["contexte"], historique, profil
    )

    morceaux = []

    try:
        for fragment in assistant.generer_flux(messages):
            morceaux.append(fragment)
            yield evenement("token", {"texte": fragment})

    except ErreurGeneration as erreur:
        logger.error("Generation impossible : %s", erreur)
        yield evenement(
            "error",
            {
                "type": "generation_indisponible",
                "message": MESSAGE_GENERATION_INDISPONIBLE,
                "source": resultat["source"],
                "detail": str(erreur),
            },
        )
        return

    texte, diagnostic = assistant.finaliser(
        "".join(morceaux), etape["contexte"]
    )

    # Une reponse ecartee par le controle d'ancrage n'entre pas dans
    # l'historique : c'est le message d'abstention qui y est conserve.
    session.ajouter_message("user", question)
    session.ajouter_message("assistant", texte)

    if diagnostic["origine"] == "abstention_verification":
        yield evenement(
            "error",
            {
                "type": "abstention_verification",
                "message": texte,
                "source": resultat["source"],
                "non_justifies": [
                    list(chiffre) for chiffre in diagnostic["non_justifies"]
                ],
            },
        )
        return

    yield evenement(
        "done",
        {
            "reponse": texte,
            "abstention": False,
            "source": resultat["source"],
            "document": resultat["nom"],
            "verifie_le": resultat.get("verifie_le"),
            "verification": {
                "origine": diagnostic["origine"],
                "avertissements": diagnostic.get("avertissements", []),
            },
        },
    )


@app.post("/question")
def poser_question(requete: QuestionRequest):
    return StreamingResponse(
        traiter_question(requete),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
