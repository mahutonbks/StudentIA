# Note — ML Engineer

## 1. Ce qui a changé dans le calcul des scores

### Score lexical

Un mot-clé composé pèse davantage qu'un mot isolé : `residence permit` rapporte 1,5 point, `renew` en rapporte 1. La présence d'une expression de deux mots est un signal de sujet nettement plus fiable qu'un mot seul, qui peut apparaître par accident (« renouveler mon abonnement »). Le score reste borné à 1,0 : au-delà de deux correspondances, la certitude lexicale n'augmente plus vraiment.

La normalisation supprime les accents des deux côtés. Un étudiant international tape souvent sans accents ou avec les mauvais ; `renouvéllement` doit correspondre à `renouvellement`. Deux tests couvrent les deux sens.

### Score final

```text
score_final = 0,85 × sémantique + 0,15 × lexical
```

Inchangé, et toujours non démontré optimal. Mais son rôle a changé : **il classe, il ne décide plus**. Voir la note AI Researcher pour le raisonnement.

## 2. Calibration des seuils

`evaluation/calibrer_seuils.py`, à lancer sur la machine qui héberge Ollama.

Le script calcule une seule fois les similarités de chaque question de test contre chaque passage, puis rejoue la règle d'acceptation sur une grille de 64 couples de seuils. Aucun appel réseau supplémentaire pendant le balayage.

Sortie utile en trois parties :

1. **Distribution des similarités observées**, séparée entre questions dans le corpus et questions hors corpus. Si les deux plages sont bien séparées, un seuil les sépare proprement. Si elles se chevauchent, aucun seuil ne suffira seul — c'est une information de conception, pas un simple réglage.
2. **Classement des couples de seuils**, trié en priorisant *zéro mauvaise sélection*, puis le nombre de décisions correctes. Le critère reflète un choix explicite : répondre à tort sur une règle administrative est plus grave que ne pas répondre.
3. **Couple recommandé**, à appliquer via `STUDENTIA_SEUIL_AVEC_LEXICAL` et `STUDENTIA_SEUIL_SANS_LEXICAL`.

Le script affiche aussi un avertissement sur la taille du jeu de test. Optimiser deux seuils sur 21 points, c'est risquer de les sur-ajuster à ces 21 points.

## 3. Suite de tests

### Hors ligne — 53 assertions, aucun modèle

`tests/test_hors_ligne.py`. C'est ce qui manquait le plus : les tests existants exigeaient les deux modèles, donc ne tournaient que sur la machine principale et jamais en intégration continue.

Les embeddings sont remplacés par une fonction déterministe (hash SHA-256 projeté sur 32 dimensions, normalisé). Ces vecteurs n'ont aucun sens sémantique — et c'est assumé : ils permettent de vérifier le chargement, le classement, le format de retour et la propagation des erreurs, pas la pertinence. La calibration des seuils est testée séparément, sur `est_pertinent()` en isolation.

Les points d'injection (`definir_fonction_embedding`, `definir_fonction_generation`) existent pour cela et sont utilisés aussi bien par les tests que par le script de calibration.

### En ligne — 29 cas, modèles requis

`tests/test_recherche.py`. Les 11 cas d'origine sont conservés pour comparaison, avec quatre familles ajoutées :

| Famille | Cas | Ce qu'elle sonde |
|---|---:|---|
| `origine` | 11 | Le jeu précédent |
| `corpus_elargi` | 6 | Les trois sujets ajoutés au corpus |
| `reformulation` | 6 | Questions valides sans mot-clé prévu |
| `mot_cle_trompeur` | 3 | Questions hors sujet contenant un mot-clé |
| `sujet_voisin` | 3 | Sujets administratifs absents du corpus |

8 cas sur 29 attendent une abstention.

**Trois cas ont changé de réponse attendue** avec l'élargissement du corpus : sécurité sociale, aide au logement CAF et travail pendant les études attendaient une abstention, et attendent maintenant leur document. Un jeu de test figé pendant que le corpus bouge cesse silencieusement de mesurer ce qu'il prétend mesurer — c'est un point à vérifier à chaque ajout de document.

La calibration porte maintenant sur 29 points au lieu de 21, ce qui réduit un peu le risque de sur-ajustement des deux seuils, sans l'éliminer. Les échecs sont gradués : `GRAVE` quand le système répond alors qu'il devait s'abstenir ou choisit le mauvais document, `manque` quand il s'abstient à tort. Les deux ne se corrigent pas de la même façon et n'ont pas la même gravité pour un étudiant.

## 4. Métriques à suivre ensuite

Le projet mesure aujourd'hui **quel document est sélectionné**. Il ne mesure pas la qualité de la réponse produite. À ajouter, par ordre de coût :

- **Taux de rétention par le contrôle d'ancrage** en usage réel. Un taux élevé signale soit un modèle qui invente beaucoup, soit un contrôle trop strict — les deux se distinguent en inspectant les réponses retenues.
- **Latence** par requête, séparée entre embedding et génération. Les mesures du README précédent (66,46 s → 24,69 s après cache) portaient sur une ancienne suite de 7 tests et ne sont plus comparables ; elles ont été retirées du README plutôt que présentées comme actuelles.
- **Fidélité de la réponse** jugée sur un échantillon annoté à la main, ou par un modèle juge si un modèle plus capable est disponible sur la machine. C'est la mesure qui manque vraiment.

## 5. Sur le fine-tuning LoRA

Non nécessaire aujourd'hui. Les défauts observés (chiffres inventés, formulation ambiguë) ne sont pas des défauts de format que LoRA corrigerait : ce sont des défauts d'exactitude, traités par le contrôle d'ancrage et par le prompt. Rouvrir la question si, après calibration, le modèle échoue encore à respecter le format de réponse malgré un prompt explicite.
