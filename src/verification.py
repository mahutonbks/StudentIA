"""
Verification de l'ancrage documentaire d'une reponse generee.

Le prototype precedent traitait deux problemes constates par des
correctifs specifiques : une reponse entierement pre-ecrite pour le
scenario VLS-TS, et un remplacement de chaine pour une formulation
ambigue. Ces correctifs ne couvrent que les cas deja rencontres.

Ce module applique a la place un controle general : tout chiffre
present dans la reponse (montant, duree, pourcentage) doit apparaitre
dans le document source. Un modele de 3 milliards de parametres
invente surtout des chiffres et des delais ; c'est precisement ce que
ce controle attrape, y compris sur des questions jamais testees.

Le controle est volontairement conservateur : il signale, il ne
reecrit pas. C'est a l'appelant de decider quoi faire du signalement
(avertir l'utilisateur, ou s'abstenir).
"""

import re
import unicodedata


# Chiffres accompagnes d'une unite administrative pertinente.
MOTIF_MONTANT = re.compile(
    r"(\d[\d\s\u00a0.,]*)\s*(?:€|EUR|euros?)",
    re.IGNORECASE,
)

MOTIF_DUREE = re.compile(
    r"(\d+)\s*"
    r"(heures?|hours?|h\b"
    r"|mois|months?|jours?|days?|semaines?|weeks?"
    r"|ans?|années?|annees?|years?)"
    r"\b",
    re.IGNORECASE,
)

MOTIF_POURCENTAGE = re.compile(r"(\d[\d.,]*)\s*%")


def _normaliser_nombre(texte):
    """Ramene 877,5 / 877.5 / 1 000 a une forme comparable."""

    texte = unicodedata.normalize("NFKD", texte)
    texte = texte.replace("\u00a0", "").replace(" ", "")
    texte = texte.replace(",", ".")
    texte = texte.rstrip(".")

    try:
        valeur = float(texte)
    except ValueError:
        return texte

    if valeur == int(valeur):
        return str(int(valeur))

    return str(valeur)


def extraire_chiffres(texte):
    """Extrait les chiffres porteurs de sens administratif.

    Retourne un ensemble de couples (valeur normalisee, type).
    Les nombres sans unite sont ignores : ils sont rarement
    verifiables et generent trop de faux signalements.
    """

    trouves = set()

    for correspondance in MOTIF_MONTANT.finditer(texte):
        trouves.add((_normaliser_nombre(correspondance.group(1)), "montant"))

    for correspondance in MOTIF_DUREE.finditer(texte):
        unite = correspondance.group(2).lower()

        if unite.startswith(("mois", "month")):
            famille = "mois"
        elif unite.startswith(("heure", "hour")) or unite == "h":
            famille = "heures"
        elif unite.startswith(("jour", "day")):
            famille = "jours"
        elif unite.startswith(("semaine", "week")):
            famille = "semaines"
        else:
            famille = "annees"

        trouves.add((_normaliser_nombre(correspondance.group(1)), famille))

    for correspondance in MOTIF_POURCENTAGE.finditer(texte):
        trouves.add(
            (_normaliser_nombre(correspondance.group(1)), "pourcentage")
        )

    return trouves


def verifier_ancrage(reponse, document):
    """Compare les chiffres de la reponse a ceux du document.

    Retourne un dictionnaire :
        ancree            : True si aucun chiffre non justifie
        chiffres_reponse  : chiffres detectes dans la reponse
        chiffres_document : chiffres detectes dans le document
        non_justifies     : chiffres absents du document
    """

    chiffres_reponse = extraire_chiffres(reponse)
    chiffres_document = extraire_chiffres(document)

    non_justifies = chiffres_reponse - chiffres_document

    return {
        "ancree": not non_justifies,
        "chiffres_reponse": sorted(chiffres_reponse),
        "chiffres_document": sorted(chiffres_document),
        "non_justifies": sorted(non_justifies),
    }


def contient_lien(texte):
    """Le prompt interdit les URL : la reponse en contient-elle ?"""

    return bool(re.search(r"https?://", texte))


def proportion_francais(texte):
    """Estime grossierement si une reponse censee etre en anglais
    contient encore des phrases francaises.

    Heuristique simple basee sur des mots frequents exclusivement
    francais. Sert d'indicateur, pas de detecteur de langue fiable.
    """

    mots_francais = {
        "vous", "devez", "votre", "dans", "les", "une", "est", "avec",
        "pour", "sur", "pouvez", "doit", "cette", "aux", "leur",
    }

    mots = re.findall(r"[a-zA-Zàâçéèêëîïôûùüÿœ]+", texte.lower())

    if not mots:
        return 0.0

    return sum(1 for mot in mots if mot in mots_francais) / len(mots)


def controler_reponse(reponse, document, seuil_francais=0.08):
    """Controle complet d'une reponse generee.

    Retourne (avertissements, diagnostic). La liste d'avertissements
    est vide quand la reponse passe tous les controles.
    """

    diagnostic = verifier_ancrage(reponse, document)

    avertissements = []

    if diagnostic["non_justifies"]:
        details = ", ".join(
            f"{valeur} ({type_})"
            for valeur, type_ in diagnostic["non_justifies"]
        )
        avertissements.append(
            f"Chiffre(s) absent(s) du document source : {details}."
        )

    if contient_lien(reponse):
        avertissements.append("La reponse contient une URL non filtree.")

    part_francais = proportion_francais(reponse)
    diagnostic["proportion_francais"] = round(part_francais, 3)

    if part_francais > seuil_francais:
        avertissements.append(
            "La reponse semble contenir du francais alors que la "
            "sortie attendue est en anglais."
        )

    diagnostic["avertissements"] = avertissements

    return avertissements, diagnostic


if __name__ == "__main__":
    document_test = (
        "Vous devez demander votre titre de sejour au plus tot 4 mois "
        "et au plus tard 2 mois avant la fin de validite. Vous devez "
        "regler une taxe et un droit de timbre de 100 EUR."
    )

    exemples = {
        "reponse fidele": (
            "You must apply between 4 and 2 months before the expiry "
            "date, and pay a 100 EUR stamp duty."
        ),
        "reponse avec chiffre invente": (
            "You must apply 6 months before the expiry date and pay "
            "a 250 EUR fee."
        ),
    }

    for nom, reponse in exemples.items():
        avertissements, _ = controler_reponse(reponse, document_test)
        print(f"\n{nom} :")
        print("  OK" if not avertissements else f"  {avertissements}")
