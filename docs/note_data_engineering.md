# Note — Data Engineering

## 1. Métadonnées dans les documents, plus dans le code

Les mots-clés vivaient dans un dictionnaire `MOTS_THEMES` codé en dur au milieu de `recherche.py`. Ajouter un quatrième document imposait de modifier du Python, ce qui rendait l'extension du corpus dépendante de la personne qui connaît le code.

Ils sont maintenant dans l'en-tête de chaque `.txt` :

```text
Titre : Renouvellement du titre de séjour étudiant
Catégorie : titre_sejour
Mots-clés : renouvellement, renouveler, expiration, renew, residence permit
Vérifié-le : 2026-09-18
Source : https://www.service-public.fr/particuliers/vosdroits/F2231

<corps du document>
```

L'analyseur (`corpus.analyser_entete`) accepte les variantes française et anglaise des noms de champ, avec ou sans accents. Ajouter un document se réduit à déposer un fichier.

Point vérifié par un test : l'en-tête est retiré du texte envoyé au modèle. Une ligne `Source :` laissée dans le corps aurait donné une URL au modèle alors que le prompt lui interdit d'en produire.

## 2. Champ `Vérifié-le`

Nouveau champ, et c'est le plus important du lot. Une règle administrative sans date de vérification ne devrait pas être servie à un étudiant : le corpus est extrait manuellement de Service-Public et rien ne garantit qu'il n'a pas changé depuis.

La date est remontée par l'API (`verifie_le`) et affichée sous le lien source dans l'interface. `valider_corpus()` signale un document sans date.

Les dates actuelles correspondent à la révision de ce corpus, **pas** à une revérification ligne à ligne contre Service-Public. À refaire avant toute utilisation réelle.

## 3. Découpage en passages

`corpus.decouper()` regroupe les paragraphes jusqu'à une taille cible (120 mots par défaut), avec chevauchement.

Une règle spécifique a été ajoutée après un bug trouvé pendant les tests : une ligne d'intertitre très courte — typiquement `Attention` — est fusionnée avec le paragraphe qu'elle introduit. Sans cela, le découpage plaçait « Attention » à la fin d'un passage et le droit de régularisation de 180 € dans le suivant, **séparant une règle de son exception**. Une réponse sur le renouvellement pouvait alors omettre l'exception hors délai. Un test vérifie que le délai (4 mois) et l'exception (180 €) restent dans le même passage.

Avec les documents actuels, chaque document tient en un passage. Le découpage devient utile dès qu'un texte plus long est ajouté, ce qui est le cas de la plupart des pages Service-Public.

## 4. Validation du corpus

```powershell
python src/corpus.py
```

Aucun appel réseau, donc exécutable en intégration continue. Contrôles :

- titre, source et date de vérification présents ;
- la source est bien une URL ;
- au moins un mot-clé (sans mot-clé, le document ne peut être retenu que par le seuil sémantique haut) ;
- au moins un passage généré ;
- **mot-clé ambigu** : un même mot-clé attribué à deux documents différents est signalé. C'est le genre d'erreur qui dégrade silencieusement la recherche quand le corpus grossit.

Le workflow GitHub Actions lance cette validation à chaque push et échoue si un problème est détecté.

## 5. Cache d'embeddings

Le cache précédent vivait en mémoire de processus. Avec `uvicorn --reload`, chaque sauvegarde de fichier redémarrait le processus et relançait le calcul de tous les embeddings du corpus.

Le nouveau cache écrit dans `.cache/embeddings/<empreinte>.json`. L'empreinte est un hash du texte **et** du nom du modèle : modifier un document ou changer de modèle d'embedding invalide l'entrée automatiquement, sans manipulation manuelle — un piège classique quand on teste plusieurs modèles.

Un fichier de cache corrompu est ignoré et recalculé, plutôt que de faire remonter une exception. `.cache/` est dans `.gitignore`.

## 6. Corpus élargi à six documents

Trois sujets ont été ajoutés, chacun rédigé à partir de sa source officielle consultée le 18/09/2026 :

| Document | Source | Pourquoi ce sujet |
|---|---|---|
| `securite_sociale_etudiant.txt` | ameli.fr | Démarche obligatoire dès l'arrivée, et une source fréquente d'inquiétude puisque beaucoup d'étudiants croient devoir payer |
| `logement_caf.txt` | caf.fr | Règle modifiée au 1er juillet 2026, la plus susceptible d'être mal connue |
| `travail_etudiant.txt` | service-public.gouv.fr | Le plafond de 964 heures conditionne le renouvellement du titre de séjour |

Les textes sont des synthèses rédigées à partir des sources, pas des copies intégrales. Chaque document porte l'URL de sa source, que l'interface affiche pour que l'étudiant puisse remonter au texte complet.

### Le cas CAF : pourquoi la date de vérification compte

La règle d'aide au logement a changé le 1er juillet 2026 : un étudiant extracommunautaire titulaire d'un titre « poursuite d'études » n'y a désormais droit que s'il perçoit une bourse sur critères sociaux, sauf s'il travaille, est en apprentissage, est réfugié ou apatride, ou est conjoint d'un étudiant extracommunautaire.

Ce changement est postérieur à la rédaction de la version précédente du projet. C'est exactement ce contre quoi le champ `Vérifié-le` protège : sans lui, rien ne distingue un document à jour d'un document décrivant un état du droit périmé.

## 7. Le champ `À-vérifier`

Nouveau champ optionnel, pour consigner un doute identifié mais non tranché. Affiché par `python src/corpus.py`, journalisé au démarrage de l'API, retourné par `/health`, et **sans effet sur la réussite de la validation** : un doute n'est pas une erreur de saisie et ne doit pas bloquer l'intégration continue.

Il existe pour une raison précise : le contrôle d'ancrage accepte tout chiffre présent dans le document, juste ou faux. Il protège contre un modèle qui invente, pas contre un corpus erroné. Un chiffre que personne n'a confirmé a donc besoin d'un marqueur distinct.

**Un doute est signalé aujourd'hui.** `renouvellement_etudiant.txt` mentionne une taxe et un droit de timbre de 100 €. Plusieurs sources 2026 décrivent un total de 150 € pour les étudiants (100 € de taxe et 50 € de droit de timbre). Le délai de dépôt (4 à 2 mois) et la majoration de 180 € hors délai ont été confirmés. À trancher sur service-public.fr, puis corriger le document ou retirer le marqueur.

## 8. Séparation des mots-clés

Avec six documents, le risque de collision augmente. Deux garde-fous :

- `valider_corpus()` signale tout mot-clé attribué à deux documents différents ;
- un test vérifie qu'avec des embeddings factices — donc aucun signal sémantique — le seul signal lexical route correctement les six sujets vers leur document. Les jeux de mots-clés sont donc bien séparés.

## 9. Ce qu'il reste à faire sur les données

- **Trancher le doute** sur la taxe de renouvellement.
- **Étendre encore.** Trois sujets voisins déclenchent aujourd'hui l'abstention, à juste titre : compte bancaire, logement CROUS, déclaration d'impôts.
- **Faire échouer le build** quand un document dépasse une ancienneté donnée — le champ `Vérifié-le` existe, la règle reste à écrire. Le cas CAF montre qu'une règle peut changer en quelques mois.
- **Générer les mots-clés** au lieu de les écrire à la main, une fois le corpus assez grand pour que l'écriture manuelle devienne le goulot d'étranglement.
