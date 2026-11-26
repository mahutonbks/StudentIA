"""
Recherche hybride semantique + lexicale.

Changements par rapport a la version precedente :

1. CORRECTION D'UN BUG : la constante SEUIL_SEMANTIQUE_SANS_LEXICAL
   etait definie mais jamais utilisee. L'acceptation reposait donc
   uniquement sur la presence d'un mot-cle ecrit a la main, ce qui
   faisait rejeter toute reformulation valide n'employant aucun de
   ces mots. Le seuil est maintenant reellement applique.

2. La recherche porte sur des passages (corpus.Passage) et non plus
   sur des fichiers entiers.

3. Les mots-cles viennent des metadonnees du document, plus d'un
   dictionnaire code en dur.

4. La fonction d'embedding est injectable (definir_fonction_embedding),
   ce qui permet de tester toute la logique de classement sans Ollama.

5. Les print() de debogage sont remplaces par du logging.
"""

import json
import logging
import math
import re
import urllib.error
import urllib.request

import cache_embeddings
import config
from corpus import charger_passages, normaliser


logger = logging.getLogger(__name__)

_PASSAGES = None
_EMBEDDINGS = {}


class ErreurOllama(RuntimeError):
    """Ollama est injoignable ou a renvoye une reponse inattendue."""


# --- Embeddings ----------------------------------------------------------

def embedding_ollama(texte):
    """Appelle le modele d'embedding via Ollama."""

    donnees = {
        "model": config.MODELE_EMBEDDING,
        "input": texte,
    }

    requete = urllib.request.Request(
        config.URL_EMBEDDING,
        data=json.dumps(donnees).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            requete,
            timeout=config.TIMEOUT_EMBEDDING,
        ) as reponse:
            resultat = json.loads(reponse.read().decode("utf-8"))

    except urllib.error.URLError as erreur:
        raise ErreurOllama(
            f"Impossible de joindre Ollama sur {config.OLLAMA_HOST} "
            f"({erreur}). Verifiez qu'Ollama tourne et que "
            f"OLLAMA_HOST est correct."
        ) from erreur

    try:
        return resultat["embeddings"][0]
    except (KeyError, IndexError) as erreur:
        raise ErreurOllama(
            "Reponse d'embedding inattendue. Le modele "
            f"{config.MODELE_EMBEDDING} est-il bien installe "
            "(ollama pull) ?"
        ) from erreur


_fonction_embedding = embedding_ollama


def definir_fonction_embedding(fonction):
    """Remplace la source des embeddings.

    Utilise par les tests hors ligne pour injecter des vecteurs
    deterministes a la place d'un appel reseau.
    """

    global _fonction_embedding

    _fonction_embedding = fonction

    reinitialiser()


def creer_embedding(texte):
    """Retourne l'embedding d'un texte, via le cache si possible."""

    modele = config.MODELE_EMBEDDING

    vecteur = cache_embeddings.lire(texte, modele)

    if vecteur is not None:
        return vecteur

    vecteur = _fonction_embedding(texte)

    cache_embeddings.ecrire(texte, modele, vecteur)

    return vecteur


# --- Scores --------------------------------------------------------------

def similarite_cosinus(vecteur_a, vecteur_b):
    if len(vecteur_a) != len(vecteur_b):
        return 0.0

    produit = sum(a * b for a, b in zip(vecteur_a, vecteur_b))

    norme_a = math.sqrt(sum(a * a for a in vecteur_a))
    norme_b = math.sqrt(sum(b * b for b in vecteur_b))

    if norme_a == 0 or norme_b == 0:
        return 0.0

    return produit / (norme_a * norme_b)


def contient_mot(texte, mot):
    """Le mot-cle apparait-il comme mot entier (pluriel en s/x admis) ?

    Une simple recherche de sous-chaine faisait correspondre "work" a
    "paperwork", "rent" a "parents" et "bourse" a "rembourse", et
    envoyait la question vers le mauvais document.
    """

    motif = r"(?<![a-z0-9])" + re.escape(mot) + r"[sx]?(?![a-z0-9])"
    return re.search(motif, texte) is not None


def calculer_score_lexical(question, mots_cles):
    """Score lexical base sur les mots-cles du document.

    Un mot-cle compose ("residence permit") vaut davantage qu'un mot
    isole : sa presence est un signal bien plus fiable du sujet.
    """

    if not mots_cles:
        return 0.0

    question_normalisee = normaliser(question)

    points = 0.0

    for mot in mots_cles:
        mot_normalise = normaliser(mot)

        if mot_normalise and contient_mot(question_normalisee, mot_normalise):
            points += 1.5 if " " in mot_normalise else 1.0

    if points == 0:
        return 0.0

    # Sature a 1.0 : au-dela de deux correspondances, la certitude
    # lexicale n'augmente plus vraiment.
    return min(1.0, 0.6 + 0.2 * points)


# --- Index ---------------------------------------------------------------

def reinitialiser():
    """Force le rechargement du corpus et des embeddings en memoire."""

    global _PASSAGES

    _PASSAGES = None
    _EMBEDDINGS.clear()


def preparer_index(forcer=False):
    """Charge les passages et calcule leurs embeddings (une seule fois)."""

    global _PASSAGES

    if forcer:
        reinitialiser()

    if _PASSAGES is None:
        _PASSAGES = charger_passages()
        logger.info("Corpus charge : %d passage(s).", len(_PASSAGES))

    for passage in _PASSAGES:
        if passage.identifiant not in _EMBEDDINGS:
            _EMBEDDINGS[passage.identifiant] = creer_embedding(
                passage.texte_embedding
            )

    return _PASSAGES


def rechercher_passages(question):
    """Classe tous les passages du corpus pour une question donnee."""

    passages = preparer_index()

    if not passages:
        return []

    embedding_question = creer_embedding(question)

    resultats = []

    for passage in passages:
        # Un vecteur de dimension differente (cache pollue, changement
        # de modele sous le meme nom) donnerait une similarite nulle
        # sans aucun message, donc une abstention systematique. On le
        # recalcule sans passer par le cache et on corrige l'entree.
        if len(_EMBEDDINGS[passage.identifiant]) != len(embedding_question):
            logger.warning(
                "Embedding de %s incoherent (dimension %d au lieu de %d) : "
                "recalcul.",
                passage.identifiant,
                len(_EMBEDDINGS[passage.identifiant]),
                len(embedding_question),
            )
            vecteur = _fonction_embedding(passage.texte_embedding)
            cache_embeddings.ecrire(
                passage.texte_embedding, config.MODELE_EMBEDDING, vecteur
            )
            _EMBEDDINGS[passage.identifiant] = vecteur

        score_semantique = similarite_cosinus(
            embedding_question,
            _EMBEDDINGS[passage.identifiant],
        )

        score_lexical = calculer_score_lexical(question, passage.mots_cles)

        score_final = (
            config.POIDS_SEMANTIQUE * score_semantique
            + config.POIDS_LEXICAL * score_lexical
        )

        resultats.append(
            {
                "passage": passage,
                "nom": passage.nom_document,
                "titre": passage.titre,
                "source": passage.source,
                "texte": passage.texte,
                "score_semantique": score_semantique,
                "score_lexical": score_lexical,
                "score": score_final,
            }
        )

        logger.debug(
            "%s - semantique %.4f - lexical %.2f - final %.4f",
            passage.identifiant,
            score_semantique,
            score_lexical,
            score_final,
        )

    resultats.sort(key=lambda resultat: resultat["score"], reverse=True)

    return resultats


# --- Acceptation / abstention -------------------------------------------

def est_pertinent(resultat):
    """Decide si un passage justifie une reponse.

    La decision porte sur la similarite semantique seule, avec un seuil
    different selon qu'un mot-cle est present ou non :

    - mot-cle present : seuil bas, qui sert uniquement a bloquer un
      mot-cle trompeur apparaissant dans une question sans rapport ;
    - aucun mot-cle : seuil haut, qui permet malgre tout de repondre a
      une reformulation valide non prevue par les mots-cles.

    Le score final pondere continue de servir au classement, mais pas a
    l'acceptation : c'est un melange de deux echelles differentes,
    difficile a interpreter et donc a calibrer.
    """

    if resultat["score_lexical"] > 0:
        return (
            resultat["score_semantique"]
            >= config.SEUIL_SEMANTIQUE_AVEC_LEXICAL
        )

    return (
        resultat["score_semantique"]
        >= config.SEUIL_SEMANTIQUE_SANS_LEXICAL
    )


def rechercher_document(question, categories_exclues=None):
    """Retourne le meilleur passage retenu, ou None (abstention).

    Le format de retour reste compatible avec l'ancienne version
    (cles nom, titre, contenu, source, scores) pour ne rien casser
    dans assistant.py, api.py et les tests existants.

    categories_exclues : categories de documents a ignorer (ex.
    "titre_sejour" pour un ressortissant UE). Le filtrage a lieu avant
    la selection : un passage exclu ne peut ni etre retenu, ni bloquer
    le passage suivant.
    """

    resultats = rechercher_passages(question)

    if categories_exclues:
        exclues = {normaliser(categorie) for categorie in categories_exclues}
        resultats = [
            resultat
            for resultat in resultats
            if normaliser(resultat["passage"].categorie) not in exclues
        ]

    if not resultats:
        return None

    # On parcourt les candidats dans l'ordre et on retient le premier
    # qui passe les criteres. S'abstenir parce que le passage classe
    # premier echoue de peu, alors que le second est clairement
    # acceptable, serait inutilement restrictif : les scores sont
    # souvent tres proches.
    meilleur = next(
        (
            resultat
            for resultat in resultats
            if est_pertinent(resultat)
        ),
        None,
    )

    if meilleur is None:
        tete = resultats[0]
        logger.info(
            "Abstention : meilleur candidat %s (semantique %.4f, "
            "lexical %.2f) sous les criteres de pertinence.",
            tete["nom"],
            tete["score_semantique"],
            tete["score_lexical"],
        )
        return None

    # Contexte complementaire : un second passage n'est ajoute que s'il
    # est proche en score et apporte un autre document.
    passages_retenus = [meilleur]

    for resultat in resultats[1:]:
        if len(passages_retenus) >= config.NOMBRE_PASSAGES:
            break

        ecart = meilleur["score"] - resultat["score"]

        if ecart > config.ECART_MAX_SECOND_PASSAGE:
            break

        if not est_pertinent(resultat):
            continue

        if resultat["nom"] == meilleur["nom"]:
            continue

        passages_retenus.append(resultat)

    contenu = "\n\n---\n\n".join(
        resultat["texte"] for resultat in passages_retenus
    )

    return {
        "nom": meilleur["nom"],
        "titre": meilleur["titre"],
        "contenu": contenu,
        "source": meilleur["source"],
        "score": meilleur["score"],
        "score_semantique": meilleur["score_semantique"],
        "score_lexical": meilleur["score_lexical"],
        "documents_utilises": [
            resultat["nom"] for resultat in passages_retenus
        ],
        "verifie_le": meilleur["passage"].verifie_le,
        "passages": [resultat["passage"] for resultat in passages_retenus],
    }


if __name__ == "__main__":
    logging.basicConfig(level=config.NIVEAU_LOG)

    question = input("Pose ta question : ").strip()

    if not question:
        print("Veuillez saisir une question.")

    else:
        try:
            resultat = rechercher_document(question)

        except ErreurOllama as erreur:
            print(f"\n{erreur}")
            raise SystemExit(1)

        if resultat is None:
            print("\nAucun document pertinent trouve.")

        else:
            print("\n--- DOCUMENT RETENU ---")
            print("\nDocument :", resultat["nom"])
            print(
                "Score semantique :",
                f"{resultat['score_semantique']:.4f}",
            )
            print("Score lexical :", f"{resultat['score_lexical']:.2f}")
            print("Score final :", f"{resultat['score']:.4f}")
            print("\nExtrait :")
            print(resultat["contenu"])
            print("\nSource :")
            print(resultat["source"])
