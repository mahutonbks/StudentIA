"""
Profil de l'etudiant et regles qui en decoulent.

Trois regles metier, appliquees avant la generation :

1. Ressortissant UE/EEE/Suisse : les passages de categorie
   "titre_sejour" sont exclus du contexte (pas de titre de sejour
   requis pour etudier en France).

2. Ressortissant algerien : un drapeau est ajoute au contexte pour
   interdire de presenter la carte pluriannuelle comme accessible
   (l'accord franco-algerien de 1968 prevoit un regime distinct).

3. Pays inconnu et question sur le titre de sejour : on demande le
   pays avant de chercher, plutot que de repondre a cote.
"""

import corpus
from corpus import normaliser
from recherche import contient_mot


ZONE_UE = "UE"
ZONE_HORS_UE = "HORS_UE"

CATEGORIE_TITRE_SEJOUR = "titre_sejour"

DRAPEAU_ALGERIEN = "carte_pluriannuelle_exclue"

# Formes normalisees (minuscules, sans accents).
PAYS_ALGERIE = {"algerie", "algerien", "algerienne"}

# UE + EEE + Suisse, noms de pays et gentiles courants, normalises.
PAYS_UE = {
    "allemagne", "allemand", "allemande", "autriche", "autrichien",
    "autrichienne", "belgique", "belge", "bulgarie", "bulgare",
    "chypre", "chypriote", "croatie", "croate", "danemark", "danois",
    "danoise", "espagne", "espagnol", "espagnole", "estonie", "estonien",
    "estonienne", "finlande", "finlandais", "finlandaise", "france",
    "francais", "francaise", "grece", "grec", "grecque", "hongrie",
    "hongrois", "hongroise", "irlande", "irlandais", "irlandaise",
    "italie", "italien", "italienne", "lettonie", "letton", "lettone",
    "lituanie", "lituanien", "lituanienne", "luxembourg",
    "luxembourgeois", "luxembourgeoise", "malte", "maltais", "maltaise",
    "pays-bas", "pays bas", "neerlandais", "neerlandaise", "hollandais",
    "hollandaise", "pologne", "polonais", "polonaise", "portugal",
    "portugais", "portugaise", "republique tcheque", "tchequie",
    "tcheque", "roumanie", "roumain", "roumaine", "slovaquie",
    "slovaque", "slovenie", "slovene", "suede", "suedois", "suedoise",
    # EEE hors UE
    "islande", "islandais", "islandaise", "liechtenstein",
    "norvege", "norvegien", "norvegienne",
    # Suisse
    "suisse",
}

# Expressions signalant une question sur le titre de sejour, en plus
# des mots-cles des documents de categorie titre_sejour du corpus.
EXPRESSIONS_TITRE_SEJOUR = [
    "titre de sejour", "carte de sejour", "residence permit",
    "vls-ts", "vlsts", "visa", "prefecture", "anef", "pluriannuel",
]


def _pays_normalise(profil):
    return normaliser((profil or {}).get("pays_origine") or "").strip()


def deduire_zone(pays_origine):
    """UE ou HORS_UE a partir du pays saisi, None si inconnu."""

    pays = normaliser(pays_origine or "").strip()

    if not pays:
        return None

    return ZONE_UE if pays in PAYS_UE else ZONE_HORS_UE


def completer(profil):
    """Normalise un profil et deduit la zone si elle manque."""

    profil = {cle: valeur for cle, valeur in (profil or {}).items() if valeur}

    if profil.get("zone"):
        profil["zone"] = str(profil["zone"]).upper()
    elif profil.get("pays_origine"):
        profil["zone"] = deduire_zone(profil["pays_origine"])

    return profil


def est_ue(profil):
    return (profil or {}).get("zone") == ZONE_UE


def est_algerien(profil):
    return _pays_normalise(profil) in PAYS_ALGERIE


def categories_exclues(profil):
    return {CATEGORIE_TITRE_SEJOUR} if est_ue(profil) else set()


def drapeaux(profil):
    return [DRAPEAU_ALGERIEN] if est_algerien(profil) else []


_MOTS_CLES_TITRE_SEJOUR = None


def _mots_cles_titre_sejour():
    global _MOTS_CLES_TITRE_SEJOUR

    if _MOTS_CLES_TITRE_SEJOUR is None:
        mots = list(EXPRESSIONS_TITRE_SEJOUR)

        for document in corpus.charger_documents():
            if normaliser(document.categorie) == CATEGORIE_TITRE_SEJOUR:
                mots.extend(document.mots_cles)

        _MOTS_CLES_TITRE_SEJOUR = [
            normaliser(mot) for mot in mots if normaliser(mot).strip()
        ]

    return _MOTS_CLES_TITRE_SEJOUR


def porte_sur_titre_sejour(question):
    """Detection lexicale, sans appel au modele d'embedding."""

    question_normalisee = normaliser(question)

    return any(
        contient_mot(question_normalisee, mot)
        for mot in _mots_cles_titre_sejour()
    )


def clarification_necessaire(question, profil):
    """Champs a demander avant de chercher, liste vide sinon."""

    if not _pays_normalise(profil) and porte_sur_titre_sejour(question):
        return ["pays_origine"]

    return []


MESSAGE_CLARIFICATION = (
    "Pour te répondre précisément sur le titre de séjour, j'ai besoin "
    "de connaître ton pays d'origine (nationalité) : les règles ne sont "
    "pas les mêmes selon la nationalité."
)


def decrire(profil):
    """Profil lisible, insere dans le message envoye au modele."""

    profil = profil or {}

    zone = {
        ZONE_UE: "ressortissant UE/EEE/Suisse",
        ZONE_HORS_UE: "ressortissant hors UE/EEE/Suisse",
    }.get(profil.get("zone"), "non précisée")

    return (
        f"Pays d'origine : {profil.get('pays_origine') or 'non précisé'}\n"
        f"Zone : {zone}"
    )
