# Note — AI Researcher

## 1. Choix de l'approche

L'architecture RAG reste le bon choix face à un fine-tuning, pour trois raisons propres à ce domaine :

- **Fraîcheur.** Les montants et délais administratifs changent (877,5 € par mois, timbre de 100 €, régularisation de 180 €). Mettre à jour un fichier `.txt` coûte quelques minutes ; ré-entraîner un modèle à chaque révision d'un barème est hors de portée du projet.
- **Traçabilité.** Un étudiant doit pouvoir remonter à la source officielle. Un modèle fine-tuné produit une affirmation sans document à citer.
- **Taille du modèle.** Qwen2.5 3B n'a pas la capacité de mémoriser fidèlement une réglementation. Lui fournir le texte au moment de la question est le seul moyen réaliste d'obtenir des chiffres exacts.

Le fine-tuning léger (LoRA) resterait pertinent pour imposer un format de réponse si le prompt seul ne suffisait plus. Ce n'est pas le cas aujourd'hui : les défauts observés portent sur l'exactitude, pas sur la forme.

## 2. Refonte de la règle d'acceptation

### Le problème trouvé dans le code

`SEUIL_SEMANTIQUE_SANS_LEXICAL = 0.65` était défini et **jamais lu**. La fonction `est_pertinent()` se réduisait à `score_lexical > 0`. L'ensemble du dispositif sémantique ne servait qu'au classement ; la décision d'accepter ou de s'abstenir reposait entièrement sur une liste de mots-clés écrite à la main.

Deux conséquences, toutes deux listées comme limitations dans le README précédent sans que le lien avec ce code mort soit fait :

- une reformulation valide sans mot-clé prévu était **toujours** rejetée ;
- un mot-clé trompeur dans une question hors sujet était **toujours** accepté.

### La règle retenue

La décision porte sur la similarité sémantique seule, avec deux seuils :

| Cas | Seuil | Rôle |
|---|---|---|
| Mot-clé présent | bas (0,35) | Garde-fou contre le mot-clé trompeur |
| Aucun mot-clé | haut (0,72) | Rattrape les reformulations non prévues |

Le score final pondéré (0,85 / 0,15) continue de classer les passages mais ne décide plus rien. Un seuil posé sur un mélange de deux échelles différentes n'a pas d'interprétation claire : on ne sait pas dire ce que « 0,30 » signifie. Un cosinus, si.

Les candidats sont parcourus dans l'ordre de classement et le premier accepté est retenu, au lieu de s'abstenir dès que le passage classé premier échoue de peu.

## 3. Contrôle d'ancrage plutôt que correctifs ponctuels

La version précédente traitait deux défauts constatés par deux correctifs spécifiques : une réponse entièrement pré-écrite pour le scénario VLS-TS, et un remplacement de chaîne pour une formulation ambiguë. Ces correctifs partagent un défaut de fond : ils ne couvrent que les cas déjà rencontrés, et la réponse pré-écrite fait paraître le système meilleur qu'il n'est puisqu'elle court-circuite le modèle.

Le remplacement est un contrôle général : **tout chiffre d'une réponse doit apparaître dans le document source**. Ce contrôle vise le mode d'échec dominant d'un modèle de 3 milliards de paramètres sur ce type de tâche — inventer ou recalculer un montant, un délai. Il s'applique aussi à des questions jamais testées, ce qu'aucun correctif ponctuel ne fait.

Trois propriétés importantes :

- **Multilingue.** Le document est en français, la réponse en anglais : `4 months` et `4 mois` sont reconnus comme la même durée, `877,5 €` et `877.5 EUR` comme le même montant.
- **Conservateur.** En cas de chiffre non justifié, le système retient la réponse et renvoie à la source officielle. Sur une règle administrative, un délai faux est pire qu'une absence de réponse.
- **Signalé à l'utilisateur.** L'interface indique qu'une réponse a été retenue, plutôt que de masquer l'incident.

Ce que le contrôle **n'attrape pas**, et qu'il ne faut pas prétendre couvrir : une étape de procédure inventée sans chiffre, un contresens sur l'applicabilité d'une exception, une omission. Ce sont les prochains chantiers.

### Une leçon de l'élargissement du corpus

Le contrôle avait été écrit pour un corpus qui ne parlait que de mois et d'euros. Il ne reconnaissait pas les durées en **heures**. Dès l'ajout du document sur le travail étudiant, entièrement construit autour d'un plafond de 964 heures, une réponse affirmant « 1200 hours per year » passait sans être détectée.

Le trou existait depuis le début ; il était invisible faute d'un document qui l'expose. C'est un argument direct en faveur de l'élargissement du corpus **avant** la soutenance plutôt qu'après : chaque nouveau sujet teste les garde-fous sur un terrain qu'ils n'avaient pas rencontré.

Corollaire pour la suite : à chaque nouveau document, se demander quelles unités il introduit et si le contrôle les couvre. Les surfaces en m² (logement) et les pourcentages de remboursement sont les prochains candidats.

## 4. Protocole d'évaluation

Trois niveaux, du moins cher au plus coûteux :

1. **Hors ligne, sans modèle** (`tests/test_hors_ligne.py`, 42 assertions) : métadonnées, découpage, score lexical, règle d'acceptation, cache, contrôle d'ancrage. Tourne en intégration continue à chaque push.
2. **Recherche, avec modèles** (`tests/test_recherche.py`, 21 cas) : quel document est sélectionné, ou abstention. Résultats ventilés par famille de cas, échecs gradués — répondre à tort est signalé `GRAVE`, ne pas répondre est signalé `manque`.
3. **Calibration** (`evaluation/calibrer_seuils.py`) : balayage des deux seuils, en privilégiant les configurations produisant zéro mauvaise sélection.

### Sur le 11/11 précédent

Ce résultat était mécaniquement flatteur. Les questions de test contenaient toutes un mot-clé de la liste, et la présence d'un mot-clé *était* le critère d'acceptation. Le test vérifiait surtout que la liste couvrait des questions écrites à partir de cette liste.

Le jeu élargi ajoute les trois familles qui sondent les vraies faiblesses : reformulations sans mot-clé, mots-clés trompeurs, sujets administratifs voisins. **Un score inférieur à 100 % est attendu et se défend mieux en soutenance qu'un 11/11 ininterprétable.**

## 5. Limite assumée

Les seuils 0,35 et 0,72 sont des valeurs de départ prudentes. Je ne dispose pas des modèles pour observer la distribution réelle des cosinus produits par `nomic-embed-text` sur ce corpus ; choisir un seuil sans cette distribution serait une invention. D'où l'outil de calibration plutôt qu'une valeur affirmée.
