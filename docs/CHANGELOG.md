# Changelog

## Version 3.0.0 — conversation, profil étudiant et streaming

Les points marqués **[comportement]** changent ce que l'assistant répond. Les points marqués **[API]** cassent la compatibilité avec les clients de la version 2.

### Mémoire conversationnelle

- Nouveau module `src/sessions.py` : une session (UUID) regroupe le profil et l'historique. Elle est stockée en mémoire, expire après 30 minutes d'inactivité (`STUDENTIA_TTL_SESSION`) et garde au plus 40 messages (`STUDENTIA_HISTORIQUE_MAX`).
- Nouveaux endpoints `POST /nouvelle-session` et `GET /session/{session_id}`.
- `POST /question` accepte `session_id` et `historique` (liste de `{role, content}`). L'historique envoyé par le client fait foi, ce qui reconstruit une session perdue au redémarrage. Un identifiant inconnu n'est jamais réutilisé : le serveur en crée un nouveau.
- **[comportement]** Le modèle est appelé via `/api/chat` d'Ollama : prompt système, historique complet avec ses rôles, puis la question courante. Fenêtre de contexte portée à 8192 tokens (`STUDENTIA_NUM_CTX`).

### Profil étudiant

- Nouveau module `src/profil.py`. `POST /question` accepte `profil` : `{pays_origine, zone (UE|HORS_UE)}`. Le profil est conservé en session. La zone est déduite du pays si elle manque (liste UE + EEE + Suisse).
- **[comportement]** Profil UE : les passages de catégorie `titre_sejour` sont exclus **avant** la sélection (nouveau paramètre `categories_exclues` de `rechercher_document()`, sans effet sur l'ancien comportement).
- **[comportement]** Ressortissant algérien : le contexte commence par le drapeau `[DRAPEAU carte_pluriannuelle_exclue]`, qui interdit de présenter la carte pluriannuelle comme accessible (accord franco-algérien de 1968).
- **[comportement]** Pays inconnu et question sur le titre de séjour : une question de clarification est renvoyée **avant** toute recherche. La détection est lexicale : mots-clés des documents `titre_sejour` et quelques expressions fixes.

### Streaming

- **[API]** `POST /question` répond désormais en `text/event-stream` (SSE) au lieu d'un JSON. Événements : `session`, `meta`, `token`, puis un seul événement terminal `done`, `clarification` ou `error`.
- **[comportement]** Le contrôle d'ancrage s'exécute sur la réponse complète, après le flux. En cas d'échec, l'événement final est `error` (type `abstention_verification`) avec le message d'abstention, et c'est ce message, pas la réponse rejetée, qui entre dans l'historique.
- **[API]** Ollama indisponible ne donne plus un HTTP 503 : le statut est 200 et le flux se termine par un événement `error` (`ollama_indisponible` ou `generation_indisponible`).
- Limite assumée : l'étudiant voit la réponse avant le contrôle. Un chiffre inventé peut rester affiché quelques secondes avant d'être remplacé.

### Nouveau prompt système

- **[comportement]** `PROMPT_SYSTEME` remplace l'ancien prompt : réponses **toujours en français**, règles de profil, mémoire de conversation, règle absolue sur les chiffres, format structuré (📋 📅 💶 ⚠️ 📎).
- Chaque passage du contexte est précédé de son titre, de sa date de vérification et de sa catégorie, pour alimenter la ligne `📎 Source`.
- **[comportement]** Les messages d'abstention sont en français.
- `verification.py` n'a pas été modifié. Il signale toujours une réponse « en français », puisqu'il a été écrit quand l'anglais était attendu. Cet avertissement est désormais filtré dans `assistant.finaliser()`.

### Frontend

- Formulaire de profil (pays) à remplir avant la première question, modifiable ensuite. Une question posée avant le profil, ou ayant déclenché une clarification, est relancée automatiquement.
- Session créée à l'ouverture de la page. L'identifiant et l'historique restent en mémoire JavaScript, sans `localStorage`.
- Affichage en temps réel des tokens (effet machine à écrire). Le texte final nettoyé remplace ensuite le flux. `EventSource` ne gérant que les requêtes GET, le flux est lu avec `fetch()` et un `ReadableStream`.
- Textes de l'interface liés à la conversation passés en français.

### Corpus (12 → 15 documents, vérifiés le 25/11/2026)

Revérification sur les fiches officielles Service-Public F2231 (vérifiée le 01/08/2026), F2215, F17319, F2229 et F21841.

- **[comportement] Erreur corrigée** : `renouvellement_etudiant.txt` indiquait une taxe de **150 €** pour le renouvellement. Le bon montant est **100 €** (taxe + droit de timbre) pour la carte étudiant d'1 an ; 150 € correspond à la carte pluriannuelle. Le doute `À-vérifier` qui portait sur ce montant est levé.
- **[comportement]** `validation_vls_ts.txt` : ajout du montant de la taxe de validation (100 €) et de la durée de validité du VLS-TS (4 mois à 1 an).
- **[comportement]** `carte_sejour_pluriannuelle.txt` réécrit d'après F2231. La durée est de 2 à 4 ans et la carte coûte 150 €. Conditions : inscription, ressources, caractère réel et sérieux des études. **Retiré** : l'exigence d'un niveau A2 de français et la mention des principes de la République, absentes de la fiche officielle, ainsi que deux affirmations non sourcées (renouvellement à chaque nouveau cycle, signalement d'un changement de formation).
- `ressources_etudiant.txt` : 877,5 € confirmé. Ajout des justificatifs acceptés et de l'appréciation au renouvellement.
- **Nouveaux documents**, pour que les règles de profil s'appuient sur le corpus :
  - `etudiant_algerien.txt` (`titre_sejour`) : certificat de résidence « étudiant » d'1 an, accord de 1968, pas de carte pluriannuelle, travail limité à 50 %. Marqué `À-vérifier` : la fiche F2215 est en cours de mise à jour (décret du 26 octobre 2026) et sa section étudiant n'a été lue qu'en partie.
  - `sejour_etudiant_ue.txt` (catégorie `sejour_ue`, donc **pas** exclu pour un profil UE) : pas de titre de séjour obligatoire, trois conditions de séjour au-delà de 3 mois.
  - `changement_statut_etudiant.txt` (`titre_sejour`) : carte « recherche d'emploi ou création d'entreprise » et passage au statut salarié. Couvre les questions sur l'après-études.
- `bourse_crous.txt` : nouveau doute `À-vérifier`. Le calendrier du DSE est reconfirmé, mais les montants 2026-2027 par échelon et l'extension du repas à 1 € n'ont pas pu être confirmés.
- Validation : aucun mot-clé ambigu entre documents. Le mot-clé `aps` a été écarté, car la détection de clarification (par sous-chaîne) l'aurait trouvé dans des mots comme « laps ».

### Corrections après le premier essai réel (qwen2.5:3b + nomic-embed-text)

Constat : l'assistant s'abstenait sur **toutes** les questions, y compris les questions suggérées par l'interface.

- **[comportement] Cache d'embeddings pollué par les tests (bug antérieur, aggravé).** Les tests hors ligne écrivaient leurs vecteurs factices (dimension 32) dans le vrai cache `.cache/embeddings`, sous le nom du vrai modèle. Au démarrage, l'API relisait ces vecteurs. La similarité avec une question en dimension 768 valait 0 (`similarite_cosinus` renvoie 0 si les dimensions diffèrent), d'où une abstention systématique. 42 entrées sur 47 étaient factices, car chaque document ajouté ou modifié avait été vectorisé pour la première fois par les tests.
  - Les tests utilisent désormais un dossier temporaire. Une vérification contrôle qu'ils n'écrivent rien dans le vrai cache.
  - `recherche.py` détecte un vecteur de dimension incohérente, le signale dans les journaux et le recalcule.
  - Les 43 entrées invalides du cache local ont été supprimées.
- **[comportement]** `STUDENTIA_NUM_PREDICT` passe de 300 à 800 : les réponses au format structuré étaient coupées à 300 tokens.
- **[comportement]** Rappel ajouté après la question (`CONSIGNE_QUESTION_COURANTE`), sans modifier le prompt système. Avec l'historique, le modèle recopiait la réponse précédente et ses chiffres, et le contrôle d'ancrage retenait alors une réponse pourtant juste sur les ressources. Il écrivait aussi « [Sujet] » tel quel et inventait des étapes (préfecture, numéro de sécurité sociale). Une première version du rappel, qui citait `[QUESTION]` et `[CONTEXTE]`, faisait recopier la question et tous les passages. La version retenue ne cite aucun balisage, et un test le vérifie.
- `validation_vls_ts.txt` : mot-clé « valide mon » ajouté. « comment je valide mon titre de séjour » ne correspondait à aucun mot-clé (`valider` ≠ `valide`) et restait sous le seuil sémantique strict.
- Vérifié sur l'API réelle, avec la séquence de questions de l'essai dans une même session. Les 4 questions reçoivent une réponse ancrée dans le bon document (100 €, 4 à 2 mois, 180 €, 877,5 €), sans étape inventée ni recopie.

### Profil sans « situation », question de précision

- **[comportement]** Le champ « situation » (première arrivée, renouvellement, changement de statut) est retiré du formulaire, de l'API et de `profil.py` : les questions des étudiants sont assez précises.
- **[comportement]** Le prompt système est modifié sur deux points seulement. « (pays, situation) » devient « (pays) », et une ligne nouvelle autorise **une** question de précision quand la réponse dépend d'une information absente (par ex. première demande ou renouvellement ?).
- `assistant.question_pour_recherche` : quand l'assistant vient de poser une question, la réponse courte de l'étudiant (« renouvellement ») est recherchée avec la question qui l'a provoquée.

### Sélection des paramètres et jeu de questions

- `evaluation/calibrer_seuils.py` balaie désormais **3 paramètres** (poids sémantique, seuil avec mot-clé, seuil sans mot-clé), soit 448 combinaisons. Les questions sont coupées en deux parties fixes par hachage : calibration (61) et test (29). La meilleure combinaison est choisie sur la calibration, puis évaluée une seule fois sur la partie test, à côté des valeurs actuelles.
- Jeu de `tests/test_recherche.py` : **30 → 90 questions**. Les 15 documents sont couverts (famille `corpus_15`), avec 16 reformulations sans mot-clé, 7 sujets voisins absents du corpus et 5 nouveaux mots-clés trompeurs. Les 3 anciens `sujet_voisin` (banque, CROUS, impôts) attendaient une abstention alors que ces sujets sont couverts depuis la version 2 ; ils attendent désormais leur document.
- **Résultat du 26/11/2026 : 69/90 (76,7 %).** Sur la partie test, la combinaison retenue (0,85 / 0,45 / 0,75) fait **20/29, exactement comme les valeurs actuelles** : la configuration n'est pas modifiée. Aucune des 448 combinaisons n'élimine les mauvaises sélections. Elles viennent de mots-clés d'un seul mot (`renouveler`, `banque`, `mutuelle`, `valider` : 6 pièges sur 8 échouent) et de documents voisins confondus (CEAM / sécurité sociale, CAF / bourse), pas des seuils.

### Mots-clés génériques et question de précision

- **[comportement]** Mots-clés d'un seul mot retirés : `renouveler`, `renew`, `banque`, `banking`, `mutuelle`, `medecin`, `sante`, `doctor`, `valider`, `validation`, `validate`, `salarie`, `boursier`. Ils sont remplacés par des formes composées (`renouveler ma carte`, `valider mon visa`, `frais de medecin`, `etudiants boursiers`…). `carte europeenne d'assurance maladie` est ajouté à la CEAM. Le mot-clé `valide mon`, ajouté juste avant, est aussi retiré : il aurait accepté « valide mon semestre ».
- Résultat sur les 90 questions : **69 → 77/90**. Les pièges passent de **2/8 à 8/8** et les mauvaises sélections de 14 à 4. Sur la partie test de la calibration : **20/29 → 25/29** avec les paramètres par défaut, toujours inchangés. Réserve : une partie des formes composées a été choisie en regardant les questions en échec.
- **[comportement]** Quand la recherche ne trouve rien pour une question sur le titre de séjour (étudiant hors UE), l'assistant pose une question de précision fixe (validation du VLS-TS, renouvellement, carte pluriannuelle, après les études) au lieu de s'abstenir. Elle passe par l'événement `clarification` existant et n'est jamais posée deux fois de suite. Une question hors sujet reste une abstention. Vérifié en réel : « Combien coûte mon titre de séjour ? » → question de précision → « le renouvellement » → 100 €, plus 180 € en cas de retard.

### Correspondance des mots-clés par mot entier

- **[comportement]** Les mots-clés étaient cherchés comme sous-chaînes. `work` correspondait à « paper**work** », `rent` à « pa**rent**s » et `bourse` à « rem**bourse** », ce qui expliquait 3 des 4 dernières mauvaises sélections. `recherche.contient_mot()` exige désormais un mot entier (pluriel en s/x admis). `profil.porte_sur_titre_sejour()` l'utilise aussi.
- 90 questions : toujours 77/90, mais les mauvaises sélections passent de **4 à 1** (les trois autres deviennent des abstentions). La dernière (« Combien dois-je prouver que je gagne… ») ne relève pas d'un reclassement : le bon document n'est pas dans les 5 premiers.

### Essai non retenu : reclassement par le modèle

- Essai du 26/11/2026 : quand les deux meilleurs documents étaient à moins d'un écart donné, `qwen2.5:3b` choisissait parmi les 3 premiers (ou « aucun »). L'écart était choisi sur la calibration (0,01 à 0,08), puis testé une seule fois sur la partie test.
- Calibration : 52/61 pour tous les écarts, comme sans reclassement. Partie test : **25/29 dans les deux cas**. À l'écart 0,08, 42 questions sur 90 sont incertaines, mais 4 décisions seulement changent, aucune en mieux : 2 bonnes réponses deviennent des abstentions (le modèle répond « 0 ») et 1 bonne réponse devient mauvaise. Souvent, le document choisi par le modèle n'atteint pas le seuil sémantique, et le choix initial est conservé.
- Pas de gain, donc le code a été retiré.

### Docker

- `Dockerfile` : `PYTHONPATH=/app` corrigé en `/app/src`. Les modules de `src/` s'importent par leur nom seul, et l'API ne démarrait pas dans le conteneur.
- `docker-compose.yml` : le healthcheck d'Ollama utilisait `curl`, absent de l'image `ollama/ollama`. Il ne passait donc jamais, et ni `ollama-init` ni l'API ne démarraient. Il est remplacé par `ollama list`.

### Lancement

```bash
PYTHONPATH=src uvicorn src.api:app --reload
```

### Tests

- Suite hors ligne : **59 → 99 assertions**. Les nouvelles couvrent le prompt système, l'organisation des messages, le filtrage UE, le drapeau algérien, le partage du profil entre deux questions d'une même session, la clarification, les événements SSE et l'échec d'ancrage après le flux. La génération en flux est injectable (`assistant.definir_fonction_flux`).
- **Échec antérieur, non corrigé :** « le document attendu est premier grâce au signal lexical » échouait déjà avant cette version. Avec le corpus élargi, les embeddings factices donnent à `carte_sejour_pluriannuelle` un score sémantique (0,266) supérieur à celui de `renouvellement_etudiant` (0,105).
- Les 53 assertions annoncées pour la version 2.1.0 étaient en réalité 59 au moment de cette mise à jour.

---

## Version 2.1.0 — élargissement du corpus

### Trois documents ajoutés

Sujets vérifiés le 18/09/2026 contre leur source officielle :

| Document | Source | Points clés |
|---|---|---|
| `securite_sociale_etudiant.txt` | ameli.fr | Affiliation obligatoire et **gratuite** hors UE sur etudiant-etranger.ameli.fr ; numéro provisoire immédiat ; CEAM suffisante pour les ressortissants UE/EEE/Suisse |
| `logement_caf.txt` | caf.fr | **Changement du 1er juillet 2026** : un étudiant extracommunautaire « poursuite d'études » n'a droit aux aides au logement que s'il perçoit une bourse sur critères sociaux ; exceptions listées |
| `travail_etudiant.txt` | service-public.gouv.fr (F2713) | Plafond de **964 heures par an** (60 % de la durée légale, art. R. 5221-26) ; autorisation de travail au-delà ; déclaration nominative de l'employeur ; régime algérien distinct |

La règle CAF de juillet 2026 est postérieure à la rédaction de la version précédente. C'est l'illustration de pourquoi le corpus a besoin d'une date de vérification : sans elle, rien ne signale qu'un document décrit un état du droit périmé.

### Nouveau champ `À-vérifier`

Champ optionnel dans l'en-tête d'un document, pour consigner un doute identifié mais non tranché. Il est affiché par `python src/corpus.py`, journalisé au démarrage de l'API et retourné par `/health`, **sans faire échouer la validation** : un doute n'est pas une erreur de saisie.

Motivation : le contrôle d'ancrage accepte tout chiffre présent dans le document, juste ou faux. Un chiffre que personne n'a confirmé a donc besoin d'un marqueur propre.

**Un doute est actuellement signalé.** `renouvellement_etudiant.txt` indique une taxe et un droit de timbre de 100 €, alors que plusieurs sources 2026 décrivent un total de 150 € pour les étudiants (100 € de taxe + 50 € de droit de timbre). Le délai de dépôt (4 à 2 mois) et la majoration de 180 € hors délai ont été confirmés. **À trancher par un humain sur service-public.fr.**

### Correction dans le contrôle d'ancrage

**[comportement]** Le module de vérification ne reconnaissait pas les durées en **heures**. Le nouveau document sur le travail étudiant repose entièrement sur un plafond horaire : une réponse affirmant « 1200 hours per year » ou « about 20 hours per week » passait le contrôle sans être détectée. Les formes `964 heures`, `964 hours` et `964h` sont maintenant reconnues comme équivalentes.

Ce trou n'était pas visible tant que le corpus ne parlait que de mois et d'euros. C'est un argument concret en faveur de l'élargissement du corpus avant la soutenance.

### Tests

- Suite hors ligne : **42 → 53 assertions** (heures, formes abrégées, champ `À-vérifier`).
- Jeu de recherche : **21 → 29 cas**, avec une nouvelle famille `corpus_elargi` (6 cas).
- **Trois cas ont changé de réponse attendue.** Sécurité sociale, aide au logement CAF et travail pendant les études attendaient une abstention ; ces sujets sont désormais couverts. Un jeu de test doit suivre le corpus, sinon il cesse silencieusement de mesurer ce qu'il prétend mesurer.
- Les trois cas `sujet_voisin` ont été remplacés par des sujets réellement absents : compte bancaire, logement CROUS, déclaration d'impôts.

### Vérification du routage

Avec des embeddings factices (donc aucun signal sémantique), le seul signal lexical route correctement les 6 sujets vers leur document. Les jeux de mots-clés sont donc bien séparés — aucun mot-clé ambigu entre documents, ce que le validateur confirme également.

---

## Version 2.0.0 — révision complète

Cette version modifie le comportement du système, pas seulement son organisation. Les points marqués **[comportement]** changent ce que l'assistant répond.

### Corrections de bugs

- **[comportement]** `SEUIL_SEMANTIQUE_SANS_LEXICAL` était défini dans `recherche.py` mais jamais utilisé. L'acceptation reposait uniquement sur la présence d'un mot-clé écrit à la main, donc toute reformulation valide n'employant aucun mot-clé prévu était rejetée. Le seuil est maintenant réellement appliqué.
- **[comportement]** Le découpage séparait le bloc « Attention » (droit de 180 € hors délai) de la règle qu'il complète. Une réponse sur le renouvellement pouvait donc omettre l'exception. Une ligne d'intertitre courte est désormais fusionnée avec le paragraphe qu'elle introduit.
- **[comportement]** Si le passage classé premier échouait aux critères, le système s'abstenait, même si le second était clairement acceptable. Les candidats sont maintenant parcourus dans l'ordre et le premier accepté est retenu.
- Ollama arrêté provoquait une erreur HTTP 500 avec une trace Python. L'API renvoie maintenant un 503 et un message exploitable.
- `requirements.txt` était encodé en UTF-16, ce qui fait échouer `pip install -r` sur certaines configurations. Ré-encodé en UTF-8.
- Une entrée de cache corrompue faisait remonter une exception. Elle est maintenant ignorée et recalculée.

### Changements de conception

- **[comportement]** Le seuil sur le score final pondéré est remplacé par deux seuils sémantiques distincts (avec mot-clé : 0,35 ; sans mot-clé : 0,72). Mélanger deux signaux d'échelles différentes produisait un nombre difficile à interpréter et donc à calibrer. Le score pondéré sert désormais uniquement au classement.
- **[comportement]** Nouveau garde-fou : tout chiffre d'une réponse générée doit apparaître dans le document source, sinon la réponse est retenue et l'utilisateur renvoyé à la source officielle.
- **[comportement]** La réponse pré-écrite pour le scénario VLS-TS est désactivée par défaut (`STUDENTIA_REPONSES_CONTROLEES=true` pour la réactiver). Elle court-circuitait le modèle et masquait la qualité réelle du système.
- Les mots-clés passent du dictionnaire `MOTS_THEMES` codé en dur vers l'en-tête des fichiers `.txt`. Ajouter un document ne demande plus de modifier du Python.
- **[comportement]** Un mot-clé composé (« residence permit ») pèse davantage qu'un mot isolé dans le score lexical.
- La recherche porte sur des passages et non plus sur des fichiers entiers.
- Le cache d'embeddings est persistant sur disque, invalidé automatiquement par un changement de document ou de modèle.
- Toute la configuration passe par `src/config.py` et des variables d'environnement.
- Les `print()` de débogage dans le code de bibliothèque sont remplacés par du `logging`.

### Ajouts

- `src/config.py`, `src/corpus.py`, `src/cache_embeddings.py`, `src/verification.py`.
- `tests/test_hors_ligne.py` : 42 assertions sans modèle, exécutables en intégration continue.
- `evaluation/calibrer_seuils.py` : calibration des deux seuils sur le jeu de test.
- `.github/workflows/tests.yml`.
- Champ `Vérifié-le` dans les documents, affiché dans l'interface.
- `/health` interroge réellement Ollama et vérifie que les deux modèles sont installés.
- Frontend : signalement d'une réponse retenue par la vérification, date de vérification du document, adresse du backend configurable via `window.STUDENTIA_API`.

### Suppressions

- `src/recherche_lexicale.py` : module hérité, plus importé nulle part, avec des `print()` de débogage.
- `src/test_modele.py` : script de vérification manuelle d'Ollama, remplacé par `GET /health`.

### Tests

- Le jeu de recherche passe de 11 à 21 cas, avec trois familles ajoutées : reformulations sans mot-clé, mots-clés trompeurs, sujets administratifs voisins absents du corpus.
- **Attendez-vous à un score inférieur à 100 %.** Le 11/11 précédent était mécaniquement flatteur : les questions de test contenaient toutes un mot-clé de la liste qui servait de critère d'acceptation.

### À faire au premier lancement

1. `python evaluation/calibrer_seuils.py` sur la machine hébergeant Ollama — les seuils par défaut sont prudents, pas calibrés.
2. Appliquer les valeurs recommandées via `STUDENTIA_SEUIL_AVEC_LEXICAL` et `STUDENTIA_SEUIL_SANS_LEXICAL`.
3. `python tests/test_recherche.py` pour mesurer le point de départ réel.
