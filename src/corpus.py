"""
Chargement, decoupage et validation du corpus documentaire.

Ce module remplace la lecture de fichiers dispersee dans recherche.py
et apporte trois changements de fond :

1. Les metadonnees (titre, source, mots-cles, date de verification)
   sont lues depuis l'en-tete du fichier .txt. Ajouter un document ne
   demande plus de modifier du code Python : le dictionnaire
   MOTS_THEMES ecrit en dur dans recherche.py a disparu.

2. Les documents sont decoupes en passages (chunks). Tant que les
   documents sont courts, un document = un passage ; le decoupage
   devient utile des qu'on ajoute des textes plus longs.

3. valider_corpus() detecte les erreurs de saisie (source manquante,
   mots-cles absents, date de verification absente) avant qu'elles ne
   degradent silencieusement la recherche.
"""

import hashlib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import config


CHAMPS_ENTETE = {
    "titre": "titre",
    "title": "titre",
    "source": "source",
    "mots-cles": "mots_cles",
    "mots-clés": "mots_cles",
    "keywords": "mots_cles",
    "verifie-le": "verifie_le",
    "vérifié-le": "verifie_le",
    "verified-on": "verifie_le",
    "categorie": "categorie",
    "catégorie": "categorie",
    "a-verifier": "a_verifier",
    "à-vérifier": "a_verifier",
    "a-verifier-note": "a_verifier",
    "to-check": "a_verifier",
}


@dataclass
class Passage:
    """Unite de recherche : un morceau de document avec ses metadonnees."""

    nom_document: str
    titre: str
    source: str
    categorie: str
    mots_cles: list
    verifie_le: str
    texte: str
    a_verifier: str = ""
    indice: int = 0

    @property
    def identifiant(self):
        return f"{self.nom_document}#{self.indice}"

    @property
    def texte_embedding(self):
        """Le titre est prefixe au passage : il porte le sujet du document."""
        return f"{self.titre}\n{self.texte}"

    @property
    def empreinte(self):
        """Hash du contenu, utilise comme cle de cache d'embedding."""
        return hashlib.sha256(
            self.texte_embedding.encode("utf-8")
        ).hexdigest()


@dataclass
class Document:
    nom: str
    titre: str
    source: str
    categorie: str
    mots_cles: list
    verifie_le: str
    texte: str
    a_verifier: str = ""
    passages: list = field(default_factory=list)


def normaliser(texte):
    """Minuscules sans accents, pour les comparaisons lexicales."""

    texte = texte.lower()
    texte = unicodedata.normalize("NFD", texte)

    return "".join(
        caractere
        for caractere in texte
        if unicodedata.category(caractere) != "Mn"
    )


def analyser_entete(contenu):
    """Separe l'en-tete de metadonnees du corps du document.

    L'en-tete est constitue des lignes de la forme "Cle : valeur"
    situees en debut de fichier, ainsi que de la ligne "Source :"
    qui se trouve historiquement en fin de fichier.
    """

    metadonnees = {
        "titre": "",
        "source": "",
        "categorie": "",
        "mots_cles": [],
        "verifie_le": "",
        "a_verifier": "",
    }

    lignes_corps = []

    for ligne in contenu.splitlines():
        ligne_propre = ligne.strip()

        if ":" in ligne_propre:
            cle_brute, valeur = ligne_propre.split(":", 1)
            cle = normaliser(cle_brute.strip())

            if cle in CHAMPS_ENTETE:
                champ = CHAMPS_ENTETE[cle]
                valeur = valeur.strip()

                if champ == "mots_cles":
                    metadonnees["mots_cles"] = [
                        mot.strip()
                        for mot in valeur.split(",")
                        if mot.strip()
                    ]
                else:
                    metadonnees[champ] = valeur

                continue

        lignes_corps.append(ligne)

    metadonnees["texte"] = "\n".join(lignes_corps).strip()

    return metadonnees


def decouper(texte, taille_mots=None, chevauchement=None):
    """Decoupe un texte en passages en respectant les paragraphes.

    Un paragraphe court est accumule avec les suivants jusqu'a
    atteindre la taille cible. Un paragraphe d'avertissement
    (commencant par "Attention") est rattache au paragraphe precedent
    pour ne jamais separer une regle de son exception.
    """

    if taille_mots is None:
        taille_mots = config.TAILLE_CHUNK_MOTS

    if chevauchement is None:
        chevauchement = config.CHEVAUCHEMENT_MOTS

    paragraphes_bruts = [
        paragraphe.strip()
        for paragraphe in texte.split("\n\n")
        if paragraphe.strip()
    ]

    if not paragraphes_bruts:
        return []

    # Une ligne isolee tres courte ("Attention", "Exception") est un
    # intertitre : on la fusionne avec le paragraphe qui la suit pour
    # qu'un avertissement ne soit jamais coupe de son contenu.
    paragraphes = []

    for paragraphe in paragraphes_bruts:
        if paragraphes and len(paragraphes[-1].split()) <= 3:
            paragraphes[-1] = paragraphes[-1] + "\n\n" + paragraphe
        else:
            paragraphes.append(paragraphe)

    passages = []
    courant = []
    nombre_mots = 0

    for paragraphe in paragraphes:
        mots = paragraphe.split()

        avertissement = normaliser(paragraphe).startswith(
            ("attention", "warning", "exception")
        )

        depassement = nombre_mots + len(mots) > taille_mots

        if depassement and courant and not avertissement:
            passages.append("\n\n".join(courant))

            mots_precedents = " ".join(courant).split()
            report = mots_precedents[-chevauchement:] if chevauchement else []

            courant = [" ".join(report)] if report else []
            nombre_mots = len(report)

        courant.append(paragraphe)
        nombre_mots += len(mots)

    if courant:
        passages.append("\n\n".join(courant))

    return passages


def charger_documents(dossier=None):
    """Lit tous les fichiers .txt du dossier data et les decoupe."""

    if dossier is None:
        dossier = config.DOSSIER_DATA

    dossier = Path(dossier)
    documents = []

    for chemin in sorted(dossier.glob("*.txt")):
        contenu = chemin.read_text(encoding="utf-8")
        metadonnees = analyser_entete(contenu)

        if not metadonnees["texte"]:
            continue

        document = Document(
            nom=chemin.name,
            titre=metadonnees["titre"],
            source=metadonnees["source"],
            categorie=metadonnees["categorie"],
            mots_cles=metadonnees["mots_cles"],
            verifie_le=metadonnees["verifie_le"],
            texte=metadonnees["texte"],
            a_verifier=metadonnees["a_verifier"],
        )

        for indice, texte_passage in enumerate(decouper(document.texte)):
            document.passages.append(
                Passage(
                    nom_document=document.nom,
                    titre=document.titre,
                    source=document.source,
                    categorie=document.categorie,
                    mots_cles=document.mots_cles,
                    verifie_le=document.verifie_le,
                    texte=texte_passage,
                    a_verifier=document.a_verifier,
                    indice=indice,
                )
            )

        documents.append(document)

    return documents


def charger_passages(dossier=None):
    """Retourne la liste a plat de tous les passages du corpus."""

    return [
        passage
        for document in charger_documents(dossier)
        for passage in document.passages
    ]


def points_a_verifier(dossier=None):
    """Doutes signalés dans le corpus via le champ 'À-vérifier'.

    Volontairement séparé de valider_corpus() : un doute n'est pas une
    erreur de saisie et ne doit pas faire échouer l'intégration
    continue. Il doit en revanche rester visible, sinon il se perd.

    Cas typique : une source officielle a changé de barème et personne
    n'a encore tranché. Marquer le doute vaut mieux que le laisser
    dans le corpus sans trace, puisque le contrôle d'ancrage laissera
    passer un chiffre présent dans le document, juste ou faux.
    """

    return [
        {
            "document": document.nom,
            "note": document.a_verifier,
            "verifie_le": document.verifie_le,
        }
        for document in charger_documents(dossier)
        if document.a_verifier
    ]


def valider_corpus(dossier=None):
    """Controle qualite du corpus. Retourne une liste de problemes.

    Aucun appel reseau : cette fonction tourne sans Ollama, ce qui
    permet de la lancer en integration continue.
    """

    problemes = []
    documents = charger_documents(dossier)

    if not documents:
        problemes.append("Aucun document trouve dans le dossier data.")
        return problemes

    mots_cles_vus = {}

    for document in documents:
        if not document.titre:
            problemes.append(f"{document.nom} : champ 'Titre' manquant.")

        if not document.source:
            problemes.append(f"{document.nom} : champ 'Source' manquant.")

        elif not document.source.startswith("http"):
            problemes.append(
                f"{document.nom} : la source n'est pas une URL."
            )

        if not document.mots_cles:
            problemes.append(
                f"{document.nom} : aucun mot-cle. Le document ne pourra "
                "etre retenu que par similarite semantique."
            )

        if not document.verifie_le:
            problemes.append(
                f"{document.nom} : champ 'Verifie-le' manquant. Une regle "
                "administrative sans date de verification ne devrait pas "
                "etre servie a un etudiant."
            )

        if not document.passages:
            problemes.append(f"{document.nom} : aucun passage genere.")

        for mot in document.mots_cles:
            cle = normaliser(mot)
            if cle in mots_cles_vus and mots_cles_vus[cle] != document.nom:
                problemes.append(
                    f"Mot-cle ambigu '{mot}' : present dans "
                    f"{mots_cles_vus[cle]} et {document.nom}."
                )
            mots_cles_vus[cle] = document.nom

    return problemes


if __name__ == "__main__":
    import sys

    documents = charger_documents()

    print(f"\n{len(documents)} document(s) charge(s) :\n")

    for document in documents:
        print(
            f"  {document.nom} - {len(document.passages)} passage(s) "
            f"- {len(document.mots_cles)} mot(s)-cle "
            f"- verifie le {document.verifie_le or 'jamais'}"
        )

    doutes = points_a_verifier()

    if doutes:
        print(f"\n{len(doutes)} point(s) marque(s) a verifier :\n")
        for doute in doutes:
            print(f"  - {doute['document']} : {doute['note']}")
        print(
            "\n  Ces points ne font pas echouer la validation, mais "
            "doivent etre tranches\n  par un humain avant tout usage "
            "reel."
        )

    problemes = valider_corpus()

    if problemes:
        print(f"\n{len(problemes)} probleme(s) detecte(s) :\n")
        for probleme in problemes:
            print(f"  - {probleme}")
        sys.exit(1)

    print("\nCorpus valide.")
