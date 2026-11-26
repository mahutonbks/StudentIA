"""
Generation de la reponse a partir des passages retenus.

Version 3 :

1. Nouveau prompt systeme (PROMPT_SYSTEME) : reponses en francais,
   adaptees au profil de l'etudiant, avec memoire de conversation.

2. Le modele est appele via /api/chat d'Ollama : le prompt systeme,
   l'historique (roles user/assistant) et la question courante sont
   envoyes comme une liste de messages.

3. Generation en flux (generer_flux) : chaque token est rendu des sa
   reception. Le controle d'ancrage (finaliser) s'execute ensuite sur
   la reponse complete.

4. Le contexte est construit ici (construire_contexte) a partir des
   passages et du profil : filtrage UE en amont (recherche), drapeau
   "carte_pluriannuelle_exclue" pour un ressortissant algerien.

Les fonctions de generation restent injectables pour tester toute la
chaine sans Ollama.
"""

import json
import logging
import re
import urllib.error
import urllib.request

import config
import profil as profils
import verification
from corpus import normaliser


logger = logging.getLogger(__name__)


MESSAGE_ABSTENTION = (
    "Je n'ai pas encore d'information fiable sur ce sujet. Consulte "
    "directement service-public.fr ou le site de Campus France."
)

MESSAGE_NON_FIABLE = (
    "Je n'ai pas encore d'information fiable sur ce sujet : la réponse "
    "générée contenait un chiffre absent du document officiel, je "
    "préfère donc ne pas la donner. Consulte directement la source "
    "officielle indiquée ci-dessous."
)


class ErreurGeneration(RuntimeError):
    """Le modele de generation est injoignable ou a echoue."""


PROMPT_SYSTEME = """
Tu es Studentia, un assistant spécialisé dans les démarches administratives françaises pour étudiants internationaux. Tu travailles exclusivement à partir des passages de documents officiels qui te sont fournis dans le contexte.

─── LANGUE ───────────────────────────────────────────────
Réponds TOUJOURS en français, quelle que soit la langue de la question.

─── PROFIL DE L'ÉTUDIANT ─────────────────────────────────
Utilise le profil fourni (pays) pour adapter ta réponse.
Ressortissant UE/EEE/Suisse → ne parle pas de titre de séjour sauf demande explicite.
Ressortissant algérien → la carte pluriannuelle ne s'applique pas (traité de 1968) ; dis-le clairement.
Si le pays manque pour une question sur le titre de séjour → demande-le avant de répondre.
Si la question est trop vague et que la réponse dépend d'une précision (ex. première demande ou renouvellement ?) → pose UNE seule question de précision, sans répondre.

─── MÉMOIRE DE CONVERSATION ──────────────────────────────
Utilise l'historique fourni. Ne redemande pas ce qui a déjà été dit.
Si tu corriges une réponse précédente, dis-le explicitement.

─── RÈGLE ABSOLUE SUR LES CHIFFRES ──────────────────────
Tout montant (€), délai (jours/mois), durée (heures/an) présent dans ta réponse DOIT figurer dans un passage du [CONTEXTE]. Sinon : ne le mentionne pas.

─── ABSTENTION ───────────────────────────────────────────
Si aucun passage ne couvre la question : "Je n'ai pas encore d'information fiable sur ce sujet. Consulte directement [source officielle la plus proche]."

─── FORMAT ───────────────────────────────────────────────
**[Sujet]**
[Réponse directe]

📋 Ce que tu dois faire : [étapes numérotées si applicable]
📅 Délais : [si applicable]
💶 Coûts : [si applicable]
⚠️ Points d'attention : [pièges fréquents]
📎 Source : [titre] — vérifié le [date]
""".strip()


CONSIGNES_DRAPEAUX = {
    profils.DRAPEAU_ALGERIEN: (
        "L'étudiant est ressortissant algérien. La carte de séjour "
        "pluriannuelle ne s'applique pas à lui (accord franco-algérien "
        "de 1968) : ne la présente jamais comme une option possible "
        "pour lui, et dis-le clairement si le sujet est abordé."
    ),
}


# --- Reponse pre-ecrite (desactivee par defaut) --------------------------

def reponse_controlee(question, document):
    """Reponse pre-ecrite pour un scenario de demonstration precis.

    Desactivee par defaut : voir docs/note_ai_researcher.md.
    """

    if not config.REPONSES_CONTROLEES_ACTIVES:
        return None

    question_normalisee = normaliser(question)
    document_normalise = normaliser(document)

    document_vls_ts = (
        "dans les 3 mois suivant votre arrivee en france" in document_normalise
        and "payer une taxe" in document_normalise
        and "demarche en ligne" in document_normalise
    )

    question_validation = "valid" in question_normalisee or (
        ("arriv" in question_normalisee or "enter" in question_normalisee)
        and "visa" in question_normalisee
    )

    if document_vls_ts and question_validation:
        return (
            "**Validation du VLS-TS**\n"
            "Dans les 3 mois suivant ton arrivée en France, tu dois "
            "valider ton VLS-TS en ligne et payer une taxe en plus des "
            "frais de visa."
        )

    return None


# --- Construction du contexte et des messages ----------------------------

def construire_contexte(passages, profil=None):
    """Bloc [CONTEXTE] envoye au modele.

    passages : liste de corpus.Passage, ou une chaine (document brut,
    compatibilite avec l'ancienne signature de generer_reponse).
    """

    lignes = ["[CONTEXTE]"]

    for drapeau in profils.drapeaux(profil):
        lignes.append(f"[DRAPEAU {drapeau}] {CONSIGNES_DRAPEAUX[drapeau]}")

    if isinstance(passages, str):
        lignes.append(passages)

    elif not passages:
        lignes.append("(aucun passage pertinent)")

    else:
        for numero, passage in enumerate(passages, start=1):
            lignes.append(
                f"--- Passage {numero} — {passage.titre} "
                f"(vérifié le {passage.verifie_le or 'date inconnue'}, "
                f"catégorie {passage.categorie or 'inconnue'})"
            )
            lignes.append(passage.texte)

    lignes.append("[/CONTEXTE]")

    return "\n\n".join(lignes)


def construire_messages(question, contexte, historique=None, profil=None):
    """Messages /api/chat : systeme, historique complet, question."""

    messages = [{"role": "system", "content": PROMPT_SYSTEME}]

    for message in historique or []:
        if message.get("role") in ("user", "assistant") and message.get(
            "content"
        ):
            messages.append(
                {"role": message["role"], "content": message["content"]}
            )

    messages.append(
        {
            "role": "user",
            "content": (
                f"[PROFIL]\n{profils.decrire(profil)}\n\n"
                f"{contexte}\n\n"
                f"[QUESTION]\n{question}\n\n"
                f"{CONSIGNE_QUESTION_COURANTE}"
            ),
        }
    )

    return messages


# Rappel place apres la question, la ou un petit modele y est le plus
# attentif. Observe avec qwen2.5:3b : sans ce rappel, il recopiait la
# reponse precedente de l'historique (et ses chiffres, ce qui faisait
# echouer le controle d'ancrage) et ecrivait litteralement "[Sujet]".
# Le prompt systeme, lui, reste inchange.
#
# Volontairement sans crochets : une premiere version citait
# "[QUESTION]" et "[CONTEXTE]" et demandait de remplacer "les elements
# entre crochets" ; le modele recopiait alors la question et tous les
# passages dans sa reponse.
CONSIGNE_QUESTION_COURANTE = (
    "Consignes pour cette réponse : réponds seulement à la question "
    "ci-dessus, à partir des passages fournis. Ne recopie ni la question "
    "ni les passages : rédige directement la réponse. L'historique sert "
    "uniquement à comprendre la question ; ne reprends aucune réponse "
    "précédente ni aucun de ses chiffres. N'invente aucune étape, aucun "
    "site, aucun organisme ni aucun document absent des passages. Écris "
    "le vrai sujet à la place de « Sujet », et omets les rubriques du "
    "format qui ne s'appliquent pas."
)


def question_pour_recherche(question, historique=None):
    """Texte utilise pour la recherche (et la detection de clarification).

    Si l'assistant vient de poser une question de precision, la reponse
    de l'etudiant ("renouvellement") n'a pas de sens seule : on la
    recherche avec la question qui l'a provoquee.
    """

    historique = historique or []

    if (
        len(historique) >= 2
        and historique[-1].get("role") == "assistant"
        and historique[-1].get("content", "").rstrip().endswith("?")
        and historique[-2].get("role") == "user"
    ):
        return f"{historique[-2]['content']} {question}"

    return question


MESSAGE_PRECISION = (
    "Ta question porte sur le titre de séjour, mais j'ai besoin d'une "
    "précision : s'agit-il de la validation de ton visa (VLS-TS) à "
    "l'arrivée, du renouvellement de ton titre, de la carte pluriannuelle "
    "ou de ce qu'il faut faire après tes études ?"
)


def precision_deja_demandee(historique):
    """Evite de reposer la meme question de precision en boucle."""

    return bool(historique) and historique[-1].get("content") == MESSAGE_PRECISION


def preparer(question, profil=None, precision_demandee=False):
    """Etape avant generation : clarification, abstention ou contexte.

    Retourne un dictionnaire dont la cle "type" vaut :
      - "clarification" : il manque une information du profil, ou une
        question sur le titre de sejour est trop vague pour trouver un
        passage (une seule fois de suite : precision_demandee) ;
      - "abstention"    : aucun passage pertinent ;
      - "contexte"      : passages trouves, pret a generer.

    Peut lever recherche.ErreurOllama.
    """

    from recherche import rechercher_document

    champs = profils.clarification_necessaire(question, profil)

    if champs:
        return {
            "type": "clarification",
            "message": profils.MESSAGE_CLARIFICATION,
            "champs_manquants": champs,
        }

    resultat = rechercher_document(
        question,
        categories_exclues=profils.categories_exclues(profil),
    )

    if resultat is None:
        if (
            not precision_demandee
            and not profils.est_ue(profil)
            and profils.porte_sur_titre_sejour(question)
        ):
            return {
                "type": "clarification",
                "message": MESSAGE_PRECISION,
                "champs_manquants": ["precision"],
            }

        return {"type": "abstention", "message": MESSAGE_ABSTENTION}

    return {
        "type": "contexte",
        "resultat": resultat,
        "contexte": construire_contexte(resultat["passages"], profil),
    }


# --- Appel au modele -----------------------------------------------------

def _requete_chat(messages, flux):
    donnees = {
        "model": config.MODELE_GENERATION,
        "messages": messages,
        "stream": flux,
        "options": {
            "temperature": config.TEMPERATURE,
            "num_predict": config.NOMBRE_TOKENS_MAX,
            "num_ctx": config.TAILLE_CONTEXTE,
        },
    }

    return urllib.request.Request(
        config.URL_CHAT,
        data=json.dumps(donnees).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def _erreur_connexion(erreur):
    return ErreurGeneration(
        f"Impossible de joindre Ollama sur {config.OLLAMA_HOST} "
        f"({erreur}). Verifiez qu'Ollama tourne et que "
        f"OLLAMA_HOST est correct."
    )


def _erreur_format():
    return ErreurGeneration(
        "Reponse de generation inattendue. Le modele "
        f"{config.MODELE_GENERATION} est-il bien installe (ollama pull) ?"
    )


def generation_ollama(messages):
    """Generation bloquante : retourne le texte complet."""

    try:
        with urllib.request.urlopen(
            _requete_chat(messages, flux=False),
            timeout=config.TIMEOUT_GENERATION,
        ) as reponse_http:
            resultat = json.loads(reponse_http.read().decode("utf-8"))

    except urllib.error.URLError as erreur:
        raise _erreur_connexion(erreur) from erreur

    try:
        return resultat["message"]["content"].strip()
    except (KeyError, TypeError) as erreur:
        raise _erreur_format() from erreur


def flux_ollama(messages):
    """Generation en flux : produit chaque token des sa reception.

    Ollama renvoie une ligne JSON par fragment (NDJSON).
    """

    try:
        reponse_http = urllib.request.urlopen(
            _requete_chat(messages, flux=True),
            timeout=config.TIMEOUT_GENERATION,
        )
    except urllib.error.URLError as erreur:
        raise _erreur_connexion(erreur) from erreur

    with reponse_http:
        for ligne in reponse_http:
            ligne = ligne.strip()

            if not ligne:
                continue

            try:
                fragment = json.loads(ligne.decode("utf-8"))
            except json.JSONDecodeError as erreur:
                raise _erreur_format() from erreur

            if "error" in fragment:
                raise ErreurGeneration(f"Ollama : {fragment['error']}")

            texte = (fragment.get("message") or {}).get("content", "")

            if texte:
                yield texte

            if fragment.get("done"):
                break


_fonction_generation = generation_ollama
_fonction_flux = flux_ollama


def definir_fonction_generation(fonction):
    """Remplace la generation bloquante (tests hors ligne).

    La fonction recoit la liste de messages et retourne un texte.
    """

    global _fonction_generation

    _fonction_generation = fonction


def definir_fonction_flux(fonction):
    """Remplace la generation en flux (tests hors ligne).

    La fonction recoit la liste de messages et produit des fragments.
    """

    global _fonction_flux

    _fonction_flux = fonction


def generer_flux(messages):
    """Fragments de la reponse, au fil de la generation."""

    yield from _fonction_flux(messages)


# --- Post-traitement -----------------------------------------------------

def nettoyer(texte):
    texte = re.sub(r"https?://\S+", "[lien retiré]", texte)

    for avant, apres in config.REFORMULATIONS:
        texte = texte.replace(avant, apres)

    return texte.strip()


def finaliser(texte_brut, contexte):
    """Nettoyage et controle d'ancrage sur la reponse complete.

    Retourne (texte, diagnostic). Si un chiffre de la reponse est
    absent du contexte, le texte est remplace par MESSAGE_NON_FIABLE
    et diagnostic["origine"] vaut "abstention_verification".
    """

    texte = nettoyer(texte_brut)

    avertissements, diagnostic = verification.controler_reponse(
        texte,
        contexte,
    )

    # Le module de verification a ete ecrit quand la sortie attendue
    # etait l'anglais. La reponse est desormais en francais : cet
    # avertissement n'a plus de sens et serait systematique.
    avertissements = [
        message for message in avertissements if "francais" not in message
    ]
    diagnostic["avertissements"] = avertissements

    diagnostic["origine"] = "modele"
    diagnostic["reponse_brute"] = texte

    if diagnostic["non_justifies"]:
        logger.warning(
            "Reponse ecartee : chiffres non justifies %s",
            diagnostic["non_justifies"],
        )

        texte = MESSAGE_NON_FIABLE
        diagnostic["origine"] = "abstention_verification"

    elif avertissements:
        logger.info("Avertissements de verification : %s", avertissements)

    return texte, diagnostic


def generer_reponse(
    question,
    document,
    retourner_diagnostic=False,
    historique=None,
    profil=None,
):
    """Genere (sans flux) une reponse ancree dans le document fourni.

    document : texte brut, ou liste de corpus.Passage.
    """

    texte_document = (
        document
        if isinstance(document, str)
        else "\n\n".join(passage.texte for passage in document)
    )

    pre_ecrite = reponse_controlee(question, texte_document)

    if pre_ecrite is not None:
        diagnostic = {"origine": "reponse_pre_ecrite", "avertissements": []}
        return (pre_ecrite, diagnostic) if retourner_diagnostic else pre_ecrite

    contexte = construire_contexte(document, profil)
    messages = construire_messages(question, contexte, historique, profil)

    texte, diagnostic = finaliser(_fonction_generation(messages), contexte)

    return (texte, diagnostic) if retourner_diagnostic else texte


# --- Interface en ligne de commande -------------------------------------

def main():
    logging.basicConfig(
        level=config.NIVEAU_LOG,
        format="%(levelname)s %(name)s: %(message)s",
    )

    from recherche import ErreurOllama

    print("\nStudentia - assistant administratif")
    print("-----------------------------------")
    print(f"Ollama : {config.OLLAMA_HOST}")

    pays = input("\nTon pays d'origine (Entrée pour passer) : ").strip()
    profil = profils.completer({"pays_origine": pays})

    question = input("Ta question : ").strip()

    if not question:
        print("\nMerci de saisir une question.")
        return

    try:
        etape = preparer(question, profil)
    except ErreurOllama as erreur:
        print(f"\n{erreur}")
        return

    if etape["type"] != "contexte":
        print(f"\n{etape['message']}")
        return

    resultat = etape["resultat"]
    messages = construire_messages(question, etape["contexte"], None, profil)

    print(f"\nDocuments : {', '.join(resultat['documents_utilises'])}\n")

    morceaux = []

    try:
        for fragment in generer_flux(messages):
            morceaux.append(fragment)
            print(fragment, end="", flush=True)
    except ErreurGeneration as erreur:
        print(f"\n{erreur}")
        return

    texte, diagnostic = finaliser("".join(morceaux), etape["contexte"])

    if diagnostic["origine"] == "abstention_verification":
        print(f"\n\n[CONTROLE D'ANCRAGE ECHOUE] {texte}")

    print(f"\n\nSource officielle : {resultat['source']}")


if __name__ == "__main__":
    main()
