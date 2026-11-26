# Studentia — AI Administrative Assistant

[![Tests](https://github.com/mahutonbks/StudentIA/actions/workflows/tests.yml/badge.svg)](https://github.com/mahutonbks/StudentIA/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-SSE-009688)
![Ollama](https://img.shields.io/badge/LLM-Ollama%20%C2%B7%20qwen2.5%3A3b-black)
![Version](https://img.shields.io/badge/version-3.0.0-informational)

Studentia is an academic prototype that helps international students in France find information about administrative procedures (residence permit, health insurance, housing, grants, banking, work…).

It uses Retrieval-Augmented Generation (RAG): a relevant passage is selected from an official document database before an answer is generated. Since version 3.0, answers are **always in French**, whatever the language of the question, and are streamed token by token. The assistant remembers the conversation and adapts to the student's nationality. When a question is too vague, it may ask one clarifying question first.

> [!IMPORTANT]
> Studentia is a limited academic prototype, not an official administrative service. Users must verify important information with the relevant authorities.

> [!NOTE]
> This repository is a **fork** of [MELI0-dot/IA-assistant](https://github.com/MELI0-dot/IA-assistant). See [Credits](#17-credits) for details.

### Highlights

- 🔎 **Hybrid retrieval** (85 % semantic + 15 % lexical) over 15 sourced documents, with **abstention** when nothing is reliable enough
- 🧾 **Grounding check**: every figure in the answer must appear in the source passage
- 💬 **Conversation memory** and **student profile** (EU / non-EU, Algerian-specific rules)
- ⚡ **Streaming** answers over Server-Sent Events
- 🐳 **One-command Docker setup** (Ollama + model pull + API + frontend)
- ✅ **CI** on every push (corpus validation + 99 offline assertions)

### Table of contents

1. [Quick start](#1-quick-start)
2. [Current scope](#2-current-scope)
3. [Technologies](#3-technologies)
4. [Architecture](#4-architecture)
5. [Retrieval](#5-retrieval)
6. [Acceptance and abstention](#6-acceptance-and-abstention)
7. [Answer generation and grounding check](#7-answer-generation-and-grounding-check)
8. [Conversation memory and student profile](#8-conversation-memory-and-student-profile)
9. [Document database](#9-document-database)
10. [Configuration](#10-configuration)
11. [Embedding cache](#11-embedding-cache)
12. [API](#12-api)
13. [Tests](#13-tests)
14. [Known limitations](#14-known-limitations)
15. [Next steps](#15-next-steps)
16. [Project structure](#16-project-structure)
17. [Credits](#17-credits)

---

## 1. Quick start

### Prerequisites

- [Python 3.12](https://www.python.org/downloads/)
- [Ollama](https://ollama.com/download) running locally (or reachable over the network, see section 10)
- About 2 GB of free disk space for the models
- Optional: [Docker](https://docs.docker.com/get-docker/) with Compose

### Local install

```powershell
git clone https://github.com/mahutonbks/StudentIA.git
cd StudentIA

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# Models (on the machine that hosts Ollama)
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

Then, with Ollama running:

```powershell
# Terminal 1 — backend
$env:PYTHONPATH = "src"
python -m uvicorn src.api:app --reload

# Terminal 2 — frontend
python -m http.server 5500 --bind 127.0.0.1 --directory frontend
```

On Linux/macOS (or Git Bash) the backend command is `PYTHONPATH=src uvicorn src.api:app --reload`. `src/` must be on the path because the modules import each other by name (`import config`, `import assistant`…).

Open `http://127.0.0.1:5500`. The page asks for the student's country before the first question.

### With Docker

```powershell
docker compose up --build
```

This starts four services: `ollama`, `ollama-init` (pulls `nomic-embed-text` and `qwen2.5:3b` once, about 2 GB), `studentia-api` on port 8000 and `studentia-frontend` (nginx) on port 5500. The API waits until both models are pulled. Models and the embedding cache are kept in named volumes; `data/` is mounted, so editing a document does not require a rebuild.

**First thing to run after cloning this version** — the acceptance thresholds have not been calibrated against the real models:

```powershell
python evaluation/calibrer_seuils.py
```

See section 6.

---

## 2. Current scope

The document database covers 15 topics. The category drives the profile rules of section 8: `titre_sejour` documents are never shown to EU/EEA/Swiss students.

| Document | Topic | Category | Source |
|---|---|---|---|
| `validation_vls_ts.txt` | VLS-TS validation after arrival | `titre_sejour` | Service-Public F2231 |
| `renouvellement_etudiant.txt` | Residence permit renewal | `titre_sejour` | Service-Public F2231 |
| `carte_sejour_pluriannuelle.txt` | Multi-year student permit | `titre_sejour` | Service-Public F2231 |
| `etudiant_algerien.txt` | Algerian residence certificate (1968 agreement) | `titre_sejour` | Service-Public F2215 |
| `changement_statut_etudiant.txt` | After graduation: job-search permit, change of status | `titre_sejour` | Service-Public F17319 |
| `sejour_etudiant_ue.txt` | Right of residence of EU/EEA/Swiss students | `sejour_ue` | Service-Public F21841 |
| `ressources_etudiant.txt` | Proof of financial resources | `ressources` | Service-Public F2231 |
| `securite_sociale_etudiant.txt` | Health insurance registration | `sante` | Ameli |
| `ceam_sante_ue.txt` | European health insurance card (EU students) | `sante` | Ameli |
| `logement_caf.txt` | CAF housing benefit | `logement` | CAF |
| `logement_crous.txt` | CROUS accommodation and DSE | `logement` | messervices.etudiant.gouv.fr |
| `bourse_crous.txt` | CROUS needs-based grant | `financement` | messervices.etudiant.gouv.fr |
| `impots_etudiant.txt` | Income tax return | `financement` | etudiant.gouv.fr |
| `compte_bancaire.txt` | Opening a bank account | `banque` | Service-Public F2413 |
| `travail_etudiant.txt` | Working while studying | `travail` | Service-Public F2713 |

When no passage meets the acceptance criteria, the assistant abstains rather than generating an answer.

---

## 3. Technologies

- Python 3.12, FastAPI, Ollama
- `nomic-embed-text` for embeddings
- `qwen2.5:3b` for answer generation
- HTML, CSS, JavaScript for the web interface
- GitHub Actions for continuous integration

---

## 4. Architecture

```text
Student (profile: country)
   |
   v
Web interface — session_id + conversation history
   |
   v
FastAPI — POST /question  (Server-Sent Events)
   |
   v
Session: merge profile, restore history
   |
   +---- Residence-permit question, country unknown
   |                  ---> Clarification request
   v
Profile rules: EU/EEA/Swiss -> exclude "titre_sejour" passages
               Algerian     -> flag carte_pluriannuelle_exclue
   |
   v
Question embedding (nomic-embed-text)
   |
   v
Hybrid passage retrieval
85% semantic + 15% lexical  (ranking only)
   |
   v
Acceptance check, per passage, in ranking order
   |
   +---- No passage accepted ---> Abstention
   |
   v
Selected passage(s)
   |
   v
Qwen2.5 3B (Ollama /api/chat) — system prompt
+ full history + profile + [CONTEXTE] + question
   |
   v
Tokens streamed to the browser as they are generated
   |
   v
Grounding check on the complete answer: every figure
must appear in the context
   |
   +---- Unsupported figure ----> final SSE "error" event,
   |                              answer replaced by abstention
   v
Final SSE "done" event: cleaned answer,
official source and its check date
```

---

## 5. Retrieval

Implemented in `src/recherche.py`, on top of `src/corpus.py`.

### Passages

Documents are split into passages by `corpus.decouper()`. Splitting respects paragraph boundaries, and a short label line (`Attention`) is merged with the paragraph it introduces, so a rule is never separated from its exception. With the current short documents, one document yields one passage; the splitting matters as soon as longer texts are added.

### Semantic and lexical signals

`nomic-embed-text` converts the question and each passage into embeddings; cosine similarity measures proximity.

Keywords now live in each document's header (`Mots-clés :`), not in a Python dictionary. Adding a document no longer requires editing code. A multi-word keyword (`residence permit`) scores higher than a single word, because its presence is a much stronger signal of the topic.

### Ranking

```text
final_score = 0.85 * semantic + 0.15 * lexical
```

These weights are experimental and have not been demonstrated optimal. **The final score is used for ranking only** — never to accept or reject.

---

## 6. Acceptance and abstention

The decision is made on the semantic similarity alone, with two thresholds:

| Situation | Threshold | Purpose |
|---|---|---|
| Passage **with** a matching keyword | `SEUIL_SEMANTIQUE_AVEC_LEXICAL` (default 0.35) | Low guard rail. Blocks a misleading keyword appearing in an unrelated question ("renew my Netflix subscription"). |
| Passage **without** any keyword | `SEUIL_SEMANTIQUE_SANS_LEXICAL` (default 0.72) | High bar. Allows a valid paraphrase that uses none of the expected keywords. |

Passages are examined in ranking order and the first accepted one is used. If none passes, Studentia abstains:

```text
Je n'ai pas encore d'information fiable sur ce sujet. Consulte directement service-public.fr ou le site de Campus France.
```

`rechercher_document()` accepts an optional `categories_exclues` argument. Excluded passages are removed **before** selection, so they can neither be chosen nor block the next candidate. This is how the EU profile rule is applied (section 8).

**The default thresholds are cautious starting values, not calibrated ones.** Run the calibration script on the machine hosting Ollama:

```powershell
python evaluation/calibrer_seuils.py
```

It runs a grid search over three parameters: the semantic weight (0.70 to 1.0, the lexical weight being its complement), the threshold with a keyword, and the threshold without one, giving 448 combinations. The 90 questions of `tests/test_recherche.py` are split once into a **calibration** part (about 70 %) and a **test** part (about 30 %), by hashing each question, so adding a question never moves the others. The best combination is the one with the fewest wrong selections, then the most correct decisions, measured **on the calibration part only**. It is then scored once on the test part, next to the current values. Only the test-part score should be quoted: the calibration score is always optimistic. The script prints the environment variables to set (section 10) and never changes the configuration itself.

**Results on 2026-11-26** (nomic-embed-text, 15 documents):

- **Before the keyword fix:** the best combination (0.85 / 0.45 / 0.75) scored 20/29 on the test part, exactly like the current values (0.85 / 0.35 / 0.72). No combination brought wrong selections below 4 on the calibration part, so the errors did not come from the parameters.
- **After the keyword fix (section 13):** the current values score **25/29** on the test part, with **1** wrong selection instead of 6. The best combination ties with them, so the defaults were kept.

---

## 7. Answer generation and grounding check

Implemented in `src/assistant.py` and `src/verification.py`.

The model is called through Ollama's `/api/chat` endpoint with a list of messages:

1. the system prompt `PROMPT_SYSTEME` (language, profile rules, conversation memory, absolute rule on figures, abstention, answer format);
2. the conversation history, with its `user` / `assistant` roles;
3. a final user message containing `[PROFIL]`, `[CONTEXTE]` and `[QUESTION]`, followed by a short reminder (`CONSIGNE_QUESTION_COURANTE`).

Each passage in `[CONTEXTE]` is preceded by its title, check date and category, so the model can fill the `📎 Source : [titre] — vérifié le [date]` line of the format. Temperature is `0`, which does not guarantee correctness. The context window is set with `STUDENTIA_NUM_CTX` (default 8192), because Ollama's default is too small for the prompt plus history.

The reminder placed after the question comes from testing with `qwen2.5:3b`. Without it, the model copied the previous answer from the history, including its figures, so the grounding check withheld an otherwise correct answer. It also wrote `[Sujet]` literally and invented procedural steps. The reminder deliberately contains no bracketed marker: a first version that named `[QUESTION]` and `[CONTEXTE]` made the model copy the question and every passage into its answer. The system prompt itself is unchanged.

### Streaming

Tokens are forwarded to the browser as soon as Ollama produces them. Once the stream ends, the complete answer goes through `assistant.finaliser()`: URL removal, then the **grounding check**. Each figure in the answer (amount, duration in hours, days, weeks, months or years, percentage) must appear in the context. Matching works across languages: `4 months` matches `4 mois`, `964 hours` matches `964 heures`, and `964h` matches both. If an unsupported figure is found, the stream ends with an `error` event carrying the abstention message, the browser replaces the streamed text with it, and the abstention (not the rejected answer) is what gets stored in the history.

The check also flags residual URLs. `verification.py` still flags answers "in French", because it was written when English was expected. That warning is now filtered out in `assistant.py`; the module itself was left unchanged.

### Why the hardcoded answers were removed

The previous version shipped a fully pre-written English answer for one VLS-TS scenario and a string replacement for one ambiguous phrase. Both only covered cases already encountered, and the pre-written answer bypassed the model entirely, making the system look better than it was. The grounding check replaces them with a general rule that also applies to questions nobody has tested.

The pre-written answer is still available for a side-by-side demonstration:

```powershell
$env:STUDENTIA_REPONSES_CONTROLEES = "true"
```

---

## 8. Conversation memory and student profile

Implemented in `src/sessions.py` and `src/profil.py`.

### Sessions

A session is a UUID holding the student's profile and the conversation history. It is kept **in memory**, expires after 30 minutes of inactivity (`STUDENTIA_TTL_SESSION`), and keeps at most 40 messages (`STUDENTIA_HISTORIQUE_MAX`) so the prompt fits in the context window.

The frontend creates a session on page load (`POST /nouvelle-session`) and keeps the id and history in JavaScript memory only, never in `localStorage`. Each question sends `session_id` and the current `historique`. The history sent by the client replaces the server's copy. As a result, a session lost to an API restart or to expiry is rebuilt transparently: the server issues a new id in the first SSE event and the client adopts it. An unknown id sent by a client is never reused.

### Profile

```json
{"pays_origine": "Algérie", "zone": "HORS_UE"}
```

The frontend only asks for the country. There is no "situation" field: the student's questions are specific enough. When a question is too vague (for instance "how much does my permit cost?" without saying first application or renewal), the system prompt lets the model ask **one** clarifying question instead of answering. The student's short reply ("renouvellement") is then searched together with the question that prompted it (`assistant.question_pour_recherche`).

The model can only ask that question when retrieval found a passage. A vague question often finds none. So when retrieval finds nothing **and** the question is about the residence permit (same keyword detection as the country clarification) **and** the student is not from the EU, `preparer()` returns a fixed clarifying question instead of an abstention. It asks whether this is the VLS-TS validation, a renewal, the multi-year card or the after-studies options. It is sent as a `clarification` event, so the frontend just displays it. It is never asked twice in a row (`precision_deja_demandee`): a second miss gives a normal abstention. An off-topic question still gets an abstention. When `zone` is missing, the backend deduces it from the country (EU + EEA + Switzerland list in `profil.py`, accent- and case-insensitive). The profile is stored in the session and reused for the following questions without asking again.

| Rule | Effect |
|---|---|
| `zone == "UE"` | Passages of category `titre_sejour` are excluded from the context sent to the model |
| Country is Algeria (`algérie`, `algérien`…) | The context starts with a `[DRAPEAU carte_pluriannuelle_exclue]` line forbidding the model to present the multi-year card as an option (1968 Franco-Algerian agreement) |
| Country unknown and residence-permit question | A clarification is returned **before** any retrieval or generation; the frontend reopens the profile form, then resends the question |

A question counts as a residence-permit question when it contains one of the keywords of the `titre_sejour` documents or a fixed expression (`titre de séjour`, `visa`, `préfecture`…). This check is lexical and does not call any model.

---

## 9. Document database

`data/*.txt`, one topic per file, with a metadata header:

```text
Titre : Renouvellement du titre de séjour étudiant
Catégorie : titre_sejour
Mots-clés : renouvellement, renouveler, expiration, renew, residence permit
Vérifié-le : 2026-09-18
À-vérifier : (optional) a known doubt about this document
Source : https://www.service-public.fr/particuliers/vosdroits/F2231

<document body>
```

### `À-vérifier`

Optional field recording a doubt someone has already identified but not yet resolved — typically a figure that official sources disagree on. It is reported by `python src/corpus.py`, logged at API startup and returned by `/health`, but **does not fail the build**: a doubt is not a data-entry error.

It exists because the grounding check accepts any figure present in the document, right or wrong. A figure nobody has confirmed therefore needs its own visible marker.

**Two doubts are currently flagged:**

- `bourse_crous.txt`: the DSE calendar (2 March to 31 May) was re-confirmed on 2026-11-25, but no official source consulted that day published the 2026-2027 grant amounts per level, nor confirmed that the 1 € meal was extended to all students in May 2026.
- `etudiant_algerien.txt`: the official sheet F2215 is very long and marked "being updated" for decree no. 2026-1001 of 26 October 2026, and its student section could only be read in part. The 50 % work limit and the absence of a multi-year card for Algerian students still need confirming. No fee is stated in the document until one is confirmed.

The previous doubt on the renewal tax is **resolved**. Service-Public F2231 (checked 1 August 2026) gives **100 €** (tax + stamp duty) for renewing the 1-year student card. **150 €** (100 € tax + 50 € stamp duty) is the cost of the multi-year card, which explains the conflicting figures found earlier. The document had been changed to 150 €; it now states 100 €.

`Vérifié-le` is the date the excerpt was last checked against the official source. An administrative rule with no check date should not be served to a student; the date is displayed in the interface next to the source link.

Validate the corpus at any time, without Ollama:

```powershell
python src/corpus.py
```

It reports missing sources, missing keywords, missing check dates and ambiguous keywords shared between documents.

---

## 10. Configuration

Everything is set in `src/config.py` and overridable by environment variable — useful when the frontend, the backend and the models are not on the same machine.

| Variable | Default | Role |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Address of the Ollama server |
| `STUDENTIA_MODELE_EMBEDDING` | `nomic-embed-text` | Embedding model |
| `STUDENTIA_MODELE_GENERATION` | `qwen2.5:3b` | Generation model |
| `STUDENTIA_SEUIL_AVEC_LEXICAL` | `0.35` | Threshold, keyword present |
| `STUDENTIA_SEUIL_SANS_LEXICAL` | `0.72` | Threshold, no keyword |
| `STUDENTIA_CORS_ORIGINS` | `http://127.0.0.1:5500,...` | Allowed frontend origins |
| `STUDENTIA_REPONSES_CONTROLEES` | `false` | Re-enable the pre-written answer |
| `STUDENTIA_PRECHARGE` | `true` | Build the index at API startup |
| `STUDENTIA_NUM_CTX` | `8192` | Context window requested from Ollama |
| `STUDENTIA_NUM_PREDICT` | `800` | Maximum generated tokens (300 cut the structured answer format) |
| `STUDENTIA_TTL_SESSION` | `1800` | Session lifetime when inactive, in seconds |
| `STUDENTIA_HISTORIQUE_MAX` | `40` | Maximum history messages kept per session (`0` = unlimited) |
| `STUDENTIA_LOG` | `INFO` | Log level |

Example, backend and models on a different machine:

```powershell
$env:OLLAMA_HOST = "http://192.168.1.42:11434"
$env:STUDENTIA_CORS_ORIGINS = "http://192.168.1.42:5500"
$env:PYTHONPATH = "src"
python -m uvicorn src.api:app --host 0.0.0.0
```

The frontend reads its backend address from `window.STUDENTIA_API` if defined, otherwise `http://127.0.0.1:8000`.

---

## 11. Embedding cache

Embeddings are cached in `.cache/embeddings/`, keyed by a hash of the text **and** the model name. Editing a document or switching models invalidates the entry automatically.

Unlike the previous in-memory cache, it survives a process restart — which matters with `uvicorn --reload`. A corrupted cache file is ignored rather than crashing the app. `.cache/` is gitignored.

The offline tests write their fake 32-dimension vectors to a temporary folder, never to `.cache/`. They used to write them to the real cache under the real model's name. The API then read these vectors back, the cosine similarity with a 768-dimension question was 0, and **every question triggered an abstention**. As an extra guard, retrieval now detects a cached vector whose dimension differs from the question's, logs a warning and recomputes it. If you ran the offline tests with an older version, delete `.cache/embeddings/` once.

---

## 12. API

| Endpoint | Role |
|---|---|
| `GET /` | Welcome message and version |
| `GET /health` | Checks Ollama is reachable and both models are installed; reports corpus problems, cache statistics, active sessions, and **documents every endpoint** under `endpoints`. Returns `degraded` rather than pretending everything is fine |
| `POST /nouvelle-session` | Creates a session: `{"session_id", "expire_dans_secondes"}` |
| `GET /session/{session_id}` | Current profile and history; 404 if unknown or expired |
| `POST /question` | Asks a question; the answer is a Server-Sent Events stream |

`POST /question` body (only `question` is required):

```json
{
  "question": "Puis-je obtenir la carte pluriannuelle ?",
  "session_id": "6ef07b8e-…",
  "historique": [{"role": "user", "content": "…"}, {"role": "assistant", "content": "…"}],
  "profil": {"pays_origine": "Algérie"}
}
```

Response: `text/event-stream`. Each event is `event: <type>` followed by `data: <JSON>`:

| Event | Data | When |
|---|---|---|
| `session` | `session_id` | Always first; adopt this id |
| `meta` | `source`, `document`, `documents_utilises`, `verifie_le`, `scores` | Passages were found |
| `token` | `texte` | One generated fragment |
| `done` | `reponse`, `abstention`, `source`, `verifie_le`, `verification` | **Terminal**: answer accepted, or no passage found (`abstention: true`) |
| `clarification` | `message`, `champs_manquants` | **Terminal**: profile information missing |
| `error` | `type`, `message`, … | **Terminal**: `abstention_verification` (grounding check failed), `ollama_indisponible`, `generation_indisponible`, `question_vide` |

The `reponse` of `done` is the cleaned final text and should replace what was displayed during streaming.

Because the response is a stream, Ollama errors no longer produce an HTTP 503: the status is 200 and the stream ends with an `error` event carrying an actionable message. Invalid bodies still return 422.

The browser `EventSource` API only supports GET, so the frontend reads the stream with `fetch()` and a `ReadableStream`.

Retrieval scores are not probabilities that an answer is correct.

---

## 13. Tests

### Offline — no models needed

```powershell
python tests/test_hors_ligne.py
```

99 assertions covering metadata parsing, chunking, lexical scoring, the acceptance rule, the cache and the grounding check, plus (since 3.0) the system prompt and message layout, EU filtering, the Algerian flag, sessions, clarification and the SSE stream. Embeddings and the streaming generator are replaced by deterministic fake functions, so the whole pipeline is exercised without Ollama. This suite runs in GitHub Actions on every push.

**Known failure:** one assertion, "le document attendu est premier grâce au signal lexical", fails. It was already failing before version 3.0. The fake embeddings are random-looking vectors, and since the corpus grew they give `carte_sejour_pluriannuelle` a higher semantic score (0.266) than `renouvellement_etudiant` (0.105), which outweighs the lexical signal. The test needs either a less fragile question or a fake embedding with no semantic component.

### Online — requires Ollama and both models

```powershell
python tests/test_recherche.py
```

**90 cases**, reported per family. Results on 2026-11-26 with the default parameters, before and after the keyword fix:

| Family | Cases | What it probes | Before | After |
|---|---:|---|---:|---:|
| `origine` | 11 | The original suite, kept for comparison | 11/11 | 11/11 |
| `corpus_elargi` | 9 | Topics added in version 2 | 8/9 | 9/9 |
| `corpus_15` | 33 | Two or three direct questions per document, all 15 documents | 30/33 | 31/33 |
| `reformulation` | 22 | Valid questions using no expected keyword | 11/22 | 11/22 |
| `mot_cle_trompeur` | 8 | Off-topic questions containing a keyword | 2/8 | **8/8** |
| `sujet_voisin` | 7 | Plausible administrative topics absent from the corpus | 7/7 | 7/7 |
| **Total** | **90** | | **69/90 (76.7 %)** | **77/90 (85.6 %)** |

Wrong selections (`GRAVE`) went from 14 to 4, then to **1** with the whole-word matching fix below (same 77/90: three wrong answers became abstentions).

The three former `sujet_voisin` questions (bank account, CROUS room, tax return) expected an abstention, but these topics have been in the corpus since version 2. They now expect their document, and seven truly out-of-corpus topics replace them. A test set has to move with the corpus, or it silently stops measuring the right thing.

**The fix.** The first run showed that single-word keywords caused false positives. `renouveler`, `banque`, `mutuelle` and `valider` made the system answer "renew my Netflix subscription", "my bank offers a credit card", "best pet insurance" and "validate my semester". The grid search showed that no parameter setting fixed this. The generic words (`renouveler`, `renew`, `banque`, `banking`, `mutuelle`, `medecin`, `sante`, `doctor`, `valider`, `validation`, `validate`, `salarie`, `boursier`) were replaced by compound forms (`renouveler ma carte`, `valider mon visa`, `frais de medecin`, `etudiants boursiers`, …). `carte europeenne d'assurance maladie` was also added, because the CEAM keyword lacked the apostrophe form.

**Caveat.** Some compound forms were chosen while looking at the failing questions, so the after-fix score is partly fitted to this set. The test-part score from the calibration (section 6) is the fairer number.

**What the 13 remaining failures show:**

- **Paraphrases without any keyword** mostly fall below the strict 0.72 threshold (11/22) and now end in an abstention, or in a clarifying question for residence-permit questions.
- **Whole-word matching.** Three of the last four wrong selections were not ranking errors. Keywords were matched as substrings: `work` was found in "paper**work**", `rent` in "pa**rent**s" and `bourse` in "rem**bourse**", which sent these questions to the work, CAF and grant documents. `recherche.contient_mot()` now requires a whole word (a plural `s`/`x` is accepted). The residence-permit detection in `profil.py` uses the same function.
- **1 wrong selection remains:** "Combien dois-je prouver que je gagne pour être accepté comme étudiant ?" Every document scores 0.70 to 0.72, and the resources document is not even in the top 5, so reranking the top results would not fix it.

Failures are labelled `GRAVE` when the system answered where it should have abstained, or picked the wrong document — the failure type to fix first.

### On the previous 11/11

That result was mechanically flattering: every test question contained one of the hand-written keywords, and the presence of a keyword *was* the acceptance criterion. The suite mostly verified that the keyword list covered questions written from that keyword list. A score below 100% on the extended suite is expected and more informative.

---

## 14. Known limitations

- 15 short documents, each a summary rather than the full official page.
- Two documents carry an unresolved `À-vérifier` doubt (see section 9).
- Administrative excerpts go stale; `Vérifié-le` records when each was last checked but nothing enforces re-checking.
- The CAF rules changed on 1 July 2026 and the corpus reflects that change; rules this recent are the most likely to move again.
- Keywords are still written by hand.
- The semantic threshold for keyword-free questions has not been calibrated against the real models.
- The grounding check catches invented figures, not invented procedural steps or wrong reasoning about an exception.
- **With streaming, the student sees the answer before it is checked.** If the grounding check fails, the text is replaced by the abstention message, but an invented figure may have been on screen for a few seconds.
- Sessions live in the memory of a single process: they are lost on restart (the client history limits the impact) and are not shared between several uvicorn workers.
- Residence-permit questions are detected by keywords; a paraphrase without any of them will not trigger the clarification.
- The EU country list and the Algerian rule rely on the country typed by the student; a misspelled country is treated as non-EU.
- The test set has 90 questions written by someone who knows the keyword lists; it is not independent, and its 29-question test part is small.
- Retrieval scores 77/90; half of the keyword-free paraphrases are still missed (section 13).
- Not an official administrative service.

RAG provides documentary context. It does not guarantee factual accuracy.

---

## 15. Next steps

- Resolve the two flagged doubts (CROUS grant amounts, Algerian student rules after the October 2026 decree).
- Improve recall on keyword-free paraphrases (reranking, richer titles) without reintroducing generic keywords.
- Build an independent evaluation set, written by someone who has not seen the keyword lists.
- Re-check documents on a schedule and fail the build when `Vérifié-le` is too old.
- Extend the grounding check beyond figures.
- Measure answer quality, not only retrieval.

---

## 16. Project structure

```text
StudentIA/
|
|-- data/                     Documents with metadata headers
|-- frontend/                 index.html, style.css, app.js
|-- src/
|   |-- config.py             Configuration, env-overridable
|   |-- corpus.py             Loading, chunking, validation
|   |-- cache_embeddings.py   Disk-persistent cache
|   |-- recherche.py          Hybrid retrieval and abstention
|   |-- verification.py       Grounding check
|   |-- profil.py             Student profile rules
|   |-- sessions.py           In-memory sessions with TTL
|   |-- assistant.py          Prompt, context, streaming generation, CLI
|   `-- api.py                FastAPI backend (SSE)
|-- tests/
|   |-- test_hors_ligne.py    99 assertions, no models
|   `-- test_recherche.py     90 cases, needs Ollama
|-- evaluation/
|   `-- calibrer_seuils.py    Grid search, calibration/test split
|-- docs/                     Role notes and changelog
|-- Dockerfile                API image
|-- docker-compose.yml        Ollama + model pull + API + nginx frontend
`-- .github/workflows/        Continuous integration
```

Role notes are in `docs/`. Migration details from the previous version are in `docs/CHANGELOG.md`.

---

## 17. Credits

This project is a fork of **[MELI0-dot/IA-assistant](https://github.com/MELI0-dot/IA-assistant)**. Many thanks to its original authors for the initial work on which Studentia is built.

To pull future changes from the original project:

```powershell
git remote add upstream https://github.com/MELI0-dot/IA-assistant.git
git fetch upstream
git merge upstream/main
```
