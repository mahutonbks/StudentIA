"""
Tests hors ligne : aucun appel a Ollama.

Les tests existants (tests/test_recherche.py) ont besoin des deux
modeles et ne peuvent donc tourner que sur la machine qui les heberge.
Ceux-ci verifient toute la logique qui ne depend pas des modeles :
lecture des metadonnees, decoupage, score lexical, regle d'abstention,
controle d'ancrage. Ils tournent sur n'importe quelle machine et en
integration continue.

Les embeddings sont remplaces par une fonction deterministe : les
vecteurs n'ont aucun sens semantique, mais ils permettent de verifier
que la mecanique de classement et d'abstention se comporte comme prevu.

Lancement :
    python tests/test_hors_ligne.py
"""

import hashlib
import math
import sys
from pathlib import Path


DOSSIER_PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_PROJET / "src"))

import cache_embeddings  # noqa: E402
import config  # noqa: E402
import corpus  # noqa: E402
import recherche  # noqa: E402
import verification  # noqa: E402
from assistant import generer_reponse  # noqa: E402


ECHECS = []


def verifier(condition, description):
    if condition:
        print(f"  OK    {description}")
    else:
        print(f"  ECHEC {description}")
        ECHECS.append(description)


def embedding_factice(texte):
    """Vecteur deterministe de dimension 32 derive du texte.

    Deux textes identiques donnent le meme vecteur ; deux textes
    differents donnent des vecteurs sans relation semantique. C'est
    suffisant pour tester la mecanique, pas la pertinence.
    """

    empreinte = hashlib.sha256(texte.encode("utf-8")).digest()

    vecteur = [
        (empreinte[indice % len(empreinte)] / 255.0) - 0.5
        for indice in range(32)
    ]

    norme = math.sqrt(sum(valeur * valeur for valeur in vecteur)) or 1.0

    return [valeur / norme for valeur in vecteur]


# --- Corpus --------------------------------------------------------------

def tester_corpus():
    print("\n[1] Lecture et validation du corpus")

    documents = corpus.charger_documents()

    verifier(len(documents) >= 6, "au moins six documents charges")

    verifier(
        all(document.titre for document in documents),
        "chaque document a un titre",
    )

    verifier(
        all(document.source.startswith("http") for document in documents),
        "chaque document a une source URL",
    )

    verifier(
        all(document.mots_cles for document in documents),
        "chaque document a des mots-cles dans ses metadonnees",
    )

    verifier(
        all(document.verifie_le for document in documents),
        "chaque document a une date de verification",
    )

    verifier(
        not corpus.valider_corpus(),
        "valider_corpus() ne remonte aucun probleme",
    )

    # Un doute marque doit rester visible sans faire echouer la
    # validation : ce n'est pas une erreur de saisie.
    doutes = corpus.points_a_verifier()

    verifier(
        all("note" in doute and doute["note"] for doute in doutes),
        "chaque point a verifier porte une note explicative",
    )

    verifier(
        not corpus.valider_corpus(),
        "un point a verifier ne fait pas echouer la validation",
    )

    # Les metadonnees ne doivent jamais se retrouver dans le texte
    # envoye au modele.
    for document in documents:
        verifier(
            "Source :" not in document.texte
            and "Mots-cles" not in document.texte
            and "À-vérifier" not in document.texte,
            f"{document.nom} : l'en-tete est exclu du corps du document",
        )


def tester_decoupage():
    print("\n[2] Decoupage en passages")

    texte_court = "Un paragraphe.\n\nUn autre paragraphe."
    verifier(
        len(corpus.decouper(texte_court)) == 1,
        "un texte court reste en un seul passage",
    )

    verifier(
        corpus.decouper("") == [],
        "un texte vide ne produit aucun passage",
    )

    texte_long = "\n\n".join(f"mot{indice} " * 60 for indice in range(6))
    passages = corpus.decouper(texte_long, taille_mots=100, chevauchement=10)
    verifier(len(passages) > 1, "un texte long est decoupe en plusieurs passages")

    # La regle et son exception doivent rester ensemble.
    document_renouvellement = next(
        document
        for document in corpus.charger_documents()
        if document.nom == "renouvellement_etudiant.txt"
    )

    passage_avec_delai = next(
        (
            passage
            for passage in document_renouvellement.passages
            if "4 mois" in passage.texte
        ),
        None,
    )

    verifier(
        passage_avec_delai is not None
        and "180" in passage_avec_delai.texte,
        "le delai et l'exception hors delai sont dans le meme passage",
    )


# --- Score lexical -------------------------------------------------------

def tester_score_lexical():
    print("\n[3] Score lexical")

    mots = ["renouvellement", "residence permit"]

    verifier(
        recherche.calculer_score_lexical("Bonjour", mots) == 0.0,
        "aucune correspondance donne un score nul",
    )

    verifier(
        recherche.calculer_score_lexical(
            "Quand faire le renouvellement ?", mots
        )
        > 0,
        "un mot-cle present donne un score positif",
    )

    verifier(
        recherche.calculer_score_lexical("RENOUVELLEMENT", mots) > 0,
        "la casse n'a pas d'incidence",
    )

    # Un etudiant international tape souvent sans accents, ou avec les
    # mauvais : la correspondance doit rester insensible aux accents.
    verifier(
        recherche.calculer_score_lexical(
            "renouvéllement de mon titre", ["renouvellement"]
        )
        > 0,
        "les accents n'empechent pas la correspondance",
    )

    verifier(
        recherche.calculer_score_lexical(
            "renouvellement", ["renouvèllement"]
        )
        > 0,
        "un mot-cle accentue correspond a une question sans accents",
    )

    score_expression = recherche.calculer_score_lexical(
        "my residence permit", ["residence permit"]
    )
    score_mot = recherche.calculer_score_lexical(
        "renouvellement", ["renouvellement"]
    )

    verifier(
        score_expression > score_mot,
        "une expression composee pese plus qu'un mot isole",
    )

    verifier(
        recherche.calculer_score_lexical("renouvellement expire", mots) <= 1.0,
        "le score lexical reste borne a 1.0",
    )

    # Confusions observees sur les 90 questions : un mot-cle trouve a
    # l'interieur d'un autre mot envoyait vers le mauvais document.
    for question, mot in [
        ("what paperwork do I need?", "work"),
        ("une prise en charge par mes parents", "rent"),
        ("qui rembourse mes soins ?", "bourse"),
    ]:
        verifier(
            recherche.calculer_score_lexical(question, [mot]) == 0.0,
            f"'{mot}' ne correspond pas a l'interieur d'un autre mot",
        )

    verifier(
        recherche.calculer_score_lexical("les bourses du CROUS", ["bourse"]) > 0,
        "un mot-cle au pluriel correspond toujours",
    )


# --- Abstention ----------------------------------------------------------

def tester_abstention():
    print("\n[4] Regle d'acceptation et d'abstention")

    lexical = {
        "score": 0.50,
        "score_semantique": config.SEUIL_SEMANTIQUE_AVEC_LEXICAL + 0.10,
        "score_lexical": 0.8,
    }
    verifier(
        recherche.est_pertinent(lexical),
        "un mot-cle avec une similarite correcte est accepte",
    )

    # Cas "mot-cle trompeur" : le mot apparait mais la question n'a
    # rien a voir avec le document. C'etait une limitation identifiee.
    mot_cle_trompeur = {
        "score": 0.20,
        "score_semantique": config.SEUIL_SEMANTIQUE_AVEC_LEXICAL - 0.10,
        "score_lexical": 1.0,
    }
    verifier(
        not recherche.est_pertinent(mot_cle_trompeur),
        "un mot-cle trompeur sans similarite semantique est refuse",
    )

    # C'est le comportement corrige : avant, ce cas etait toujours
    # refuse car le seuil semantique n'etait jamais applique.
    semantique = {
        "score": 0.70,
        "score_semantique": config.SEUIL_SEMANTIQUE_SANS_LEXICAL + 0.05,
        "score_lexical": 0.0,
    }
    verifier(
        recherche.est_pertinent(semantique),
        "une forte similarite semantique accepte sans mot-cle",
    )

    semantique_juste_en_dessous = {
        "score": 0.60,
        "score_semantique": config.SEUIL_SEMANTIQUE_SANS_LEXICAL - 0.05,
        "score_lexical": 0.0,
    }
    verifier(
        not recherche.est_pertinent(semantique_juste_en_dessous),
        "une similarite sous le seuil sans mot-cle est refusee",
    )

    verifier(
        config.SEUIL_SEMANTIQUE_AVEC_LEXICAL
        < config.SEUIL_SEMANTIQUE_SANS_LEXICAL,
        "le seuil sans mot-cle est plus exigeant que celui avec mot-cle",
    )


# --- Chaine de recherche complete (embeddings factices) ------------------

def tester_recherche_complete():
    print("\n[5] Chaine de recherche avec embeddings factices")

    recherche.definir_fonction_embedding(embedding_factice)

    # Les vecteurs factices n'ont aucun sens semantique : on neutralise
    # le seuil du chemin lexical le temps du test. Ce test verifie la
    # plomberie (chargement, classement, format de retour), pas la
    # calibration des seuils, testee separement en [4].
    seuil_initial = config.SEUIL_SEMANTIQUE_AVEC_LEXICAL
    config.SEUIL_SEMANTIQUE_AVEC_LEXICAL = -1.0

    resultats = recherche.rechercher_passages("renouvellement de mon titre")

    verifier(bool(resultats), "la recherche retourne des resultats")

    verifier(
        all(
            resultats[indice]["score"] >= resultats[indice + 1]["score"]
            for indice in range(len(resultats) - 1)
        ),
        "les resultats sont tries par score decroissant",
    )

    # Les vecteurs factices donnent des similarites arbitraires qui
    # peuvent depasser le signal lexical (0.85 contre 0.15). Pour tester
    # ce seul signal, on classe le temps d'un appel avec un poids
    # semantique nul.
    poids_initiaux = (config.POIDS_SEMANTIQUE, config.POIDS_LEXICAL)
    config.POIDS_SEMANTIQUE, config.POIDS_LEXICAL = 0.0, 1.0

    try:
        classement_lexical = recherche.rechercher_passages(
            "renouvellement de mon titre"
        )
    finally:
        config.POIDS_SEMANTIQUE, config.POIDS_LEXICAL = poids_initiaux

    verifier(
        classement_lexical[0]["nom"] == "renouvellement_etudiant.txt",
        "le document attendu est premier grace au signal lexical",
    )

    resultat = recherche.rechercher_document(
        "Quand dois-je faire le renouvellement de mon titre ?"
    )

    verifier(resultat is not None, "une question dans le corpus est acceptee")

    verifier(
        resultat is not None and resultat["source"].startswith("http"),
        "la source officielle est remontee",
    )

    # Avec des embeddings factices, une question hors sujet n'a ni
    # mot-cle ni similarite : elle doit declencher l'abstention.
    hors_sujet = recherche.rechercher_document(
        "Comment adopter un chat en Belgique ?"
    )

    verifier(
        hors_sujet is None,
        "une question hors corpus declenche l'abstention",
    )

    config.SEUIL_SEMANTIQUE_AVEC_LEXICAL = seuil_initial
    recherche.definir_fonction_embedding(recherche.embedding_ollama)


# --- Cache ---------------------------------------------------------------

def tester_cache():
    print("\n[6] Cache d'embeddings")

    texte = "texte de test pour le cache"
    modele = "modele-de-test"

    cache_embeddings.ecrire(texte, modele, [0.1, 0.2, 0.3])

    verifier(
        cache_embeddings.lire(texte, modele) == [0.1, 0.2, 0.3],
        "un vecteur ecrit est relu a l'identique",
    )

    verifier(
        cache_embeddings.lire(texte, "autre-modele") is None,
        "changer de modele invalide l'entree de cache",
    )

    verifier(
        cache_embeddings.lire("autre texte", modele) is None,
        "modifier le texte invalide l'entree de cache",
    )


# --- Verification --------------------------------------------------------

def tester_verification():
    print("\n[7] Controle d'ancrage des reponses")

    document = (
        "Vous devez demander votre titre au plus tot 4 mois et au plus "
        "tard 2 mois avant la fin de validite. Vous devez regler une "
        "taxe et un droit de timbre de 100 EUR. Hors delai, un droit "
        "de visa de regularisation de 180 EUR s'applique."
    )

    fidele = (
        "You must apply between 4 and 2 months before your permit "
        "expires, and pay a 100 EUR stamp duty."
    )

    avertissements, _ = verification.controler_reponse(fidele, document)
    verifier(not avertissements, "une reponse fidele ne declenche rien")

    invente = "You must apply 6 months before and pay a 250 EUR fee."
    avertissements, diagnostic = verification.controler_reponse(
        invente, document
    )
    verifier(
        diagnostic["non_justifies"],
        "un chiffre absent du document est detecte",
    )

    # Le document est en francais, la reponse en anglais : les unites
    # doivent se correspondre malgre la langue.
    verifier(
        ("4", "mois") in verification.extraire_chiffres("4 months"),
        "'4 months' et '4 mois' sont reconnus comme la meme duree",
    )

    verifier(
        ("877.5", "montant")
        in verification.extraire_chiffres("877,5 € par mois"),
        "un montant decimal a la francaise est reconnu",
    )

    # Les heures sont l'unite centrale du document sur le travail
    # etudiant (plafond de 964 heures). Sans cette famille, un plafond
    # invente passerait le controle sans etre detecte.
    verifier(
        ("964", "heures") in verification.extraire_chiffres("964 heures"),
        "une duree en heures est reconnue",
    )

    verifier(
        verification.extraire_chiffres("964 hours")
        == verification.extraire_chiffres("964 heures"),
        "'964 hours' et '964 heures' sont reconnus a l'identique",
    )

    verifier(
        ("964", "heures") in verification.extraire_chiffres("964h par an"),
        "la forme abregee 964h est reconnue",
    )

    document_travail = (
        "L'activite salariee est autorisee dans la limite de 964 heures "
        "par an, soit 60 % de la duree legale annuelle du travail."
    )

    _, diagnostic_travail = verification.controler_reponse(
        "You may work up to 1200 hours per year.",
        document_travail,
    )
    verifier(
        ("1200", "heures") in diagnostic_travail["non_justifies"],
        "un plafond horaire invente est detecte",
    )

    _, diagnostic_conversion = verification.controler_reponse(
        "You may work about 20 hours per week.",
        document_travail,
    )
    verifier(
        diagnostic_conversion["non_justifies"],
        "une conversion horaire absente du document est detectee",
    )

    avec_lien, _ = verification.controler_reponse(
        "See https://exemple.fr for details.", document
    )
    verifier(
        any("URL" in message for message in avec_lien),
        "une URL residuelle est signalee",
    )

    en_francais, _ = verification.controler_reponse(
        "Vous devez demander votre titre dans les delais prevus.", document
    )
    verifier(
        any("francais" in message for message in en_francais),
        "une reponse restee en francais est signalee",
    )


# --- Garde-fou de generation --------------------------------------------

def tester_garde_fou_generation():
    print("\n[8] Garde-fou de generation")

    document = (
        "Vous devez pouvoir justifier de ressources au moins egales a "
        "877,5 EUR par mois."
    )

    from assistant import MESSAGE_NON_FIABLE, definir_fonction_generation

    definir_fonction_generation(
        lambda prompt: "You must prove resources of at least 877,5 EUR per month."
    )

    reponse = generer_reponse("How much money do I need?", document)
    verifier(
        "877" in reponse,
        "une reponse correctement ancree est transmise telle quelle",
    )

    definir_fonction_generation(
        lambda prompt: "You must prove resources of at least 1200 EUR per month."
    )

    reponse = generer_reponse("How much money do I need?", document)
    verifier(
        reponse == MESSAGE_NON_FIABLE,
        "un montant invente declenche l'abstention plutot que la diffusion",
    )

    definir_fonction_generation(
        lambda prompt: "Check https://faux-site.fr for the amount."
    )

    reponse = generer_reponse("How much money do I need?", document)
    verifier(
        "https://" not in reponse,
        "une URL generee par le modele est filtree",
    )


# --- Version 3 : prompt, profil, sessions, flux --------------------------

def _evenements(flux_sse):
    """Decode une suite d'evenements SSE en liste de (type, donnees)."""

    import json

    resultat = []

    for bloc in flux_sse:
        lignes = dict(
            ligne.split(": ", 1) for ligne in bloc.strip().split("\n")
        )
        resultat.append((lignes["event"], json.loads(lignes["data"])))

    return resultat


def _activer_recherche_factice():
    recherche.definir_fonction_embedding(embedding_factice)
    seuil_initial = config.SEUIL_SEMANTIQUE_AVEC_LEXICAL
    config.SEUIL_SEMANTIQUE_AVEC_LEXICAL = -1.0
    return seuil_initial


def _desactiver_recherche_factice(seuil_initial):
    config.SEUIL_SEMANTIQUE_AVEC_LEXICAL = seuil_initial
    recherche.definir_fonction_embedding(recherche.embedding_ollama)


QUESTION_TITRE_ET_LOGEMENT = (
    "Renouvellement de mon titre de séjour et aide au logement CAF ?"
)


def tester_prompt_systeme():
    print("\n[9] Prompt systeme et messages envoyes au modele")

    import assistant

    verifier(
        "TOUJOURS en français" in assistant.PROMPT_SYSTEME,
        "le prompt systeme contient 'TOUJOURS en français'",
    )

    historique = [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Bonjour, que veux-tu savoir ?"},
    ]
    messages = assistant.construire_messages(
        "Et la CAF ?", "[CONTEXTE]\n[/CONTEXTE]", historique, None
    )

    verifier(
        messages[0] == {"role": "system", "content": assistant.PROMPT_SYSTEME},
        "le premier message est le prompt systeme",
    )
    verifier(
        [message["role"] for message in messages]
        == ["system", "user", "assistant", "user"],
        "l'historique complet est transmis avec ses roles",
    )
    verifier(
        "[QUESTION]\nEt la CAF ?" in messages[-1]["content"]
        and "[CONTEXTE]" in messages[-1]["content"],
        "le dernier message porte le contexte et la question",
    )

    precision = [
        {"role": "user", "content": "Combien coûte mon titre ?"},
        {"role": "assistant", "content": "Première demande ou renouvellement ?"},
    ]
    verifier(
        assistant.question_pour_recherche("renouvellement", precision)
        == "Combien coûte mon titre ? renouvellement",
        "apres une question de precision, la reponse est recherchee avec la question d'origine",
    )
    verifier(
        assistant.question_pour_recherche(
            "Et la CAF ?",
            [
                {"role": "user", "content": "Bonjour"},
                {"role": "assistant", "content": "**Logement**\nVoici la réponse."},
            ],
        )
        == "Et la CAF ?",
        "sans question de precision, la question est recherchee seule",
    )

    # Aucun passage trouve : question de precision ou abstention.
    recherche_initiale = recherche.rechercher_document
    recherche.rechercher_document = lambda question, categories_exclues=None: None

    try:
        hors_ue = {"pays_origine": "Maroc", "zone": "HORS_UE"}
        vague = "Combien coûte mon titre de séjour ?"

        verifier(
            assistant.preparer(vague, hors_ue)["type"] == "clarification",
            "titre de sejour sans passage : question de precision au lieu d'abstention",
        )
        verifier(
            assistant.preparer("How do I renew my Netflix subscription?", hors_ue)["type"]
            == "abstention",
            "hors sujet sans passage : abstention",
        )
        verifier(
            assistant.preparer(vague, {"pays_origine": "Italie", "zone": "UE"})["type"]
            == "abstention",
            "profil UE : pas de question de precision sur le titre de sejour",
        )
        verifier(
            assistant.preparer(
                vague,
                hors_ue,
                precision_demandee=assistant.precision_deja_demandee(
                    [{"role": "assistant", "content": assistant.MESSAGE_PRECISION}]
                ),
            )["type"]
            == "abstention",
            "pas de deuxieme question de precision d'affilee",
        )
    finally:
        recherche.rechercher_document = recherche_initiale

    # Une consigne citant "[QUESTION]" / "[CONTEXTE]" faisait recopier
    # la question et les passages par qwen2.5:3b.
    verifier(
        messages[-1]["content"].endswith(assistant.CONSIGNE_QUESTION_COURANTE)
        and "[" not in assistant.CONSIGNE_QUESTION_COURANTE,
        "la consigne finale suit la question et ne cite aucun balisage",
    )


def tester_filtrage_ue():
    print("\n[10] Filtrage UE")

    import assistant
    import profil

    verifier(
        profil.completer({"pays_origine": "Italie"})["zone"] == "UE",
        "la zone UE est deduite du pays",
    )
    verifier(
        profil.completer({"pays_origine": "Sénégal"})["zone"] == "HORS_UE",
        "la zone HORS_UE est deduite du pays",
    )

    seuil = _activer_recherche_factice()

    try:
        sans_profil = recherche.rechercher_document(QUESTION_TITRE_ET_LOGEMENT)
        verifier(
            sans_profil is not None
            and any(
                passage.categorie == "titre_sejour"
                for passage in sans_profil["passages"]
            ),
            "sans profil UE, un passage titre_sejour est retenu (temoin)",
        )

        etape = assistant.preparer(
            QUESTION_TITRE_ET_LOGEMENT, {"pays_origine": "Italie", "zone": "UE"}
        )
        verifier(
            etape["type"] == "contexte",
            "profil UE : un contexte est tout de meme construit",
        )
        verifier(
            etape["type"] == "contexte"
            and all(
                passage.categorie != "titre_sejour"
                for passage in etape["resultat"]["passages"]
            ),
            "profil UE : aucun passage titre_sejour dans le contexte",
        )

        textes_titre_sejour = [
            passage.texte
            for passage in corpus.charger_passages()
            if passage.categorie == "titre_sejour"
        ]
        verifier(
            etape["type"] == "contexte"
            and not any(
                texte in etape["contexte"] for texte in textes_titre_sejour
            ),
            "profil UE : aucun texte titre_sejour dans le prompt envoye",
        )

    finally:
        _desactiver_recherche_factice(seuil)


def tester_filtrage_algerien():
    print("\n[11] Profil algerien")

    import assistant
    import profil

    for pays in ("Algérie", "algérien", "ALGERIE"):
        contexte = assistant.construire_contexte(
            "Un passage.", profil.completer({"pays_origine": pays})
        )
        verifier(
            "carte_pluriannuelle_exclue" in contexte,
            f"pays '{pays}' : drapeau carte_pluriannuelle_exclue present",
        )

    contexte_maroc = assistant.construire_contexte(
        "Un passage.", profil.completer({"pays_origine": "Maroc"})
    )
    verifier(
        "carte_pluriannuelle_exclue" not in contexte_maroc,
        "autre nationalite : pas de drapeau",
    )


def tester_sessions_et_flux():
    print("\n[12] Sessions, clarification et flux SSE")

    import api
    import assistant
    import sessions

    sessions.vider()
    seuil = _activer_recherche_factice()

    messages_recus = []

    def flux_factice(messages):
        messages_recus.append(messages)
        yield "**Logement**\n"
        yield "Tu peux demander une aide au logement."

    assistant.definir_fonction_flux(flux_factice)

    try:
        session_id = api.nouvelle_session()["session_id"]

        premiers = _evenements(
            api.traiter_question(
                api.QuestionRequest(
                    question=QUESTION_TITRE_ET_LOGEMENT,
                    session_id=session_id,
                    profil={"pays_origine": "Algérie"},
                )
            )
        )

        verifier(
            premiers[0] == ("session", {"session_id": session_id}),
            "le premier evenement SSE annonce la session",
        )
        verifier(
            [type_ for type_, _ in premiers if type_ == "token"]
            == ["token", "token"],
            "chaque fragment genere est transmis comme evenement token",
        )
        verifier(
            premiers[-1][0] == "done",
            "une reponse ancree se termine par l'evenement done",
        )

        seconds = _evenements(
            api.traiter_question(
                api.QuestionRequest(
                    question="Et pour le renouvellement de mon titre ?",
                    session_id=session_id,
                )
            )
        )

        verifier(
            seconds[-1][0] == "done",
            "meme session sans profil : pas de nouvelle clarification",
        )
        verifier(
            sessions.obtenir(session_id).profil.get("pays_origine") == "Algérie",
            "le profil est conserve dans la session",
        )
        verifier(
            len(messages_recus) == 2
            and "carte_pluriannuelle_exclue" in messages_recus[1][-1]["content"],
            "la deuxieme question reutilise le profil (drapeau algerien)",
        )
        verifier(
            [message["role"] for message in messages_recus[1]]
            == ["system", "user", "assistant", "user"],
            "la deuxieme question recoit l'historique de la premiere",
        )
        verifier(
            len(api.lire_session(session_id)["historique"]) == 4,
            "GET /session retourne l'historique courant",
        )

        # Nouvelle session sans profil, question sur le titre de sejour.
        clarification = _evenements(
            api.traiter_question(
                api.QuestionRequest(
                    question="Quand renouveler mon titre de séjour ?"
                )
            )
        )
        verifier(
            clarification[-1][0] == "clarification"
            and "pays_origine" in clarification[-1][1]["champs_manquants"],
            "profil absent + titre de sejour : question de clarification",
        )
        verifier(
            not any(type_ == "meta" for type_, _ in clarification)
            and len(messages_recus) == 2,
            "la clarification precede toute recherche et generation",
        )

        # Controle d'ancrage en echec apres le flux.
        assistant.definir_fonction_flux(
            lambda messages: iter(["Il faut 9999 € de ressources."])
        )
        echec = _evenements(
            api.traiter_question(
                api.QuestionRequest(
                    question=QUESTION_TITRE_ET_LOGEMENT,
                    session_id=session_id,
                )
            )
        )
        verifier(
            echec[-1][0] == "error"
            and echec[-1][1]["type"] == "abstention_verification"
            and echec[-1][1]["message"] == assistant.MESSAGE_NON_FIABLE,
            "ancrage en echec : evenement final error avec l'abstention",
        )

    finally:
        assistant.definir_fonction_flux(assistant.flux_ollama)
        _desactiver_recherche_factice(seuil)
        sessions.vider()


def isoler_cache():
    """Redirige le cache d'embeddings vers un dossier temporaire.

    Sans cela, les vecteurs factices (dimension 32) etaient ecrits dans
    le vrai cache .cache/embeddings sous le nom du vrai modele : l'API,
    relancee ensuite, relisait ces vecteurs, la similarite valait 0
    (dimensions differentes) et l'assistant s'abstenait sur tout.
    """

    import tempfile

    dossier = Path(tempfile.mkdtemp(prefix="studentia-tests-"))
    cache_embeddings.DOSSIER_CACHE = dossier
    cache_embeddings._MEMOIRE.clear()

    return dossier


def main():
    print("\n=== TESTS HORS LIGNE (sans Ollama) ===")

    import shutil

    dossier_cache_tests = isoler_cache()
    vrai_cache = config.DOSSIER_CACHE / "embeddings"
    fichiers_avant = set(vrai_cache.glob("*.json")) if vrai_cache.exists() else set()

    try:
        tester_corpus()
        tester_decoupage()
        tester_score_lexical()
        tester_abstention()
        tester_recherche_complete()
        tester_cache()
        tester_verification()
        tester_garde_fou_generation()
        tester_prompt_systeme()
        tester_filtrage_ue()
        tester_filtrage_algerien()
        tester_sessions_et_flux()
    finally:
        shutil.rmtree(dossier_cache_tests, ignore_errors=True)

    print("\n[13] Isolation du cache")

    fichiers_apres = set(vrai_cache.glob("*.json")) if vrai_cache.exists() else set()
    verifier(
        fichiers_apres <= fichiers_avant,
        "les tests n'ecrivent rien dans le vrai cache d'embeddings",
    )

    print("\n" + "=" * 46)

    if ECHECS:
        print(f"{len(ECHECS)} test(s) en echec :")
        for description in ECHECS:
            print(f"  - {description}")
        print("=" * 46 + "\n")
        return 1

    print("Tous les tests hors ligne passent.")
    print("=" * 46 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
