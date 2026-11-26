"""
Tests de recherche necessitant Ollama et les deux modeles.

Le jeu precedent (11 questions) affichait 11/11. Ce resultat etait
flatteur pour une raison mecanique : chaque question de test contenait
au moins un des mots-cles ecrits a la main, et c'etait exactement le
critere d'acceptation. Le jeu testait donc surtout que la liste de
mots-cles couvrait les questions... ecrites a partir de cette liste.

Les 11 cas d'origine sont conserves pour pouvoir comparer, et sont
completes par trois familles de cas plus severes :

- REFORMULATION : question valide qui n'emploie aucun mot-cle prevu.
  C'est le cas que l'ancienne regle d'acceptation rejetait toujours.
- MOT-CLE TROMPEUR : question hors sujet contenant un mot-cle.
- SUJET VOISIN : question administrative plausible mais absente du
  corpus. L'abstention est la bonne reponse.
- CORPUS ELARGI : les trois sujets ajoutes au corpus (securite
  sociale, aide au logement CAF, travail pendant les etudes). Trois
  de ces questions attendaient une abstention dans la version
  precedente ; le corpus les couvre desormais.

Un resultat inferieur a 100 % sur ce jeu elargi est normal et plus
informatif qu'un 11/11 sur le jeu d'origine.

Lancement :
    python tests/test_recherche.py
"""

import sys
from pathlib import Path


DOSSIER_PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_PROJET / "src"))

from recherche import ErreurOllama, rechercher_document  # noqa: E402


TESTS = [
    # --- Jeu d'origine : francais -----------------------------------
    {
        "question": "Quand dois-je renouveler mon titre de séjour étudiant ?",
        "attendu": "renouvellement_etudiant.txt",
        "famille": "origine",
    },
    {
        "question": (
            "À quel moment dois-je refaire mes papiers étudiants "
            "avant qu'ils expirent ?"
        ),
        "attendu": "renouvellement_etudiant.txt",
        "famille": "origine",
    },
    {
        "question": (
            "De combien d'argent ai-je besoin chaque mois pour mon "
            "séjour étudiant ?"
        ),
        "attendu": "ressources_etudiant.txt",
        "famille": "origine",
    },
    {
        "question": (
            "Quelles ressources financières dois-je avoir en tant "
            "qu'étudiant étranger ?"
        ),
        "attendu": "ressources_etudiant.txt",
        "famille": "origine",
    },
    {
        "question": (
            "Comment valider mon VLS-TS étudiant après mon arrivée "
            "en France ?"
        ),
        "attendu": "validation_vls_ts.txt",
        "famille": "origine",
    },
    {
        "question": (
            "Je viens d'arriver en France avec mon visa étudiant, "
            "qu'est-ce que je dois faire maintenant ?"
        ),
        "attendu": "validation_vls_ts.txt",
        "famille": "origine",
    },
    {
        "question": "Comment obtenir un permis de conduire en France ?",
        "attendu": None,
        "famille": "origine",
    },

    # --- Jeu d'origine : anglais ------------------------------------
    {
        "question": "When should I renew my student residence permit?",
        "attendu": "renouvellement_etudiant.txt",
        "famille": "origine",
    },
    {
        "question": "How do I validate my student VLS-TS after arriving in France?",
        "attendu": "validation_vls_ts.txt",
        "famille": "origine",
    },
    {
        "question": (
            "What financial resources do I need as an international "
            "student in France?"
        ),
        "attendu": "ressources_etudiant.txt",
        "famille": "origine",
    },
    {
        "question": "How can I get a driving licence in France?",
        "attendu": None,
        "famille": "origine",
    },

    # --- Reformulations sans mot-cle prevu --------------------------
    {
        "question": (
            "Ma carte arrive bientôt à échéance, quelles sont les "
            "démarches à faire ?"
        ),
        "attendu": "renouvellement_etudiant.txt",
        "famille": "reformulation",
    },
    {
        "question": (
            "Combien dois-je prouver que je gagne pour être accepté "
            "comme étudiant ?"
        ),
        "attendu": "ressources_etudiant.txt",
        "famille": "reformulation",
    },
    {
        "question": (
            "My card runs out soon, what paperwork do I need to do?"
        ),
        "attendu": "renouvellement_etudiant.txt",
        "famille": "reformulation",
    },
    {
        "question": (
            "I landed in Paris last week to start my degree. What is "
            "the first official step I must complete?"
        ),
        "attendu": "validation_vls_ts.txt",
        "famille": "reformulation",
    },

    # --- Mots-cles trompeurs ----------------------------------------
    {
        "question": (
            "Je veux renouveler mon abonnement de salle de sport, "
            "comment faire ?"
        ),
        "attendu": None,
        "famille": "mot_cle_trompeur",
    },
    {
        "question": "How do I renew my Netflix subscription?",
        "attendu": None,
        "famille": "mot_cle_trompeur",
    },
    {
        "question": (
            "Quel budget par mois faut-il prévoir pour un voyage "
            "au Japon ?"
        ),
        "attendu": None,
        "famille": "mot_cle_trompeur",
    },

    # --- Sujets ajoutes au corpus -----------------------------------
    # Ces trois questions attendaient une abstention dans la version
    # precedente : les sujets n'etaient pas couverts. Ils le sont
    # maintenant, et la reponse attendue a change en consequence.
    {
        "question": "Comment m'inscrire à la sécurité sociale étudiante ?",
        "attendu": "securite_sociale_etudiant.txt",
        "famille": "corpus_elargi",
    },
    {
        "question": "How do I apply for CAF housing assistance?",
        "attendu": "logement_caf.txt",
        "famille": "corpus_elargi",
    },
    {
        "question": "Puis-je travailler pendant mes études avec un titre étudiant ?",
        "attendu": "travail_etudiant.txt",
        "famille": "corpus_elargi",
    },
    {
        "question": "Combien d'heures par an ai-je le droit de travailler ?",
        "attendu": "travail_etudiant.txt",
        "famille": "corpus_elargi",
    },
    {
        "question": "Ai-je droit aux APL si je ne suis pas boursier ?",
        "attendu": "logement_caf.txt",
        "famille": "corpus_elargi",
    },
    {
        "question": "Do I have to pay to register with French health insurance?",
        "attendu": "securite_sociale_etudiant.txt",
        "famille": "corpus_elargi",
    },

    # --- Reformulations sur les nouveaux sujets ---------------------
    {
        "question": (
            "Je suis tombé malade, comment mes frais de médecin "
            "seront-ils pris en charge ?"
        ),
        "attendu": "securite_sociale_etudiant.txt",
        "famille": "reformulation",
    },
    {
        "question": (
            "Mon employeur veut me faire signer un contrat, y a-t-il "
            "une limite à ne pas dépasser ?"
        ),
        "attendu": "travail_etudiant.txt",
        "famille": "reformulation",
    },

    # --- Anciens "sujets voisins", couverts depuis la version 2 ------
    # Ces trois questions attendaient une abstention ; les documents
    # compte_bancaire, logement_crous et impots_etudiant existent
    # maintenant. Les vrais sujets hors corpus sont plus bas.
    {
        "question": "Comment ouvrir un compte bancaire en France ?",
        "attendu": "compte_bancaire.txt",
        "famille": "corpus_elargi",
    },
    {
        "question": "How do I apply for a CROUS student room?",
        "attendu": "logement_crous.txt",
        "famille": "corpus_elargi",
    },
    {
        "question": "Dois-je déclarer mes impôts en tant qu'étudiant étranger ?",
        "attendu": "impots_etudiant.txt",
        "famille": "corpus_elargi",
    },
] + [
    {"question": question, "attendu": attendu, "famille": famille}
    for famille, attendu, question in [
        # --- Version 3 : couverture des 15 documents -----------------
        ("corpus_15", "validation_vls_ts.txt", "Combien coûte la validation de mon visa étudiant ?"),
        ("corpus_15", "validation_vls_ts.txt", "Dans quel délai dois-je valider mon VLS-TS ?"),
        ("corpus_15", "validation_vls_ts.txt", "Is there a fee to validate my long-stay student visa?"),
        ("reformulation", "validation_vls_ts.txt", "Avec mon visa long séjour étudiant, puis-je quitter l'espace Schengen et revenir ?"),
        ("corpus_15", "renouvellement_etudiant.txt", "Combien coûte le renouvellement de ma carte de séjour étudiant ?"),
        ("corpus_15", "renouvellement_etudiant.txt", "Que se passe-t-il si je dépose ma demande de renouvellement en retard ?"),
        ("corpus_15", "renouvellement_etudiant.txt", "What happens if I apply late for my residence permit renewal?"),
        ("reformulation", "renouvellement_etudiant.txt", "Ma carte n'est plus valable dans trois semaines, est-il trop tard pour la demande ?"),
        ("corpus_15", "carte_sejour_pluriannuelle.txt", "Quelles conditions pour obtenir la carte de séjour pluriannuelle étudiant ?"),
        ("corpus_15", "carte_sejour_pluriannuelle.txt", "Can I get a multi-year residence card as a student?"),
        ("reformulation", "carte_sejour_pluriannuelle.txt", "Puis-je obtenir un titre qui couvre toute la durée de ma licence ?"),
        ("reformulation", "carte_sejour_pluriannuelle.txt", "Je voudrais ne plus renouveler chaque année mon titre, c'est possible ?"),
        ("corpus_15", "etudiant_algerien.txt", "Je suis algérien, quel titre de séjour dois-je demander pour étudier ?"),
        ("corpus_15", "etudiant_algerien.txt", "What residence document does an Algerian student need in France?"),
        ("corpus_15", "etudiant_algerien.txt", "Combien de temps un étudiant algérien peut-il travailler pendant ses études ?"),
        ("corpus_15", "changement_statut_etudiant.txt", "Comment passer d'un titre étudiant à un titre salarié ?"),
        ("corpus_15", "changement_statut_etudiant.txt", "Can I stay in France after graduation to look for a job?"),
        ("reformulation", "changement_statut_etudiant.txt", "J'ai trouvé un CDI à la fin de mon master, que dois-je faire pour mon titre ?"),
        ("reformulation", "changement_statut_etudiant.txt", "Je finis mon diplôme et je veux créer mon entreprise en France, est-ce possible ?"),
        ("corpus_15", "sejour_etudiant_ue.txt", "Je suis espagnol, ai-je besoin d'un titre de séjour pour étudier en France ?"),
        ("corpus_15", "sejour_etudiant_ue.txt", "As an EU citizen, do I need a residence permit to study in France?"),
        ("reformulation", "sejour_etudiant_ue.txt", "Je viens d'Italie pour un an d'études, quelles conditions pour rester plus de trois mois ?"),
        ("corpus_15", "ressources_etudiant.txt", "Quel montant minimum par mois dois-je justifier pour mon titre étudiant ?"),
        ("corpus_15", "ressources_etudiant.txt", "How much money per month must I prove to get a student permit?"),
        ("reformulation", "ressources_etudiant.txt", "Une attestation de prise en charge par mes parents suffit-elle ?"),
        ("corpus_15", "securite_sociale_etudiant.txt", "Où m'inscrire pour obtenir un numéro de sécurité sociale ?"),
        ("corpus_15", "securite_sociale_etudiant.txt", "How do I get a French social security number as a non-EU student?"),
        ("reformulation", "securite_sociale_etudiant.txt", "Quels papiers faut-il pour m'affilier à l'assurance maladie en arrivant ?"),
        ("corpus_15", "ceam_sante_ue.txt", "Je suis allemand, ma carte européenne d'assurance maladie suffit-elle en France ?"),
        ("corpus_15", "ceam_sante_ue.txt", "Does my EHIC card cover doctor visits in France?"),
        ("reformulation", "ceam_sante_ue.txt", "Étudiant belge, qui rembourse mes soins si je vais chez le médecin à Lyon ?"),
        ("corpus_15", "logement_caf.txt", "Je suis non européen et non boursier, ai-je droit à l'aide au logement ?"),
        ("corpus_15", "logement_caf.txt", "Can I get housing benefit from the CAF without a scholarship?"),
        ("reformulation", "logement_caf.txt", "Puis-je recevoir une aide pour payer mon loyer en tant qu'étudiant étranger ?"),
        ("corpus_15", "logement_crous.txt", "Comment demander une chambre en résidence universitaire ?"),
        ("corpus_15", "logement_crous.txt", "Combien coûte un logement CROUS par mois ?"),
        ("reformulation", "logement_crous.txt", "On m'a attribué une chambre au CROUS, combien de temps ai-je pour accepter ?"),
        ("corpus_15", "bourse_crous.txt", "Comment savoir si j'ai droit à une bourse sur critères sociaux ?"),
        ("corpus_15", "bourse_crous.txt", "How much is the CROUS needs-based grant?"),
        ("reformulation", "bourse_crous.txt", "Les étudiants boursiers doivent-ils payer leurs frais d'inscription ?"),
        ("corpus_15", "impots_etudiant.txt", "Mon salaire de job étudiant est-il imposable ?"),
        ("corpus_15", "impots_etudiant.txt", "Do I need to file a tax return in France if I have no income?"),
        ("reformulation", "impots_etudiant.txt", "Dois-je rester rattaché au foyer fiscal de mes parents ou déclarer seul ?"),
        ("corpus_15", "compte_bancaire.txt", "La banque refuse de m'ouvrir un compte, que faire ?"),
        ("corpus_15", "compte_bancaire.txt", "Which documents do I need to open a French bank account?"),
        ("reformulation", "compte_bancaire.txt", "Puis-je avoir un RIB français sans justificatif de domicile ?"),
        ("corpus_15", "travail_etudiant.txt", "Ai-je besoin d'une autorisation de travail pour un job étudiant ?"),
        ("corpus_15", "travail_etudiant.txt", "Can I work more than 964 hours a year as a student?"),
        ("reformulation", "travail_etudiant.txt", "Combien de temps puis-je être employé à côté de mes cours ?"),
        # --- Sujets administratifs voisins, absents du corpus --------
        ("sujet_voisin", None, "Comment faire reconnaître mon diplôme étranger en France ?"),
        ("sujet_voisin", None, "Comment demander la nationalité française ?"),
        ("sujet_voisin", None, "Où acheter un abonnement de transport étudiant à Paris ?"),
        ("sujet_voisin", None, "How do I enrol my child in a French school?"),
        ("sujet_voisin", None, "Comment passer le DELF pour prouver mon niveau de français ?"),
        ("sujet_voisin", None, "Do I need home insurance for my student flat?"),
        ("sujet_voisin", None, "Comment échanger mon permis de conduire étranger ?"),
        # --- Mots-cles trompeurs -------------------------------------
        ("mot_cle_trompeur", None, "Comment renouveler mon passeport auprès de mon consulat ?"),
        ("mot_cle_trompeur", None, "Ma banque me propose une carte de crédit, est-ce intéressant ?"),
        ("mot_cle_trompeur", None, "Quelle est la meilleure mutuelle pour mon chat ?"),
        ("mot_cle_trompeur", None, "Comment valider mon semestre à l'université ?"),
        ("mot_cle_trompeur", None, "Is there a student discount at the cinema?"),
    ]
]


def executer_tests():
    print("\n=== TESTS DU RETRIEVAL RAG ===\n")

    resultats_par_famille = {}
    echecs = []
    nombre_correct = 0

    for numero, test in enumerate(TESTS, start=1):
        question = test["question"]
        attendu = test["attendu"]
        famille = test["famille"]

        print(f"\n--- Test {numero}/{len(TESTS)} [{famille}] ---")
        print("Question :", question)

        try:
            resultat = rechercher_document(question)
        except ErreurOllama as erreur:
            print(f"\n{erreur}")
            return False

        obtenu = resultat["nom"] if resultat else None

        reussi = obtenu == attendu

        if reussi:
            nombre_correct += 1
        else:
            gravite = (
                "GRAVE" if attendu is None or obtenu is not None else "manque"
            )
            echecs.append((famille, question, attendu, obtenu, gravite))

        compteur = resultats_par_famille.setdefault(
            famille, {"reussis": 0, "total": 0}
        )
        compteur["total"] += 1
        compteur["reussis"] += int(reussi)

        print("Attendu :", attendu)
        print("Obtenu  :", obtenu)

        if resultat:
            print(
                f"Scores  : semantique {resultat['score_semantique']:.4f} "
                f"| lexical {resultat['score_lexical']:.2f}"
            )

        print("Resultat :", "OK" if reussi else "ECHEC")

    total = len(TESTS)

    print("\n" + "=" * 46)
    print(f"Resultat global : {nombre_correct}/{total} "
          f"({100 * nombre_correct / total:.1f} %)")
    print("=" * 46)

    print("\nDetail par famille de cas :\n")

    for famille, compteur in resultats_par_famille.items():
        print(
            f"  {famille:<20} {compteur['reussis']}/{compteur['total']}"
        )

    if echecs:
        print("\nEchecs :\n")

        for famille, question, attendu, obtenu, gravite in echecs:
            print(f"  [{gravite}] ({famille}) {question}")
            print(f"           attendu {attendu} / obtenu {obtenu}")

        print(
            "\n  GRAVE = le systeme a repondu alors qu'il aurait du "
            "s'abstenir,\n  ou a choisi le mauvais document. C'est le "
            "type d'echec a corriger\n  en priorite : une mauvaise "
            "reponse sur une regle administrative\n  est pire qu'une "
            "absence de reponse."
        )

    print()

    return nombre_correct == total


if __name__ == "__main__":
    sys.exit(0 if executer_tests() else 1)
