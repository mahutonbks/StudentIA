// Adresse du backend. Modifiable sans toucher au code : ajouter
// <script>window.STUDENTIA_API = "http://192.168.1.42:8000";</script>
// avant app.js dans index.html, ou definir la valeur ci-dessous.
const API_BASE = window.STUDENTIA_API || "http://127.0.0.1:8000";

const API_URL = `${API_BASE}/question`;
const SESSION_URL = `${API_BASE}/nouvelle-session`;

const form = document.getElementById("question-form");
const input = document.getElementById("question-input");
const conversation = document.getElementById("conversation");
const loading = document.getElementById("loading");
const sendButton = document.getElementById("send-button");
const suggestionCards = document.querySelectorAll(".suggestion-card");

const profilForm = document.getElementById("profil-form");
const profilPays = document.getElementById("profil-pays");
const profilResume = document.getElementById("profil-resume");


// --- Etat de la conversation (memoire JS uniquement, pas de localStorage)

let sessionId = null;
let historique = [];          // [{role, content}] des echanges termines
let profil = null;            // {pays_origine}
let profilAEnvoyer = false;   // le profil n'est envoye que s'il a change
let questionEnAttente = null; // question posee avant le profil


async function demarrerSession() {
    try {
        const response = await fetch(SESSION_URL, { method: "POST" });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        sessionId = (await response.json()).session_id;
    } catch (error) {
        // Pas bloquant : le backend cree une session a la premiere
        // question et la renvoie dans l'evenement "session".
        console.warn("Session non creee au demarrage :", error);
    }
}


// --- Affichage ------------------------------------------------------------

function scrollConversation() {
    conversation.scrollTo({
        top: conversation.scrollHeight,
        behavior: "smooth"
    });
}


function ajouterMessageUtilisateur(texte) {
    const row = document.createElement("div");
    row.className = "user-row";

    const message = document.createElement("div");
    message.className = "message user-message";
    message.textContent = texte;

    row.appendChild(message);
    conversation.appendChild(row);

    scrollConversation();
}


// Cree une bulle vide qui se remplit au fil des tokens.
function creerBulleAssistant() {
    const row = document.createElement("div");
    row.className = "assistant-row";

    const avatar = document.createElement("div");
    avatar.className = "assistant-avatar";
    avatar.textContent = "S";

    const message = document.createElement("div");
    message.className = "message assistant-message";

    const contenu = document.createElement("div");
    contenu.className = "reponse-texte en-cours";

    message.appendChild(contenu);
    row.appendChild(avatar);
    row.appendChild(message);
    conversation.appendChild(row);

    scrollConversation();

    return { message, contenu };
}


// Rendu final : texte echappe, seul le gras **...** est interprete.
function afficherTexteFinal(contenu, texte) {
    contenu.classList.remove("en-cours");
    contenu.textContent = "";

    texte.split(/(\*\*[^*]+\*\*)/g).forEach((morceau) => {
        if (/^\*\*[^*]+\*\*$/.test(morceau)) {
            const gras = document.createElement("strong");
            gras.textContent = morceau.slice(2, -2);
            contenu.appendChild(gras);
        } else if (morceau) {
            contenu.appendChild(document.createTextNode(morceau));
        }
    });
}


function ajouterNote(message, texte) {
    const note = document.createElement("p");
    note.className = "verification-note";
    note.textContent = texte;
    message.appendChild(note);
}


function ajouterSource(message, source, verifieLe) {
    if (!source) {
        return;
    }

    const sourceCard = document.createElement("div");
    sourceCard.className = "source-card";

    const sourceLabel = document.createElement("span");
    sourceLabel.textContent = "Source officielle";

    const sourceLink = document.createElement("a");
    sourceLink.href = source;
    sourceLink.target = "_blank";
    sourceLink.rel = "noopener noreferrer";
    sourceLink.textContent = "Voir la source officielle →";

    sourceCard.appendChild(sourceLabel);
    sourceCard.appendChild(sourceLink);

    if (verifieLe) {
        const date = document.createElement("small");
        date.className = "source-date";
        date.textContent = `Document vérifié le ${verifieLe}`;
        sourceCard.appendChild(date);
    }

    message.appendChild(sourceCard);
}


function afficherChargement() {
    loading.classList.remove("hidden");
    sendButton.disabled = true;
    input.disabled = true;
}


function masquerChargement() {
    loading.classList.add("hidden");
    sendButton.disabled = false;
    input.disabled = false;
}


// --- Profil ---------------------------------------------------------------

function afficherFormulaireProfil() {
    profilForm.classList.remove("hidden");
    profilResume.classList.add("hidden");
    profilPays.focus();
}


function afficherResumeProfil() {
    profilForm.classList.add("hidden");

    profilResume.textContent = `Profil : ${profil.pays_origine}`;

    const modifier = document.createElement("button");
    modifier.type = "button";
    modifier.textContent = "modifier";
    modifier.addEventListener("click", afficherFormulaireProfil);

    profilResume.appendChild(modifier);
    profilResume.classList.remove("hidden");
}


profilForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const pays = profilPays.value.trim();

    if (!pays) {
        profilPays.focus();
        return;
    }

    profil = { pays_origine: pays };
    profilAEnvoyer = true;

    afficherResumeProfil();

    // Une question posee avant le profil (ou ayant declenche une
    // clarification) est relancee automatiquement.
    if (questionEnAttente) {
        const question = questionEnAttente;
        questionEnAttente = null;
        await envoyerQuestion(question, { dejaAffichee: true });
    } else {
        input.focus();
    }
});


// --- Lecture du flux SSE --------------------------------------------------
//
// EventSource ne sait faire que des requetes GET : le flux de
// POST /question est donc lu avec fetch() + ReadableStream, en
// decodant le format SSE (blocs "event: ...\ndata: ...\n\n").

async function lireEvenements(response, surEvenement) {
    const lecteur = response.body.getReader();
    const decodeur = new TextDecoder("utf-8");
    let tampon = "";

    while (true) {
        const { value, done } = await lecteur.read();

        if (done) {
            break;
        }

        tampon += decodeur.decode(value, { stream: true });

        let fin;

        while ((fin = tampon.indexOf("\n\n")) !== -1) {
            const bloc = tampon.slice(0, fin);
            tampon = tampon.slice(fin + 2);

            let type = "message";
            let donnees = "";

            bloc.split("\n").forEach((ligne) => {
                if (ligne.startsWith("event: ")) {
                    type = ligne.slice(7);
                } else if (ligne.startsWith("data: ")) {
                    donnees += ligne.slice(6);
                }
            });

            if (donnees) {
                surEvenement(type, JSON.parse(donnees));
            }
        }
    }
}


// --- Envoi d'une question -------------------------------------------------

async function envoyerQuestion(question, options = {}) {
    const texte = question.trim();

    if (!texte) {
        return;
    }

    if (!options.dejaAffichee) {
        ajouterMessageUtilisateur(texte);
        input.value = "";
        ajusterTextarea();
    }

    // Profil requis avant la premiere question.
    if (!profil) {
        questionEnAttente = texte;
        afficherFormulaireProfil();
        return;
    }

    afficherChargement();

    const corps = {
        question: texte,
        session_id: sessionId,
        historique: historique
    };

    if (profilAEnvoyer) {
        corps.profil = profil;
    }

    let bulle = null;
    let texteRecu = "";
    let meta = {};
    let terminal = false;

    const obtenirBulle = () => {
        if (!bulle) {
            masquerChargement();
            sendButton.disabled = true;
            input.disabled = true;
            bulle = creerBulleAssistant();
        }
        return bulle;
    };

    const terminer = (reponseFinale) => {
        terminal = true;
        historique.push({ role: "user", content: texte });
        historique.push({ role: "assistant", content: reponseFinale });
    };

    try {
        const response = await fetch(API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(corps)
        });

        if (!response.ok || !response.body) {
            throw new Error(`HTTP error ${response.status}`);
        }

        profilAEnvoyer = false;

        await lireEvenements(response, (type, data) => {
            if (type === "session") {
                sessionId = data.session_id;

            } else if (type === "meta") {
                meta = data;

            } else if (type === "token") {
                // Effet machine a ecrire : chaque token est affiche
                // des sa reception.
                texteRecu += data.texte;
                obtenirBulle().contenu.textContent = texteRecu;
                scrollConversation();

            } else if (type === "done") {
                const { message, contenu } = obtenirBulle();

                if (data.abstention) {
                    message.classList.add("abstention-message");
                }

                // Le texte final (nettoye cote serveur) remplace le flux.
                afficherTexteFinal(contenu, data.reponse);
                ajouterSource(
                    message,
                    data.source,
                    data.verifie_le || meta.verifie_le
                );
                terminer(data.reponse);

            } else if (type === "clarification") {
                const { message, contenu } = obtenirBulle();

                message.classList.add("clarification-message");
                afficherTexteFinal(contenu, data.message);
                terminer(data.message);

                if ((data.champs_manquants || []).includes("pays_origine")) {
                    // Le profil complete, la question est relancee.
                    profil = null;
                    questionEnAttente = texte;
                    afficherFormulaireProfil();
                }

            } else if (type === "error") {
                const { message, contenu } = obtenirBulle();

                message.classList.add("abstention-message");
                afficherTexteFinal(contenu, data.message);

                if (data.type === "abstention_verification") {
                    ajouterNote(
                        message,
                        "Réponse retirée : le texte généré contenait un " +
                        "chiffre absent du document officiel."
                    );
                    terminer(data.message);
                } else {
                    terminal = true;
                }

                ajouterSource(message, data.source || meta.source, null);
            }
        });

        if (!terminal) {
            throw new Error("Flux interrompu avant la fin de la réponse.");
        }

    } catch (error) {
        console.error("Error communicating with the API:", error);

        const { message, contenu } = obtenirBulle();
        message.classList.add("abstention-message");
        afficherTexteFinal(
            contenu,
            (texteRecu ? texteRecu + "\n\n" : "") +
            "Impossible de joindre le serveur pour le moment. " +
            "Vérifie que l'assistant est lancé, puis réessaie."
        );
    }

    masquerChargement();
    scrollConversation();

    if (profil) {
        input.focus();
    }
}


// --- Evenements -----------------------------------------------------------

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    await envoyerQuestion(input.value);
});


suggestionCards.forEach((card) => {
    card.addEventListener("click", async () => {
        const question = card.dataset.question;

        if (!question || sendButton.disabled) {
            return;
        }

        document
            .querySelector(".assistant-section")
            .scrollIntoView({
                behavior: "smooth",
                block: "start"
            });

        await envoyerQuestion(question);
    });
});


function ajusterTextarea() {
    input.style.height = "auto";

    input.style.height =
        Math.min(input.scrollHeight, 140) + "px";
}


input.addEventListener("input", ajusterTextarea);


input.addEventListener("keydown", (event) => {
    if (
        event.key === "Enter" &&
        !event.shiftKey
    ) {
        event.preventDefault();

        if (
            input.value.trim() &&
            !sendButton.disabled
        ) {
            form.requestSubmit();
        }
    }
});


demarrerSession();
