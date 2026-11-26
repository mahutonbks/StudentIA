# Note — Integration

## 1. Configuration par variables d'environnement

Tout ce qui était écrit en dur dans le code est regroupé dans `src/config.py` et surchargeable par variable d'environnement : adresse d'Ollama, noms des modèles, seuils, origines CORS, timeouts, niveau de log.

C'est ce qui rend le déploiement possible sans modifier le code. Le cas concret de ce projet — les modèles tournent sur une machine, le développement se fait sur une autre :

```powershell
$env:OLLAMA_HOST = "http://192.168.1.42:11434"
$env:STUDENTIA_CORS_ORIGINS = "http://192.168.1.42:5500"
python -m uvicorn api:app --app-dir src --host 0.0.0.0
```

L'ancienne configuration CORS n'autorisait que `http://127.0.0.1:5500`. Servir le frontend depuis la machine principale aurait provoqué un blocage CORS silencieux côté navigateur — une erreur qui se diagnostique mal en démonstration.

Côté frontend, l'adresse du backend se règle sans toucher à `app.js` :

```html
<script>window.STUDENTIA_API = "http://192.168.1.42:8000";</script>
<script src="app.js"></script>
```

## 2. Gestion des pannes

**Ollama arrêté.** `POST /question` remontait une exception non attrapée : HTTP 500 et trace Python dans la réponse. L'API renvoie maintenant **503** avec un message actionnable, et le frontend l'affiche tel quel plutôt qu'un « erreur HTTP 503 » générique. Deux chemins sont couverts séparément : échec à l'embedding (recherche) et échec à la génération. Dans le second cas, la source officielle est quand même renvoyée, puisque le document a été trouvé.

Les erreurs distinguent aussi « Ollama injoignable » de « modèle absent » : le message invite à lancer `ollama pull` dans le second cas.

**Question vide ou trop longue.** Validation par Pydantic (`min_length=1, max_length=500`), cohérente avec le `maxlength` du champ de saisie.

**Cache corrompu.** Ignoré et recalculé, plutôt que de faire échouer la requête.

Vérifié en conditions réelles avec le client de test FastAPI : Ollama injoignable → 503 ; `/health` → `degraded` ; question valide → 200 ; chiffre inventé par le modèle → réponse retenue ; question vide → 422.

## 3. `/health`

L'ancienne route renvoyait `{"status": "ok"}` quoi qu'il arrive, y compris Ollama arrêté — un contrôle de santé qui ne contrôle rien.

La nouvelle interroge `GET /api/tags` sur Ollama, vérifie que **les deux modèles sont effectivement installés**, et remonte les problèmes du corpus, les points marqués `À-vérifier` et les statistiques de cache. Elle renvoie `degraded` avec un `detail` exploitable au lieu de prétendre que tout va bien.

C'est le premier endroit à regarder au moment de lancer sur la machine principale.

## 4. Démarrage de l'API

Au démarrage, l'API valide le corpus (avertissements dans les logs) et précalcule les embeddings des documents (`STUDENTIA_PRECHARGE`, activé par défaut). La première question d'une démonstration n'est donc plus la plus lente.

Si Ollama n'est pas joignable au démarrage, l'API démarre quand même et répond 503 tant que le service n'est pas là, au lieu de refuser de se lancer.

## 5. Journalisation

Le code de bibliothèque affichait des `print()` de débogage à chaque requête — les scores de chaque document, le message « Création de l'embedding de la question... ». Ces sorties polluaient les tests et l'exécution de l'API, et n'étaient pas désactivables.

Remplacés par `logging`. Les scores détaillés passent en `DEBUG`, les abstentions et avertissements de vérification en `INFO`/`WARNING`. Niveau réglable par `STUDENTIA_LOG`.

## 6. Interface

Trois ajouts, tous liés à une information que le backend produit désormais et que l'utilisateur doit voir :

- **Réponse retenue par la vérification** : un encadré explique que la réponse générée contenait un chiffre absent du document officiel. Masquer l'incident serait la pire option.
- **Date de vérification** du document, sous le lien source.
- **Abstention** visuellement distinguée d'une réponse normale.

## 7. Intégration continue

`.github/workflows/tests.yml` lance à chaque push la validation du corpus et la suite hors ligne. Les runners GitHub n'ont pas les modèles, donc les tests de recherche restent manuels sur la machine principale — c'est documenté dans le workflow pour éviter qu'un build vert soit pris pour une validation complète.

## 8. Ordre de lancement sur la machine principale

```powershell
git pull
python -m pip install -r requirements.txt

python src/corpus.py                      # 1. corpus valide
python tests/test_hors_ligne.py           # 2. logique OK sans modèles
ollama list                               # 3. les deux modèles présents
python evaluation/calibrer_seuils.py      # 4. calibrer les seuils
# appliquer les valeurs recommandées
python tests/test_recherche.py            # 5. mesurer le point de départ réel
python -m uvicorn api:app --app-dir src   # 6. lancer
```
