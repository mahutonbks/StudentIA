# Note — Scrum Master

## 1. État de la révision

| Livrable | Statut | Vérifié comment |
|---|---|---|
| Correction du seuil jamais appliqué | Fait | Test unitaire sur `est_pertinent()` |
| Contrôle d'ancrage des chiffres | Fait | 6 assertions + test bout-en-bout |
| Découpage préservant règle + exception | Fait | Test sur le document renouvellement |
| Configuration par variables d'environnement | Fait | Lecture du code, démarrage API |
| Gestion des pannes Ollama | Fait | Test d'intégration FastAPI (503, health `degraded`) |
| Métadonnées dans les documents | Fait | `python src/corpus.py` |
| Cache persistant | Fait | 3 assertions |
| Suite hors ligne | Fait | 53 assertions exécutées, toutes vertes |
| Corpus élargi à 6 documents | Fait | Sources officielles vérifiées le 18/09/2026 |
| Champ `À-vérifier` | Fait | `python src/corpus.py`, `/health` |
| Intégration continue | Fait | Workflow écrit, à confirmer au premier push |
| **Calibration des seuils** | **À faire** | Nécessite les modèles |
| **Mesure réelle sur 21 cas** | **À faire** | Nécessite les modèles |

Les deux dernières lignes sont bloquées par l'absence des modèles sur la machine de développement. L'outillage est livré, la mesure reste à produire.

## 2. Risques à surveiller

| Risque | Gravité | Traitement |
|---|---|---|
| Le score sur 21 cas sera inférieur à l'ancien 11/11 | Moyenne | À expliquer, pas à cacher — voir §4 |
| Les seuils par défaut ne conviennent pas aux modèles réels | Élevée | Lancer la calibration avant toute démonstration |
| Le contrôle d'ancrage retient trop de réponses valides | Moyenne | Inspecter les réponses retenues ; le taux est journalisé |
| Le corpus se périme | Élevée en usage réel | Champ `Vérifié-le` ; règle d'expiration à écrire. La règle CAF a changé en juillet 2026, la démonstration du risque est faite |
| Un chiffre faux dans le corpus | Élevée | Le contrôle d'ancrage ne protège pas contre ça. Champ `À-vérifier` ; un doute est ouvert |
| Démonstration sans réseau vers la machine des modèles | Élevée | Vérifier `/health` avant de commencer |

## 3. Répartition du travail restant

| Rôle | Tâche immédiate |
|---|---|
| ML Engineer | Lancer `calibrer_seuils.py`, appliquer les valeurs, relancer les 21 cas |
| Data Engineering | **Trancher le doute sur la taxe de renouvellement** (100 € ou 150 €) |
| Data Engineering | Ajouter compte bancaire, logement CROUS, impôts (les 3 sujets qui déclenchent encore l'abstention) |
| AI Researcher | Analyser les échecs `GRAVE` et décider prompt ou seuil |
| Integration | Confirmer le workflow au premier push, vérifier CORS depuis la machine principale |
| Scrum Master | Répétition chronométrée de la soutenance |

## 4. Comment présenter la baisse de score

C'est le point de communication le plus délicat de cette révision, et il se retourne facilement en argument fort.

**Ce qu'il ne faut pas dire** : « on est passé de 11/11 à moins bien ».

**Ce qu'il faut dire** : le 11/11 mesurait une tautologie. Les questions de test contenaient toutes un mot-clé de la liste, et la présence d'un mot-clé *était* le critère d'acceptation. Le test vérifiait que la liste couvrait des questions écrites à partir de cette liste. Un jury technique repérera ce point si vous ne le soulevez pas d'abord.

Le nouveau jeu ajoute les cas que le système ratait vraiment : reformulations sans mot-clé, mots-clés trompeurs, sujets voisins. Un score plus bas sur un test plus honnête est un progrès de méthode, et vous êtes en mesure de dire **lesquels** échouent et **pourquoi**, ce qui n'était pas le cas avant.

## 5. Checklist de conformité

- [ ] Chaque réponse affiche sa source officielle et sa date de vérification.
- [ ] Une réponse retenue par le contrôle d'ancrage est signalée à l'utilisateur, pas masquée.
- [ ] L'abstention est visuellement distincte d'une réponse.
- [ ] L'avertissement « prototype académique, vérifier auprès des autorités » est visible en permanence.
- [ ] Aucune réponse ne présente une exception comme automatiquement applicable.
- [ ] Les extraits du corpus ont été revérifiés et `Vérifié-le` est à jour.
- [ ] `python src/corpus.py` ne remonte aucun problème **et aucun point `À-vérifier` non tranché**.
- [ ] Le document sur l'aide au logement reflète bien la règle en vigueur au jour de la démonstration.
- [ ] `/health` répond `ok` avant la démonstration.

## 6. Plan de soutenance (5 minutes)

1. **Le problème** (30 s) — la complexité administrative pour un étudiant international, et le risque particulier d'une réponse fausse sur un délai légal.
2. **Démonstration** (1 min 30) — une question dans le corpus avec sa source ; une question hors corpus qui déclenche l'abstention.
3. **Le bug trouvé** (1 min) — le seuil sémantique défini mais jamais appliqué, et ses deux conséquences directement visibles dans la liste des limitations de la version précédente. C'est le moment le plus convaincant : un défaut identifié dans son propre code, tracé jusqu'à ses effets.

   Enchaînement possible si le temps le permet : le contrôle d'ancrage ne couvrait pas les heures, et ce trou n'est apparu qu'en ajoutant le document sur le travail étudiant. Un garde-fou ne se valide que sur un corpus assez varié pour l'éprouver.
4. **Le garde-fou** (1 min) — le contrôle d'ancrage des chiffres, avec un exemple de réponse retenue. Expliquer pourquoi un contrôle général vaut mieux que deux correctifs ponctuels.
5. **Honnêteté de la mesure** (30 s) — pourquoi le jeu de test est passé à 21 cas et pourquoi le score baisse.
6. **Limites et suite** (30 s) — trois documents seulement, seuils calibrés sur un jeu trop petit, contrôle limité aux chiffres.

Prévoir une capture d'écran de secours de la démonstration, au cas où la machine hébergeant les modèles ne réponde pas le jour J.
