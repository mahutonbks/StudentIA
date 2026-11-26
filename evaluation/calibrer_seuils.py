"""
Selection des parametres de recherche par balayage de grille.

A LANCER SUR LA MACHINE QUI HEBERGE OLLAMA.

Parametres balayes :
  - poids semantique (le poids lexical vaut 1 - poids) : il fixe le
    CLASSEMENT des passages ;
  - seuil semantique avec mot-cle et seuil sans mot-cle : ils fixent
    l'ACCEPTATION ou l'abstention.

Methode :

1. les similarites de chaque question contre chaque passage sont
   calculees une seule fois (un appel d'embedding par question) ;
2. le jeu de questions (tests/test_recherche.py) est coupe en deux
   parties fixes, par hachage de la question : calibration (~70 %)
   et test (~30 %) ;
3. toutes les combinaisons de la grille sont evaluees sur la partie
   calibration ; la meilleure est celle qui fait le moins de mauvaises
   selections, puis le plus de decisions correctes (mieux vaut
   s'abstenir que se tromper sur une regle administrative) ;
4. la combinaison retenue est evaluee UNE fois sur la partie test,
   jamais vue pendant la selection : c'est ce score-la qu'il faut
   citer, pas celui de calibration, toujours optimiste.

Les valeurs ne sont pas ecrites dans la configuration : le script
affiche les variables d'environnement a definir.

Usage :
    python evaluation/calibrer_seuils.py
"""

import hashlib
import sys
from pathlib import Path


DOSSIER_PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_PROJET / "src"))
sys.path.insert(0, str(DOSSIER_PROJET / "tests"))

import config  # noqa: E402
import recherche  # noqa: E402
from test_recherche import TESTS  # noqa: E402


GRILLE_POIDS_SEMANTIQUE = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.0]
GRILLE_AVEC_LEXICAL = [0.0, 0.15, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
GRILLE_SANS_LEXICAL = [0.55, 0.60, 0.65, 0.70, 0.72, 0.75, 0.80, 0.85]

PART_CALIBRATION = 0.7


def partie(question):
    """'calibration' ou 'test', stable d'une execution a l'autre.

    Le hachage evite qu'ajouter une question deplace les autres d'une
    partie a l'autre, ce que ferait un decoupage par position.
    """

    valeur = int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16)
    return "calibration" if valeur % 100 < PART_CALIBRATION * 100 else "test"


def collecter_scores():
    """Calcule une fois pour toutes les scores de chaque question."""

    mesures = []

    for numero, test in enumerate(TESTS, start=1):
        print(f"  [{numero}/{len(TESTS)}] {test['question'][:58]}...")

        resultats = recherche.rechercher_passages(test["question"])

        mesures.append(
            {
                "question": test["question"],
                "attendu": test["attendu"],
                "partie": partie(test["question"]),
                "candidats": [
                    {
                        "nom": resultat["nom"],
                        "semantique": resultat["score_semantique"],
                        "lexical": resultat["score_lexical"],
                    }
                    for resultat in resultats
                ],
            }
        )

    return mesures


def decider(candidats, poids, seuil_avec, seuil_sans):
    """Rejoue le classement puis la regle d'acceptation de recherche.py."""

    classes = sorted(
        candidats,
        key=lambda candidat: poids * candidat["semantique"]
        + (1 - poids) * candidat["lexical"],
        reverse=True,
    )

    for candidat in classes:
        seuil = seuil_avec if candidat["lexical"] > 0 else seuil_sans

        if candidat["semantique"] >= seuil:
            return candidat["nom"]

    return None


def evaluer(mesures, poids, seuil_avec, seuil_sans):
    bilan = {
        "poids": poids,
        "seuil_avec": seuil_avec,
        "seuil_sans": seuil_sans,
        "bonnes": 0,
        "mauvaises": 0,
        "abstentions_correctes": 0,
        "abstentions_a_tort": 0,
    }

    for mesure in mesures:
        obtenu = decider(mesure["candidats"], poids, seuil_avec, seuil_sans)
        attendu = mesure["attendu"]

        if obtenu == attendu:
            cle = "abstentions_correctes" if attendu is None else "bonnes"
        elif obtenu is None:
            cle = "abstentions_a_tort"
        else:
            # Le pire cas : une reponse confiante sur le mauvais
            # document, ou une reponse a une question hors sujet.
            cle = "mauvaises"

        bilan[cle] += 1

    bilan["correctes"] = bilan["bonnes"] + bilan["abstentions_correctes"]
    bilan["total"] = len(mesures)

    return bilan


def afficher_ligne(bilan):
    print(
        f"  {bilan['poids']:>5.2f} {bilan['seuil_avec']:>6.2f} "
        f"{bilan['seuil_sans']:>6.2f} {bilan['bonnes']:>7} "
        f"{bilan['mauvaises']:>10} {bilan['abstentions_correctes']:>8} "
        f"{bilan['abstentions_a_tort']:>10}   "
        f"{bilan['correctes']}/{bilan['total']}"
    )


def afficher_distribution(mesures):
    dans_corpus = [
        mesure["candidats"][0]["semantique"]
        for mesure in mesures
        if mesure["attendu"] is not None and mesure["candidats"]
    ]
    hors_corpus = [
        mesure["candidats"][0]["semantique"]
        for mesure in mesures
        if mesure["attendu"] is None and mesure["candidats"]
    ]

    print("\nMeilleure similarite semantique par question :\n")

    if dans_corpus:
        print(f"  dans le corpus : min {min(dans_corpus):.3f} "
              f"max {max(dans_corpus):.3f}")

    if hors_corpus:
        print(f"  hors corpus    : min {min(hors_corpus):.3f} "
              f"max {max(hors_corpus):.3f}")

    print("\n  Des plages qui se chevauchent signifient qu'aucun seuil")
    print("  ne separera parfaitement les deux cas.")


def main():
    print("\n=== SELECTION DES PARAMETRES DE RECHERCHE ===\n")
    print("Calcul des scores (un appel d'embedding par question)...\n")

    try:
        mesures = collecter_scores()
    except recherche.ErreurOllama as erreur:
        print(f"\n{erreur}")
        return 1

    calibration = [m for m in mesures if m["partie"] == "calibration"]
    test = [m for m in mesures if m["partie"] == "test"]

    print(f"\nDecoupage : {len(calibration)} questions de calibration, "
          f"{len(test)} questions de test.")

    afficher_distribution(calibration)

    bilans = [
        evaluer(calibration, poids, seuil_avec, seuil_sans)
        for poids in GRILLE_POIDS_SEMANTIQUE
        for seuil_avec in GRILLE_AVEC_LEXICAL
        for seuil_sans in GRILLE_SANS_LEXICAL
    ]

    # Priorite : aucune mauvaise reponse, puis maximum de decisions
    # correctes ; a egalite, les seuils les plus permissifs et le poids
    # le plus proche de la valeur actuelle.
    bilans.sort(
        key=lambda bilan: (
            bilan["mauvaises"],
            -bilan["correctes"],
            bilan["seuil_avec"],
            bilan["seuil_sans"],
            abs(bilan["poids"] - config.POIDS_SEMANTIQUE),
        )
    )

    entete = (
        f"  {'poids':>5} {'avec':>6} {'sans':>6} {'bonnes':>7} "
        f"{'mauvaises':>10} {'abst.ok':>8} {'abst.tort':>10}   correct"
    )

    print(f"\n\nMeilleures combinaisons sur la calibration "
          f"({len(bilans)} testees) :\n")
    print(entete)

    for bilan in bilans[:8]:
        afficher_ligne(bilan)

    meilleur = bilans[0]
    actuel = (
        config.POIDS_SEMANTIQUE,
        config.SEUIL_SEMANTIQUE_AVEC_LEXICAL,
        config.SEUIL_SEMANTIQUE_SANS_LEXICAL,
    )

    print("\n\nEvaluation sur la partie test (jamais vue pendant la "
          "selection) :\n")
    print(entete)
    afficher_ligne(evaluer(test, *actuel))
    print("  ^ valeurs actuelles")
    afficher_ligne(
        evaluer(
            test,
            meilleur["poids"],
            meilleur["seuil_avec"],
            meilleur["seuil_sans"],
        )
    )
    print("  ^ valeurs retenues")

    print("\n\nPour appliquer les valeurs retenues :\n")
    print(f"  STUDENTIA_POIDS_SEMANTIQUE   = {meilleur['poids']}")
    print(f"  STUDENTIA_POIDS_LEXICAL      = {round(1 - meilleur['poids'], 2)}")
    print(f"  STUDENTIA_SEUIL_AVEC_LEXICAL = {meilleur['seuil_avec']}")
    print(f"  STUDENTIA_SEUIL_SANS_LEXICAL = {meilleur['seuil_sans']}")

    print(
        "\nN'appliquez les valeurs retenues que si elles font mieux que "
        "les valeurs actuelles sur la partie test. Les questions ont ete "
        "ecrites par quelqu'un qui connait les mots-cles : un jeu "
        "independant reste necessaire.\n"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
