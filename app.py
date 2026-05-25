import streamlit as st 
import json
import re
import urllib.parse
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
from collections import Counter

import pandas as pd
import requests
from ddgs import DDGS
from newspaper import Article
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
try:
    from openai import OpenAI
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception:
    client = None

import math

NEGATIONS = {"pas", "aucun", "jamais", "ni", "rien"}
ATTENUATORS = {"peut-être", "semble", "probable", "possible"}
INTENSIFIERS = {"grave", "extrême", "massif", "violent"}

def tokenize(text):
    return re.findall(r"\b[\wà-ÿ'-]+\b", text.lower())

def compute_emotional_score(text, emotion_dict):
    words = tokenize(text)
    total_score = 0.0
    word_count = len(words)

    for i, word in enumerate(words):

        # gestion simple du pluriel
        base_word = word.rstrip("s")

        if base_word in emotion_dict:
            base_weight = emotion_dict[base_word]
            modifier = 1.0

            # fenêtre locale
            context = words[max(0, i-2):i+3]

            context_set = set(context)

            # négation
            if context_set & NEGATIONS:
                modifier *= 0.2

            # atténuation
            if context_set & ATTENUATORS:
                modifier *= 0.6

            # intensification
            if context_set & INTENSIFIERS:
                modifier *= 1.4

            total_score += base_weight * modifier

    # normalisation + stabilisation
    score = total_score / (math.log(1 + word_count) + 1)

    return min(score, 1.0)

st.markdown("""
<style>

div[data-testid="stMetricValue"] {
    font-size: 36px !important;
}

div[data-testid="stMetricLabel"] {
    font-size: 20px !important;
}

</style>
""", unsafe_allow_html=True)

# -----------------------------
# Mots grammaticaux ignorés
# -----------------------------
STOPWORDS = {
    "le","la","les","l","un","une","des",
    "de","du","d","à","au","aux",
    "et","ou","mais","donc","or","ni","car",
    "est","sont","était","étaient","etre","être",
    "a","ont","avait","avaient","avoir",
    "dans","sur","sous","avec","sans","pour","par","chez",
    "ce","cet","cette","ces","se","sa","son","ses",
    "je","tu","il","elle","on","nous","vous","ils","elles",
    "ne","n","pas","plus","moins","très","tres",
    "y","en","que","qui","quoi","dont","où","ou"
}

# -----------------------------
# Sources presse française
# -----------------------------
FRENCH_NEWS_DOMAINS = [

# centre / généralistes
"lemonde.fr",
"francetvinfo.fr",
"ouest-france.fr",

# centre droit
"lefigaro.fr",
"lesechos.fr",

# gauche
"liberation.fr",
"nouvelobs.com",

# droite
"valeursactuelles.com",

# droite radicale / extrême droite
"fdesouche.com",
"ripostelaique.com",
"boulevardvoltaire.fr",
"egaliteetreconciliation.fr",
"reseauinternational.net",

# international
"france24.com",
"rfi.fr"
]

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from streamlit_mic_recorder import speech_to_text
    MICRO_AVAILABLE = True
except Exception:
    speech_to_text = None
    MICRO_AVAILABLE = False


# -----------------------------
# Configuration page
# -----------------------------
st.set_page_config(
    page_title="DOXA Detector",
    page_icon="🧠",
    layout="wide",
)

st.image("banner2.png", use_container_width=True)
st.caption("Laboratoire de calibration cognitive — M = (G + N) − D")
st.markdown("---")

st.markdown("""
<style>
/* Force une base lisible, même si le téléphone est en mode sombre */
html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: #ffffff !important;
    color: #111827 !important;
}

/* Texte général */
p, span, div, label, textarea, input {
    color: #111827 !important;
}

/* Zones Streamlit */
[data-testid="stMarkdownContainer"],
[data-testid="stText"],
[data-testid="stCaptionContainer"],
[data-testid="stExpander"],
[data-testid="stForm"] {
    color: #111827 !important;
}

/* Champs de saisie */
textarea, input {
    background-color: #ffffff !important;
    color: #111827 !important;
    border-color: #cbd5e1 !important;
}

/* Boutons */
button {
    color: #111827 !important;
}

/* Cartes / containers */
[data-testid="stVerticalBlockBorderWrapper"] {
    background-color: #ffffff !important;
    color: #111827 !important;
}

/* Code blocks */
code, pre {
    background-color: #f8fafc !important;
    color: #111827 !important;
}
</style>
""", unsafe_allow_html=True)

# =============================
# STYLE GLOBAL DOXA DETECTOR (mobile friendly)
# =============================
st.markdown("""
<style>

/* =========================
   Compatibilité mobile / dark mode
   ========================= */

html, body, [data-testid="stAppViewContainer"], .stApp {
    background-color: #ffffff !important;
    color: #111827 !important;
}

/* Fond général */
.stApp {
    background: linear-gradient(
        180deg,
        #f8fafc 0%,
        #eef2f7 100%
    ) !important;

    color: #111827 !important;
}

/* Force le texte lisible partout */
.stApp,
.stApp * {
    color: #111827 !important;
}

/* Exceptions : garde les couleurs des jauges */
.stApp span[style*="color"],
.stApp b[style*="color"] {
    color: inherit !important;
}

/* Container principal */
.block-container {
    padding-top: 2rem;
}

/* Titres */
h1, h2, h3 {
    letter-spacing: -0.02em;
    font-weight: 600;
}

/* Cartes */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 6px 16px rgba(0,0,0,0.05);
    background: rgba(255,255,255,0.92) !important;
}

/* Boutons */
.stButton > button,
[data-testid="stLinkButton"] a {
    border-radius: 12px !important;
    font-weight: 600 !important;
    border: 1px solid #cbd5e1 !important;
    transition: all 0.2s ease;
    color: #111827 !important;
}

/* Hover boutons */
.stButton > button:hover,
[data-testid="stLinkButton"] a:hover {
    border-color: #94a3b8 !important;
}

/* Inputs */
textarea,
input {
    border-radius: 12px !important;
    background-color: #ffffff !important;
    color: #111827 !important;
    border-color: #cbd5e1 !important;
}

/* Labels */
label,
p,
span,
div {
    color: #111827 !important;
}

/* Progress bars */
div[data-testid="stProgressBar"] > div > div > div > div {
    height: 20px;
    border-radius: 8px;
}

/* Metrics */
[data-testid="stMetric"] {
    background: white !important;
    border-radius: 14px;
    padding: 12px;
    border: 1px solid #e2e8f0;
}

/* Expander */
.streamlit-expanderHeader {
    font-weight: 600;
}

/* Caption */
[data-testid="stCaptionContainer"] {
    color: #475569 !important;
}

/* Code blocks */
code,
pre {
    background-color: #f8fafc !important;
    color: #111827 !important;
}

/* Smartphone */
@media (max-width: 768px) {

    .block-container {
        padding-top: 1rem;
        padding-left: 0.6rem;
        padding-right: 0.6rem;
    }

    h1 {
        font-size: 1.5rem;
    }

    h2 {
        font-size: 1.3rem;
    }

    h3 {
        font-size: 1.1rem;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px !important;
        padding: 6px;
    }

    .stButton > button {
        width: 100%;
        padding: 0.6rem;
    }
}

</style>
""", unsafe_allow_html=True)


# -----------------------------
# Textes FR uniques
# -----------------------------
T = {
    "settings": "Réglages",
    "load_example": "Charger l'exemple",
    "show_method": "Afficher la méthode",
    "hard_fact_score_scale": "Échelle du Hard Fact Score",
    "scale_0_5": "très fragile",
    "scale_6_9": "douteux",
    "scale_10_14": "plausible mais à recouper",
    "scale_15_20": "structurellement robuste",
    "topic_section": "Analyse de plusieurs articles par sujet",
    "topic": "Sujet à analyser",
    "topic_placeholder": "ex. : intelligence artificielle",
    "analyze_topic": "📰 Analyser 10 articles sur ce sujet",
    "searching": "Recherche et analyse des articles en cours...",
    "articles_analyzed": "articles analysés.",
    "analyzed_articles": "Articles analysés",
    "avg_hard_fact": "Moyenne Hard Fact",
    "avg_classic_score": "Moyenne score classique",
    "topic_doxa_index": "Indice de doxa du sujet",
    "high": "Élevé",
    "medium": "Moyen",
    "low": "Faible",
    "credibility_score_dispersion": "Dispersion des scores de crédibilité",
    "article_label": "Article",
    "no_exploitable_articles_found": "Aucun article exploitable trouvé pour ce sujet.",
    "enter_keyword_first": "Entrez d'abord un mot-clé ou un sujet.",
    "url": "Analyser un article par URL",
    "load_url": "🌐 Charger l'article depuis l'URL",
    "article_loaded_from_url": "Article chargé depuis l'URL.",
    "unable_to_retrieve_text": "Impossible de récupérer le texte de cette URL.",
    "paste_url_first": "Collez d'abord une URL.",
    "paste": "Collez ici un article ou un texte",
    "analyze": "🔍 Analyser l'article",
    "manual_paste": "copier-coller manuel",
    "loaded_url_source": "article chargé par URL",
    "text_source": "Source du texte",
    "paste_text_or_load_url": "Collez un texte ou chargez une URL, puis cliquez sur « 🔍 Analyser l'article ».",
    "classic_score": "Score classique",
    "improved_score": "Score amélioré",
    "hard_fact_score": "Hard Fact Score",
    "help_classic_score": "M = (G + N) − D",
    "help_improved_score": "Ajout de V et pénalité R",
    "help_hard_fact_score": "Contrôle plus dur des affirmations et des sources",
    "credibility_gauge": "Jauge de crédibilité",
    "fragile": "Fragile",
    "fragile_message": "Le texte présente de fortes fragilités structurelles ou factuelles.",
    "doubtful": "Douteux",
    "doubtful_message": "Le texte contient quelques éléments crédibles, mais reste très incertain.",
    "plausible": "Plausible",
    "plausible_message": "Le texte paraît globalement plausible, mais demande encore vérification.",
    "robust": "Robuste",
    "robust_message": "Le texte présente une base structurelle et factuelle plutôt solide.",
    "score": "Score",
    "verdict": "Verdict",
    "summary": "Résumé de l'analyse",
    "strengths_detected": "Forces détectées",
    "few_strong_signals": "Peu de signaux forts repérés.",
    "weaknesses_detected": "Fragilités détectées",
    "no_major_weakness": "Aucune fragilité majeure repérée par l'heuristique.",
    "presence_of_source_markers": "Présence de marqueurs de sources ou de données",
    "verifiability_clues": "Indices de vérifiabilité repérés : liens, chiffres, dates ou pourcentages",
    "text_contains_nuances": "Le texte contient des nuances, limites ou contrepoints",
    "text_evokes_robust_sources": "Le texte évoque des sources potentiellement robustes ou institutionnelles",
    "some_claims_verifiable": "Certaines affirmations sont assez bien ancrées pour être vérifiées proprement",
    "overly_assertive_language": "Langage trop assuré ou absolutiste",
    "notable_emotional_sensational_charge": "Charge émotionnelle ou sensationnaliste notable",
    "almost_total_absence_of_verifiable_elements": "Absence quasi totale d'éléments vérifiables",
    "text_too_short": "Texte trop court pour soutenir sérieusement une affirmation forte",
    "multiple_claims_very_fragile": "Plusieurs affirmations centrales sont très fragiles au regard des indices présents",
    "hard_fact_checking_by_claim": "Fact-checking des affirmations",
    "claim": "Affirmation",
    "status": "Statut",
    "verifiability": "Vérifiabilité",
    "risk": "Risque",
    "number": "Nombre",
    "date": "Date",
    "named_entity": "Nom propre",
    "attributed_source": "Source attribuée",
    "yes": "Oui",
    "no": "Non",
    "to_verify": "À vérifier",
    "rather_verifiable": "Plutôt vérifiable",
    "very_fragile": "Très fragile",
    "low_credibility": "Crédibilité basse",
    "prudent_credibility": "Crédibilité prudente",
    "rather_credible": "Plutôt crédible",
    "strong_credibility": "Crédibilité forte",
    "paste_longer_text": "Collez un texte un peu plus long pour obtenir une cartographie fine des affirmations.",
    "llm_analysis": "Analyse de mécroyance pour systèmes",
    "llm_intro": "Cette section applique les modèles dérivés du traité pour évaluer la posture cognitive d'un système.",
    "overconfidence": "Surconfiance (asymétrie)",
    "calibration": "Calibration relative (ratio)",
    "revisability": "Révisabilité (R)",
    "cognitive_closure": "Clôture cognitive",
    "interpretation": "Interprétation",
    "llm_metrics": "Métriques dérivées",
    "zone_closure": "Zone de clôture cognitive : la certitude excède l’ancrage cognitif.",
    "zone_stability": "Zone de stabilité révisable : la mécroyance accompagne sans dominer.",
    "zone_lucidity": "Zone de lucidité croissante : le doute structure la cognition.",
    "zone_rare": "Zone rare : cognition hautement intégrée et réflexive.",
    "zone_pansapience": "Pan-sapience hypothétique : horizon limite d’une cognition presque totalement révisable.",
    "zone_asymptote": "Asymptote idéale : totalité du savoir et de l’intégration, sans rigidification.",
    "out_of_spectrum": "Valeur hors spectre théorique.",
    "external_corroboration_module": "🔎 Module de corroboration externe",
    "external_corroboration_caption": "Ce module cherche des sources externes susceptibles de confirmer, nuancer ou contredire les affirmations centrales du texte collé.",
    "corroboration_in_progress": "Recherche de corroborations en cours...",
    "generated_query": "Requête générée",
    "no_strong_sources_found": "Aucune source suffisamment solide trouvée pour cette affirmation.",
    "no_corroboration_found": "Aucune corroboration exploitable trouvée.",
    "corroborated": "Corroborée",
    "mixed": "Mitigée",
    "not_corroborated": "Non corroborée",
    "insufficiently_documented": "Insuffisamment documentée",
    "corroboration_verdict": "Verdict de corroboration",
    "match_score": "Score de correspondance",
    "contradiction_signal": "Signal de contradiction",
    "detected": "Détecté",
    "not_detected": "Non détecté",
    "ai_module": "Module IA",
    "ai_module_caption": "L’IA relit l’analyse heuristique et formule une lecture critique plus synthétique.",
    "generate_ai_analysis": "✨ Générer l’analyse IA",
    "ai_unavailable": "Module IA indisponible : clé OpenAI absente ou bibliothèque non installée.",
    "ai_analysis_result": "Analyse IA",
    "method": "Méthode",
    "original_formula": "Formule originelle",
    "articulated_knowledge_density": "G : densité de savoir articulé — sources, chiffres, noms, références, traces vérifiables.",
    "integration": "N : intégration — contexte, nuances, réserves, cohérence argumentative.",
    "assertive_rigidity": "D : rigidité assertive — certitudes non soutenues, emballement rhétorique.",
    "disclaimer": "Cette app ne remplace ni un journaliste, ni un chercheur, ni un greffier du réel. Mais elle retire déjà quelques masques au texte qui parade.",
}


# -----------------------------
# Triangle cognitif 3D
# -----------------------------
def plot_cognitive_triangle_3d(G: float, N: float, D: float):
    G_pt = [10, 0, 0]
    N_pt = [0, 10, 0]
    D_pt = [0, 0, 10]
    P = [G, N, D]

    fig = plt.figure(figsize=(8, 7))
    ax = fig.add_subplot(111, projection="3d")

    verts = [[G_pt, N_pt, D_pt]]
    tri = Poly3DCollection(
        verts,
        alpha=0.18,
        edgecolor="black",
        linewidths=1.5
    )
    ax.add_collection3d(tri)

    ax.plot(
        [G_pt[0], N_pt[0]],
        [G_pt[1], N_pt[1]],
        [G_pt[2], N_pt[2]],
        linewidth=2
    )
    ax.plot(
        [N_pt[0], D_pt[0]],
        [N_pt[1], D_pt[1]],
        [N_pt[2], D_pt[2]],
        linewidth=2
    )
    ax.plot(
        [D_pt[0], G_pt[0]],
        [D_pt[1], G_pt[1]],
        [D_pt[2], G_pt[2]],
        linewidth=2
    )

    ax.scatter(*G_pt, s=80)
    ax.scatter(*N_pt, s=80)
    ax.scatter(*D_pt, s=80)

    ax.text(G_pt[0] + 0.3, G_pt[1], G_pt[2], "G", fontsize=12, weight="bold")
    ax.text(N_pt[0], N_pt[1] + 0.3, N_pt[2], "N", fontsize=12, weight="bold")
    ax.text(D_pt[0], D_pt[1], D_pt[2] + 0.3, "D", fontsize=12, weight="bold")

    ax.scatter(*P, s=140, marker="o")
    ax.text(P[0] + 0.2, P[1] + 0.2, P[2] + 0.2, "Texte", fontsize=11, weight="bold")

    ax.plot([0, G], [0, 0], [0, 0], linestyle="--", linewidth=1)
    ax.plot([0, 0], [0, N], [0, 0], linestyle="--", linewidth=1)
    ax.plot([0, 0], [0, 0], [0, D], linestyle="--", linewidth=1)
    ax.plot([0, G], [0, N], [0, D], linestyle=":", linewidth=1.5)

    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_zlim(0, 10)

    ax.set_xlabel("G — gnōsis")
    ax.set_ylabel("N — nous")
    ax.set_zlabel("D — doxa")
    ax.set_title("Triangle cognitif 3D")
    ax.view_init(elev=24, azim=35)

    # -----------------------------
    # Zones cognitives dérivées
    # -----------------------------
    ax.text(
        0.2, 1.0, 8.5,
        "Mécroyance",
        fontsize=10,
        fontweight="bold"
    )
    ax.text(
        0.2, 0.4, 7.8,
        "Certitude > savoir + compréhension",
        fontsize=8
    )

    ax.text(
        7.0, 1.0, 5.8,
        "Pseudo-savoir",
        fontsize=10,
        fontweight="bold"
    )
    ax.text(
        7.0, 0.3, 5.0,
        "Savoir accumulé,\nmais mal intégré",
        fontsize=8
    )

    ax.text(
        1.0, 7.0, 5.8,
        "Intuition dogmatique",
        fontsize=10,
        fontweight="bold"
    )
    ax.text(
        1.0, 6.2, 5.0,
        "Conviction forte\nsans base de savoir",
        fontsize=8
    )

    return fig


# -----------------------------
# OpenAI client
# -----------------------------
def get_openai_client() -> Optional["OpenAI"]:
    if OpenAI is None:
        return None

    api_key = st.secrets.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        return OpenAI(api_key=api_key)
    except Exception:
        return None


client = get_openai_client()


# -----------------------------
# Header
# -----------------------------
st.markdown("""
<h1 style="text-align:center; font-size:36px;">
De la logique d’Aristote aux équations du discours
</h1>
""", unsafe_allow_html=True)

st.markdown(
    """
**DOXA Detector analyse la structure cognitive des discours grâce à un moteur analytique fondé sur des équations, des heuristiques linguistiques et des fonctions de calcul.**

**Basé entièrement sur du calcul, le cœur du modèle repose sur l’équation cognitive : M = (G + N) − D.**

**Dans la tradition logique inaugurée par Aristote — qui distinguait prémisses, raisonnements et sophismes — l’application examine les structures argumentatives présentes dans un texte.**

**L’application identifie les différentes formes de sophismes et autres procédés de persuasion présents dans un texte sans avoir besoin de connaître la définition des mots ; celle-ci n’étant utilisée qu’à titre optionnel via une analyse sémantique complémentaire.**

**Ces structures constituent souvent l’empreinte des biais du langage et permettent d’en révéler les mécanismes, aussi bien dans l’analyse des publications médiatiques que pour s’exercer à ne pas les reproduire.**

**L’intelligence artificielle n’intervient que comme module optionnel d’assistance et d’interprétation.**
"""
)

st.markdown(
    "<div style='border-top:1px solid #e6e6e6;margin:22px 0'></div>",
    unsafe_allow_html=True
)

with st.container(border=True):

    st.subheader("Analyser la structure cognitive d’un discours")

    st.write(
        "DOXA Detector examine un texte comme une IRM du raisonnement. "
        "L’application analyse la solidité argumentative, les sources, les affirmations, "
        "les signaux rhétoriques, les sophismes, la propagande et les dérives cognitives."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 1️⃣ Entrer un contenu")
        st.write(
            "Collez un texte, chargez une URL, analysez plusieurs articles "
            "sur un sujet ou utilisez la dictée vocale (microphone classique "
            "ou mobile). Les publications publiques peuvent également être "
            "chargées depuis certains réseaux ou pages web."
        )

    with col2:
        st.markdown("### 2️⃣ Lancer l’analyse")
        st.write(
            "Le moteur examine les affirmations, les sources, la cohérence "
            "du raisonnement et les indices linguistiques du discours. "
            "Il détecte également les sophismes, les procédés rhétoriques "
            "et les structures de persuasion."
        )

    with col3:
        st.markdown("### 3️⃣ Comprendre les résultats")
        st.write(
            "L’analyse produit plusieurs indicateurs : solidité argumentative, "
            "mécroyance, tension cognitive, pression rhétorique, propagande, "
            "gravité cognitive et diagnostic du cerveau DOXA."
        )


# =============================
# Philosophie derrière l'IRM
# =============================

st.markdown("### 🧠 La philosophie derrière l’IRM")

st.caption(
    "La notion de mécroyance et le modèle cognitif utilisé par DOXA Detector "
    "s’inscrivent dans une réflexion plus large sur la structure du langage "
    "et les mécanismes de formation des croyances."
)

st.link_button(
    "📖 Lire la philosophie complète du modèle (README)",
    "https://github.com/nrledard-web/Doxa-Detector-fr#readme",
    use_container_width=True
)

st.markdown(
    "<div style='border-top:1px solid #e6e6e6;margin:22px 0'></div>",
    unsafe_allow_html=True
)


# -----------------------------
# Modèle de cognition
# -----------------------------
class Cognition:
    def __init__(self, gnosis: float, nous: float, doxa: float):
        self.G = self.clamp(gnosis)
        self.N = self.clamp(nous)
        self.D = self.clamp(doxa)
        self.M = self.compute_mecroyance()

    @staticmethod
    def clamp(value: float, min_val: float = 0.0, max_val: float = 10.0) -> float:
        return max(min_val, min(max_val, value))

    def compute_mecroyance(self) -> float:
    
        discourse = getattr(self, "discourse_type", "").lower()
    
        if "fictionnel" in discourse or "mythique" in discourse:
            return (self.G + self.N) - (self.D * 0.3)
    
        if "poétique" in discourse or "littéraire" in discourse:
            return (self.G + self.N) - (self.D * 0.5)
    
        if "religieux" in discourse:
            return (self.G + self.N) - (self.D * 0.7)
    
        return (self.G + self.N) - self.D

    def interpret(self) -> str:
        m = self.M
        if m < 0:
            return T["zone_closure"]
        if 0 <= m <= 10:
            return T["zone_stability"]
        if 10 < m <= 17:
            return T["zone_lucidity"]
        if 17 < m < 19:
            return T["zone_rare"]
        if 19 <= m < 20:
            return T["zone_pansapience"]
        if m == 20:
            return T["zone_asymptote"]
        return T["out_of_spectrum"]


# =====================================================
# Mécroyance contextuelle selon le régime discursif
# =====================================================
def compute_contextual_mecroyance(G, N, D, discourse_type=""):
    discourse = discourse_type.lower()

    if "fiction" in discourse or "romanesque" in discourse or "narratif" in discourse:
        return (G + N) - (D * 0.3)

    if "poétique" in discourse or "littéraire" in discourse:
        return (G + N) - (D * 0.5)

    if "religieux" in discourse or "mythique" in discourse:
        return (G + N) - (D * 0.7)

    return (G + N) - D

# -----------------------------
# Exemple
# -----------------------------
SAMPLE_ARTICLE = (
    "L'intelligence artificielle va remplacer 80% des emplois d'ici 2030, selon une étude choc publiée hier par le cabinet GlobalTech. "
    "Le rapport de 45 pages affirme que les secteurs de la finance et de la santé seront les plus touchés. "
    "\"C'est une révolution sans précédent\", déclare Jean Dupont, expert en robotique. "
    "Cependant, certains économistes comme Marie Curie restent prudents : \"Il faut nuancer ces chiffres, car de nouveaux métiers vont apparaître.\" "
    "L'étude précise que 12 millions de postes pourraient être créés en Europe. "
    "Malgré cela, l'inquiétude grandit chez les salariés qui craignent pour leur avenir. "
    "Il est absolument certain que nous allons vers une crise sociale majeure si rien n'est fait immédiatement."
)

# -----------------------------
# Helpers
# -----------------------------
def clamp(n: float, minn: float, maxn: float) -> float:
    return max(min(maxn, n), minn)

INGROUP_TERMS = [
    "citoyens",
    "peuple",
    "gens honnêtes",
    "honnêtes citoyens",
    "ceux qui disent la vérité",
    "ceux qui ouvrent les yeux",
    "la population",
    "les travailleurs",
    "les familles",
    "les innocents",
    "les justes",
]

OUTGROUP_TERMS = [
    "élites",
    "système",
    "médias",
    "autorités",
    "oligarchie",
    "classe dirigeante",
    "puissants",
    "dominants",
    "bureaucrates",
    "technocrates",
]

def compute_linguistic_suspicion(text: str) -> dict:
    """
    Amplificateur linguistique simple pour le mensonge brut.
    Retourne un facteur L entre 1.0 et 2.0 environ.
    """
    if not text:
        return {
            "L": 1.0,
            "rhetorical_pressure": 0,
            "absolute_claims": 0,
            "vague_authority": 0,
            "dramatic_framing": 0,
            "lack_of_nuance": 0,
            "trigger_count": 0,
        }

    t = text.lower()

    rhetorical_pressure_terms = [
        "clearly", "obviously", "without doubt", "there is no doubt",
        "the truth is", "everyone knows", "it is certain", "undeniable",
        "il est évident", "sans aucun doute", "la vérité est",
        "tout le monde sait", "il est certain", "indéniable"
    ]

    absolute_claim_terms = [
        "always", "never", "everyone", "nobody", "all", "none",
        "toujours", "jamais", "tout le monde", "personne", "tous", "aucun"
    ]

    dramatic_framing_terms = [
        "shocking truth", "what they don't want you to know", "unbelievable",
        "hidden truth", "explosive revelation", "scandalous",
        "vérité choquante", "ce qu'on ne veut pas que vous sachiez",
        "incroyable", "vérité cachée", "révélation explosive", "scandaleux"
    ]

    nuance_terms = [
        "may", "might", "could", "perhaps", "possibly", "suggests", "appears",
        "peut", "pourrait", "peut-être", "possiblement", "semble", "suggère"
    ]

    def count_hits(terms):
        return sum(1 for term in terms if contains_term(t, term))

    rhetorical_pressure = count_hits(rhetorical_pressure_terms)
    absolute_claims = count_hits(STRONG_CERTAINTY_MARKERS)
    vague_authority = count_hits(VAGUE_AUTHORITY_TERMS)
    dramatic_framing = count_hits(dramatic_framing_terms)
    nuance_hits = count_hits(nuance_terms)
    ingroup_hits = count_hits(INGROUP_TERMS)
    outgroup_hits = count_hits(OUTGROUP_TERMS)
    
    structural_polarization = (
        2 if ingroup_hits > 0 and outgroup_hits > 0 else 0
    )

    lack_of_nuance = 2 if nuance_hits == 0 else 1 if nuance_hits <= 2 else 0

    raw_score = (
        rhetorical_pressure
        + absolute_claims
        + vague_authority
        + dramatic_framing
        + lack_of_nuance
        + structural_polarization
    )

    L = 1.0 + min(raw_score / 8.0, 1.0)

    return {
        "L": round(L, 3),
        "rhetorical_pressure": rhetorical_pressure,
        "absolute_claims": absolute_claims,
        "vague_authority": vague_authority,
        "dramatic_framing": dramatic_framing,
        "lack_of_nuance": lack_of_nuance,
        "trigger_count": raw_score,
        "structural_polarization": structural_polarization,
    }
# -----------------------------
# Bibliothèques rhétoriques
# -----------------------------
VICTIMISATION = [
    "on nous empêche d'agir",
    "on veut nous faire taire",
    "on refuse d'entendre le peuple",
    "le peuple est abandonné",
    "les français sont abandonnés",
    "nous sommes attaqués",
    "nous sommes affaiblis",
    "nous sommes pénalisés",
    "le pays est sacrifié",
    "nos efforts sont méprisés",
    "ordinary people are ignored",
    "the people have been abandoned",
    "we are being silenced",
    "we are under attack"
]
MORALISATION = [
    "c'est une question de responsabilité",
    "c'est notre devoir",
    "nous avons le devoir",
    "nous devons être à la hauteur",
    "ce serait irresponsable",
    "il serait irresponsable",
    "notre devoir moral",
    "nous n'avons pas le droit d'échouer",
    "nous devons protéger nos enfants",
    "nous devons défendre l'avenir",
    "it is our duty",
    "it would be irresponsible",
    "we must protect our children"
    "il serait irresponsable de",
    "nous avons le devoir de",
    "nous avons la responsabilité de",
    "la justice exige",
    "la morale exige",
    "il est moralement nécessaire",
    "personne ne peut rester indifférent",
    "nous ne pouvons pas rester indifférents",
    "il serait immoral de",
    "il serait injuste de",
    "il est de notre devoir",
    "nous devons protéger",
    "nous devons défendre",
    "nous devons agir",
    "nous devons faire face",
    "it would be irresponsible",
    "we have a duty to",
    "we have a responsibility to",
    "justice requires",
    "we cannot remain indifferent"
]
URGENCE = [
    "il faut agir maintenant",
    "il faut agir immédiatement",
    "sans attendre",
    "avant qu'il ne soit trop tard",
    "il est encore temps",
    "nous devons agir vite",
    "immédiatement",
    "dès maintenant",
    "urgence absolue",
    "time is running out",
    "we must act now",
    "before it is too late",
    "immediately"
]
PROMESSE_EXCESSIVE = [
    "nous allons tout changer",
    "nous allons changer la vie",
    "nous allons redresser le pays",
    "nous allons sauver l'économie",
    "nous allons protéger tout le monde",
    "nous garantirons l'avenir",
    "nous garantirons la prospérité",
    "nous garantirons la sécurité",
    "nous allons rétablir l'ordre",
    "we will fix everything",
    "we will restore prosperity",
    "we will guarantee security"
]
POPULISME_ANTI_ELITE = [
    "les élites ont trahi",
    "les élites méprisent le peuple",
    "le peuple contre les élites",
    "les puissants contre le peuple",
    "les technocrates",
    "les bureaucrates de bruxelles",
    "la caste",
    "l'oligarchie",
    "les élites mondialisées",
    "le système est verrouillé",
    "ceux d'en haut",
    "la finance décide de tout",
    "les banques gouvernent",
    "les marchés imposent leur loi",
    "ordinary people versus the elite",
    "the elite has failed",
    "the establishment betrayed the people",
    "the system is rigged"
]
PROGRESSISME_IDENTITAIRE = [
    "les dominations systémiques",
    "la violence systémique",
    "le racisme systémique",
    "les discriminations structurelles",
    "les privilèges invisibles",
    "les privilèges blancs",
    "les privilèges de classe",
    "déconstruire les normes",
    "déconstruire les stéréotypes",
    "remettre en cause les normes",
    "les identités minorisées",
    "les corps minorisés",
    "les personnes marginalisées",
    "les vécus minoritaires",
    "intersection des oppressions",
    "les rapports de domination",
    "check your privilege",
    "systemic oppression",
    "structural discrimination",
    "deconstruct gender norms",
    "marginalized voices",
    "lived experience matters",
    "the personal is political"
]
SOCIALISME_COMMUNISME = [
    "les travailleurs exploités",
    "la lutte des classes",
    "le capital détruit",
    "le capital exploite",
    "les possédants",
    "les exploiteurs",
    "la bourgeoisie",
    "le patronat prédateur",
    "les riches doivent payer",
    "reprendre les richesses",
    "socialiser les moyens de production",
    "redistribuer les richesses",
    "mettre fin au capitalisme",
    "abolir l'exploitation",
    "protéger les services publics contre le marché",
    "workers are exploited",
    "class struggle",
    "the ruling class",
    "end capitalism",
    "redistribute wealth",
    "the wealthy must pay",
    "public ownership"
]
CONFUSION_DELEGITIMATION = [
    "tout populisme est d'extrême droite",
    "le populisme mène toujours au fascisme",
    "toute critique est réactionnaire",
    "toute opposition est haineuse",
    "qui n'est pas avec nous est contre nous",
    "refuser cette réforme c'est refuser le progrès",
    "critiquer cela c'est être raciste",
    "critiquer cela c'est être sexiste",
    "critiquer cela c'est être transphobe",
    "toute réserve est suspecte",
    "there is only one acceptable position",
    "any criticism is hate",
    "if you disagree you are on the wrong side of history"
]
AUTORITE_ACADEMIQUE_VAGUE = [
    "selon plusieurs études",
    "selon certaines études",
    "selon une étude récente",
    "selon des chercheurs",
    "selon certains chercheurs",
    "selon plusieurs chercheurs",
    "plusieurs études suggèrent",
    "plusieurs travaux suggèrent",
    "les analyses montrent",
    "les analyses suggèrent",
    "les données montrent",
    "les données indiquent",
    "les données disponibles",
    "les recherches montrent",
    "les recherches suggèrent",
    "la littérature scientifique",
    "le consensus scientifique",
    "de nombreux spécialistes",
    "certains spécialistes",
    "de nombreux experts",
    "certains experts",
    "plusieurs experts",
    "de nombreux analystes",
    "plusieurs analystes",
    "the data suggests",
    "available data shows",
    "research suggests",
    "studies suggest",
    "experts agree",
    "many specialists"
]
DILUTION_RESPONSABILITE = [
    "il ne s'agit pas d'accuser",
    "il ne s'agit pas de blâmer",
    "il ne s'agit pas de désigner",
    "personne ne cherche à accuser",
    "il faut simplement reconnaître",
    "il faut seulement reconnaître",
    "il s'agit simplement de constater",
    "il s'agit seulement de constater",
    "il convient de reconnaître",
    "il faut admettre que",
    "il serait naïf d'ignorer",
    "ignorer cette réalité reviendrait à",
    "ce n'est pas une accusation",
    "sans mettre en cause quiconque",
    "sans désigner de coupable",
    "without blaming anyone",
    "this is not about blaming",
    "it is simply necessary to recognize",
    "it would be naive to ignore"
]
CAUSALITE_IMPLICITE = [
    "depuis que",
    "depuis l'introduction de",
    "depuis la mise en place de",
    "depuis l'arrivée de",
    "suite à",
    "à cause de",
    "en raison de",
    "cela a conduit à",
    "cela explique",
    "cela montre que",
    "ce qui prouve que",
    "ce qui démontre que",
    "ce qui explique que",
    "c'est pourquoi",
    "d'où",
    "ce qui entraîne",
    "ce qui conduit à",
    "ce qui provoque",
    "which explains",
    "this proves that",
    "this shows that",
    "this leads to",
]
ABSOLUTE_PREDICTION_MARKERS = [
    "il est certain que",
    "il est absolument certain",
    "il est évident que",
    "il est inévitable",
    "c'est inévitable",
    "cela va provoquer",
    "cela va entraîner",
    "cela va conduire",
    "nous allons vers",
    "nous allons assister à",
    "va nécessairement",
    "finira par",
]
STRONG_CERTAINTY_MARKERS = [
    # tes marqueurs (gardés)
    "il est absolument certain",
    "il ne fait aucun doute",
    "sans aucun doute",
    "il est évident que",
    "il est incontestable",
    "cela prouve que",
    "preuve irréfutable",
    "personne ne peut nier",
    "de toute évidence",

    # AJOUTS CRITIQUES
    "absolument certain",
    "c'est certain",
    "c'est évident",
    "évident",
    "indiscutable",
    "indéniable",
    "aucun doute",
    "il est clair que",
    "clairement",
    "évidemment",
    "forcément",
    "inévitable",
    "inévitablement",
    "il est impossible que",
    "cela ne peut pas être faux"
]
STRONG_CERTAINTY_MARKERS += [
    "systématiquement",
    "jamais",
    "personne ne mentionne",
    "ceux qui disent la vérité",
    "ceux qui ouvrent les yeux",
    "immédiatement",
    "nécessaire d'agir",
    "nécessaire d’agir",
    "avant qu'il ne soit trop tard",
    "avant qu’il ne soit trop tard",
]
def detect_political_patterns(text: str):
    """
    Détecte des manœuvres discursives politiques ou rhétoriques
    à partir de bibliothèques d'expressions.
    Retourne :
    - total_score : nombre total d'occurrences détectées
    - results : nombre d'occurrences par catégorie
    - matched_terms : expressions effectivement trouvées
    """
    if not text:
        return 0, {}, {}

    t = text.lower()

    categories = {
        "certitude": CERTITUDE_PERFORMATIVE,
        "autorite": AUTORITE_VAGUE,
        "autorite_academique": AUTORITE_ACADEMIQUE_VAGUE,
        "dramatisation": DRAMATISATION,
        "generalisation": GENERALISATION,
        "naturalisation": NATURALISATION,
        "ennemi": ENNEMI_ABSTRAIT,
        "victimisation": VICTIMISATION,
        "moralisation": MORALISATION,
        "urgence": URGENCE,
        "promesse": PROMESSE_EXCESSIVE,
        "populisme": POPULISME_ANTI_ELITE,
        "progressisme_identitaire": PROGRESSISME_IDENTITAIRE,
        "socialisme_communisme": SOCIALISME_COMMUNISME,
        "delegitimation": CONFUSION_DELEGITIMATION,
        "dilution": DILUTION_RESPONSABILITE,
        "causalite": CAUSALITE_IMPLICITE,
    }

    results = {}
    matched_terms = {}
    total_score = 0

    for name, terms in categories.items():
        hits = [term for term in terms if contains_term(t, term)]
        results[name] = len(hits)
        matched_terms[name] = hits
        total_score += len(hits)

    return total_score, results, matched_terms


def compute_rhetorical_pressure(results: dict) -> float:
    """
    Calcule une pression rhétorique pondérée entre 0.0 et 1.0.
    Modère la pression lorsque le texte rapporte des propos plutôt qu'il ne les assume.
    """

    rhetorical = results.get("rhetorical_scores", {})
    emotions = results.get("emotional_registers", {})

    if not rhetorical:
        return 0.0

    pressure = (
        rhetorical.get("amplification", 0) * 0.16
        + rhetorical.get("saturation_rhetorique", 0) * 0.20
        + rhetorical.get("persuasion", 0) * 0.12
        + rhetorical.get("attaque", 0) * 0.14
        + rhetorical.get("implicite", 0) * 0.08
        + rhetorical.get("soupcon_systemique", 0) * 0.10
        + rhetorical.get("coherence_performative", 0) * 0.08
        + emotions.get("colere", 0) * 0.08
        + emotions.get("peur", 0) * 0.04
    )

    # -----------------------------
    # Modération du discours rapporté
    # -----------------------------
    reported_speech = max(
        results.get("reported_speech_score", 0),
        results.get("reported_speech_ratio", 0),
        results.get("reported_speech", 0),
        results.get("reported_speech_gauge", 0),
    )

    if reported_speech > 0.45:
        pressure *= 0.65
    elif reported_speech > 0.25:
        pressure *= 0.80

    return round(min(max(pressure, 0), 1.0), 3)
    

def interpret_rhetorical_pressure(value: float):
    """
    Traduit la pression rhétorique en étiquette + couleur.
    Jauge de vigilance : même faible, elle ne devient pas verte.
    """
    if value < 0.20:
        return "Faible", "#ca8a04"      # jaune / ocre
    elif value < 0.40:
        return "Modérée", "#f97316"    # orange
    elif value < 0.70:
        return "Élevée", "#ea580c"     # orange foncé
    else:
        return "Très élevée", "#dc2626" # rouge
        
        
def compute_propaganda_gauge(
    lie_gauge: float,
    rhetorical_pressure: float,
    closure: float,

    false_consensus: float,
    moral_polarization: float,
    binary_opposition: float,
    victimization: float,
    semantic_shift: float,
    false_dilemma: float,

    saturation_rhetorique: float = 0.0,
    soupcon_systemique: float = 0.0,
    attaque: float = 0.0,
    amplification: float = 0.0,
    colere: float = 0.0,
    peur: float = 0.0,
    reported_speech: float = 0.0,
):
    """
    Jauge propagandiste structurelle modernisée.
    """
    # Modération émotionnelle si le texte rapporte surtout des propos extérieurs
    
    if reported_speech > 0.45:
        colere *= 0.65
        peur *= 0.65
    elif reported_speech > 0.25:
        colere *= 0.80
        peur *= 0.80
        
    ideological_core = (
        false_consensus
        + moral_polarization
        + binary_opposition
        + victimization
        + semantic_shift
        + false_dilemma
    ) / 6

    rhetorical_core = (
        saturation_rhetorique * 0.30
        + soupcon_systemique * 0.25
        + attaque * 0.20
        + amplification * 0.15
        + colere * 0.07
        + peur * 0.03
    )

    score = (
        0.18 * lie_gauge +
        0.18 * rhetorical_pressure +
        0.12 * closure +
        0.32 * ideological_core +
        0.20 * rhetorical_core
    )

    return clamp(score, 0.0, 1.0)

def interpret_propaganda_gauge(value: float):
    """
    Traduit l'indice propagandiste en étiquette + couleur + commentaire.
    Même faible, la jauge reste une vigilance (pas de vert).
    """
    if value < 0.20:
        return "Très faible", "#ca8a04", "Le texte ne présente pas de structure propagandiste marquée."
    elif value < 0.40:
        return "Faible", "#f97316", "Le discours peut orienter légèrement la perception, sans verrouillage fort."
    elif value < 0.60:
        return "Modéré", "#ea580c", "Le texte contient plusieurs éléments compatibles avec une mise en orientation du lecteur."
    elif value < 0.80:
        return "Élevé", "#dc2626", "Le discours semble fortement orienté et cherche à imposer un cadrage interprétatif."
    else:
        return "Très élevé", "#7f1d1d", "Le texte présente une structure fortement propagandiste ou de verrouillage idéologique."

def interpret_discursive_profile(
    lie_gauge: float,
    rhetorical_pressure: float,
    propaganda_gauge: float,
    premise_score: float = 0.0,
    logic_confusion_score: float = 0.0,
    scientific_simulation_score: float = 0.0,
    discursive_coherence_score: float = 0.0,
) -> str:
    if propaganda_gauge >= 0.75 and rhetorical_pressure >= 0.60:
        return "Structure discursive fortement propagandiste"
    elif logic_confusion_score >= 0.55 and premise_score >= 0.45:
        return "Discours cohérent reposant sur des prémisses fragiles"
    elif scientific_simulation_score >= 0.50 and premise_score >= 0.35:
        return "Discours pseudo-objectif ou pseudo-scientifique"
    elif lie_gauge >= 0.65 and rhetorical_pressure >= 0.45:
        return "Structure discursive manipulatoire probable"
    
    elif discursive_coherence_score >= 13 and premise_score < 0.20 and logic_confusion_score < 0.20:
        return "Discours plutôt cohérent et peu verrouillant"
    
    elif (
        discursive_coherence_score >= 11
        and rhetorical_pressure < 0.35
        and lie_gauge < 0.45
        and premise_score >= 0.20
    ):
        return "Discours analytique ou spéculatif relativement nuancé"
    
    elif (
        scientific_simulation_score < 0.30
        and logic_confusion_score < 0.30
        and rhetorical_pressure < 0.30
        and premise_score >= 0.25
    ):
        return "Discours conceptuel ou philosophique"
    
    elif propaganda_gauge >= 0.45 or rhetorical_pressure >= 0.45:
        return "Discours fortement orienté"
    
    elif lie_gauge < 0.40 and rhetorical_pressure < 0.35:
        return "Discours plutôt sincère ou peu verrouillant"
    
    else:
        return "Discours ambigu ou mixte"

# =========================================================
# MODULATION CONTEXTUELLE DES DISCOURS
# =========================================================

DISCOURSE_MODIFIERS = {

    "philosophique": {
        "false_dilemma_score": 0.45,
        "logical_jump_score": 0.60,
        "strong_certainty_score": 0.45,
        "misleading_comparison_score": 0.45,
        "scientific_simulation_score": 0.60,
        "frame_shift_score": 0.55,
    },

    "technocratique": {
        "scientific_simulation_score": 1.25,
        "abstraction_score": 1.15,
        "premise_score": 1.10,
    },

    "pamphlétaire": {
        "emotional_intensity_score": 0.75,
        "propaganda_score": 1.10,
        "rhetorical_pressure": 1.10,
    },

    "journalistique": {
        "scientific_simulation_score": 0.85,
        "false_dilemma_score": 0.80,
    },

    "religieux": {
        "false_dilemma_score": 0.60,
        "logical_jump_score": 0.70,
    },
    
    "economie_politique": {
        "false_dilemma_score": 0.40,
        "logical_jump_score": 0.70,
        "strong_certainty_score": 0.45,
        "misleading_comparison_score": 0.65,
        "scientific_simulation_score": 0.75,
        "premise_score": 0.70,
        "propaganda_score": 0.65,
        "threat_amplification_score": 0.55,
        "coherence_trompeuse_score": 0.75,
    },
    "encyclopedique": {
        "saturation_rhetorique": 0.25,
        "coherence_performative": 0.35,
        "compression_cognitive": 0.55,
        "propaganda_score": 0.35,
        "rhetorical_pressure": 0.45,
    },
    
    "definitionnel": {
        "saturation_rhetorique": 0.45,
        "coherence_performative": 0.55,
    },
}

def apply_discourse_modifiers(result: dict):

    discourse = result.get("discourse_type_rhetoric", "").lower()
    
    if "philosophique" in discourse:
        discourse_key = "philosophique"
    elif "technocratique" in discourse:
        discourse_key = "technocratique"
    elif "economie_politique" in discourse:
        discourse_key = "economie_politique"
    elif "journalistique" in discourse:
        discourse_key = "journalistique"
    elif "pamphlétaire" in discourse:
        discourse_key = "pamphlétaire"
    elif "religieux" in discourse:
        discourse_key = "religieux"
    else:
        discourse_key = discourse
    
    modifiers = DISCOURSE_MODIFIERS.get(discourse_key, {})

    for key, factor in modifiers.items():
        if key in result:
            result[key] = round(result[key] * factor, 3)

    return result
    

def interpret_closure_gauge(value: float):
    """
    Traduit la clôture cognitive en étiquette + couleur + commentaire.
    """
    if value < 0.40:
        return "Ouverture cognitive", "#16a34a", "Le texte reste assez révisable."
    elif value < 0.75:
        return "Rigidification modérée", "#ca8a04", "Le discours commence à se refermer sur ses certitudes."
    elif value < 1.10:
        return "Clôture élevée", "#f97316", "La certitude domine nettement l’ancrage cognitif."
    else:
        return "Clôture critique", "#dc2626", "Le texte semble fortement verrouillé par sa propre structure."

def generate_share_block(result):

    credibility = result.get("hard_fact_score", 0)

    gravity = result.get(
        "cognitive_gravity",
        0
    )

    stability = result.get(
        "cognitive_stability",
        0
    )

    regime = result.get(
        "dominant_regime",
        ""
    )

    verdict = result.get(
        "brain_verdict",
        ""
    )

    # -----------------------------
    # Red flags lisibles
    # -----------------------------
    flags_lines = []

    red_flags = result.get("red_flags", [])

    if isinstance(red_flags, list):
        for flag in red_flags:
            if isinstance(flag, dict):
                name = flag.get("name", "Signal détecté")
                reason = flag.get("reason", "")
                if reason:
                    flags_lines.append(f"- {name} : {reason}")
                else:
                    flags_lines.append(f"- {name}")
            else:
                flags_lines.append(f"- {flag}")

    # Catégories rhétoriques détectées
    patterns = result.get("political_patterns", {})

    if isinstance(patterns, dict):
        for name, count in patterns.items():
            if count and count > 0:
                clean_name = name.replace("_", " ").capitalize()
                flags_lines.append(f"- {clean_name} ({count})")

    if flags_lines:
        flags_text = "\n".join(flags_lines[:12])
    else:
        flags_text = "Aucun signal rhétorique majeur détecté"

    summary = f"""
Analyse DOXA Detector

Crédibilité : {credibility}/20
Gravité cognitive : {gravity}
Stabilité cognitive : {stability}

Régime dominant : {regime}

Verdict :
{verdict}

🚩 Signaux détectés :
{flags_text}

Analyse réalisée avec DOXA Detector
https://doxa-detector-fr-krsbrtpqc6kucpdg9bfgv2.streamlit.app/

M = (G + N) − D
"""

    encoded = urllib.parse.quote(summary)

    return summary, encoded

def render_custom_gauge(value: float, color: str):
    value = max(0.0, min(1.0, value))
    st.markdown(f"""
    <div style="width:100%; margin-top:10px; margin-bottom:10px;">
        <div style="
            width:100%;
            height:26px;
            background:#e5e7eb;
            border-radius:12px;
            overflow:hidden;
            border:1px solid #cbd5e1;
        ">
            <div style="
                width:{value*100}%;
                height:100%;
                background:{color};
                transition:width 0.4s ease;
            "></div>
        </div>
    </div>
    """, unsafe_allow_html=True)       

@st.cache_data(show_spinner=False, ttl=3600)
def extract_article_from_url(url: str) -> str:
    try:
        article = Article(url)
        article.download()
        article.parse()

        if article.text and len(article.text.strip()) > 300:
            return article.text.strip()

    except Exception:
        pass

    # Fallback HTML simple
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return ""

        html = response.text

        # Nettoyage basique
        html = re.sub(r"<script.*?</script>", " ", html, flags=re.DOTALL)
        html = re.sub(r"<style.*?</style>", " ", html, flags=re.DOTALL)
        html = re.sub(r"<[^>]+>", " ", html)
        html = re.sub(r"\s+", " ", html).strip()

        if len(html) > 300:
            return html[:8000]

        return ""

    except Exception:
        return ""


@st.cache_data(show_spinner=False, ttl=1800)
def search_articles_by_keyword(keyword: str, max_results: int = 10) -> List[Dict]:
    articles = []
    seen_urls = set()

    api_key = st.secrets.get("NEWS_API_KEY")
    from_date_iso = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

    # -----------------------------
    # 1) Priorité : NewsAPI
    # -----------------------------
    if api_key:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": keyword,
            "language": "fr",
            "sortBy": "publishedAt",
            "pageSize": max_results * 3,
            "apiKey": api_key,
        }

        try:
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 200:
                data = response.json()

                for art in data.get("articles", []):
                    article_url = art.get("url")
                    title = art.get("title", "Sans titre")
                    source = art.get("source", {}).get("name", "Source inconnue")
                    published_at = art.get("publishedAt", "")

                    if not article_url or article_url in seen_urls:
                        continue

                    seen_urls.add(article_url)

                    articles.append({
                        "title": title,
                        "url": article_url,
                        "source": source,
                        "published_at": published_at,
                    })

                    if len(articles) >= max_results:
                        return articles

        except Exception as e:
            st.warning(f"Erreur NewsAPI : {e}")

    # -----------------------------
    # 2) Fallback DDGS
    # -----------------------------
    try:
        clean_keyword = keyword.strip()

        core_query = clean_keyword.lower()
        core_query = core_query.replace(" wiki", "").replace(" wikipedia", "").strip()

        for article_word in ["le ", "la ", "les ", "un ", "une ", "des "]:
            if core_query.startswith(article_word):
                core_query = core_query[len(article_word):]

        queries = [
            f'"{core_query}"',
            f'"{core_query}" France',
        ]

        results = []

        with DDGS() as ddgs:
            for query in queries:
                try:
                    temp_results = list(ddgs.text(query, max_results=max_results * 8))

                    if temp_results:
                        results = temp_results
                        break

                except Exception:
                    continue

        if not results:
            return articles

        for r in results:
            url = r.get("href", "")
            title = r.get("title", "Sans titre")
            snippet = r.get("body", "")

            if not url or url in seen_urls:
                continue

            title_l = title.lower()
            url_l = url.lower()
            
            # Filtre souple : au moins un mot significatif dans le titre, l'extrait ou l'URL
            query_words = [w for w in core_query.split() if len(w) > 3]
            
            if query_words:
                title_hits = sum(1 for w in query_words if w in title_l)
                snippet_hits = sum(1 for w in query_words if w in snippet.lower())
                url_hits = sum(1 for w in query_words if w in url_l)
            
                if title_hits + snippet_hits + url_hits < 1:
                    continue

            bad_url_parts = [
                "/tag/",
                "/tags/",
                "/search",
                "/recherche",
                "/category/",
                "/categorie/",
            ]

            if any(part in url.lower() for part in bad_url_parts):
                continue

            blocked_domains = [
                "salonbeige.fr",
                "lesalonbeige.fr",
            ]

            if any(domain in url.lower() for domain in blocked_domains):
                continue

            seen_urls.add(url)

            text = fetch_text_for_textarea(url)

            if not text or len(text.strip()) < 500:
                continue

            web_noise = detect_web_noise(text)

            if web_noise["is_noise"]:
                continue

            # analysis = analyze_article(text)

            articles.append({
                "title": title,
                "url": url,
                "source": url.split("/")[2] if "://" in url else url,
                "published_at": "",
            })

            if len(articles) >= max_results:
                break
                
    except Exception as e:
        st.warning(f"Erreur DDGS : {e}")

    return articles
# -----------------------------
# Jauge mécroyance / mensonge
# -----------------------------
def compute_lie_gauge(M: float, ME: float):
    """
    Axe unique :
    0.0 = mécroyance forte
    0.5 = zone ambiguë
    1.0 = mensonge fort

    M et ME sont d'abord normalisés pour éviter
    qu'un seul indice n'écrase artificiellement l'autre.
    """
    # M : spectre théorique approximatif de -10 à +20
    m_norm = max(0.0, min(1.0, (M + 10) / 30))

    # ME : compressé sur 0..20
    me_norm = max(0.0, min(1.0, ME / 20))

    # Plus ME monte et plus M baisse, plus on va vers le mensonge
    delta = me_norm - (1 - m_norm)

    gauge = 0.5 + (delta * 0.8)
    gauge = max(0.0, min(1.0, gauge))

    if gauge < 0.20:
        label = "Mécroyance forte"
        color = "#a16207"
    
    elif gauge < 0.40:
        label = "Mécroyance modérée"
        color = "#ca8a04"
    
    elif gauge < 0.60:
        label = "Zone ambiguë"
        color = "#f59e0b"
    
    elif gauge < 0.75:
        label = "Manipulation probable"
        color = "#f97316"
    
    elif gauge < 0.92:
        label = "Manipulation forte probable"
        color = "#dc2626"
    
    else:
        label = "Mensonge probable"
        color = "#7f1d1d"
    
    if gauge < 0.5:
        intensity = (0.5 - gauge) * 0.8
    else:
        intensity = (gauge - 0.5) * 2
    
    return {
        "gauge": round(gauge, 3),
        "label": label,
        "color": color,
        "ME": round(ME, 2),
        "intensity": round(intensity, 3),
    }
    
@dataclass
class Claim:
    text: str
    has_number: bool
    has_date: bool
    has_named_entity: bool
    has_source_cue: bool
    absolutism: int
    emotional_charge: int
    verifiability: float
    risk: float
    status: str
    claim_types: List[str]
    epistemic_note: str
    short_adjustment: float
    aristotelian_type: Optional[str]
    subject_term: Optional[str]
    predicate_term: Optional[str]
    middle_term_candidate: Optional[str]


SOURCE_CUES = [
    "selon", "affirme", "déclare", "rapport", "étude", "expert",
    "source", "dit", "écrit", "publié", "annonce", "confirme", "révèle",
]
# -----------------------------
# Marqueurs propositions aristotéliciennes
# -----------------------------
SYLLOGISTIC_MARKERS = {
    "A": ["tous", "tout", "chaque"],
    "E": ["aucun", "nul"],
    "I": ["certains", "quelques", "plusieurs"],
    "O": ["certains", "quelques"]
}
# -----------------------------
# Normalisation pluriels irréguliers
# -----------------------------
IRREGULAR_NORMALIZATIONS = {
    "animaux": "animal",
    "chevaux": "cheval",
    "travaux": "travail",
    "journaux": "journal",
    "médias": "média",
    "reptiles": "reptile",
    "serpents": "serpent",
    "chiens": "chien",
    "mammifères": "mammifère",
    "hommes": "homme",
}
ABSOLUTIST_WORDS = [
    "toujours", "jamais", "absolument", "certain", "certaine",
    "prouvé", "prouvée", "incontestable", "tous", "aucun",
]
EMOTIONAL_WORDS = [
    "choc", "incroyable", "terrible", "peur", "menace",
    "scandale", "révolution", "urgent", "catastrophe", "crise",
]
NUANCE_MARKERS = [
    "cependant", "pourtant", "néanmoins", "toutefois", "mais",
    "nuancer", "prudence", "possible", "peut-être", "semble",
]
CERTITUDE_PERFORMATIVE = [
    "il est évident",
    "il est clair que",
    "sans aucun doute",
    "il est absolument certain",
    "les faits sont clairs",
    "personne ne peut nier",
    "la réalité est simple",
    "clearly",
    "it is obvious",
    "without any doubt",
    "there is no doubt"
]
AUTORITE_VAGUE = [
    "selon des experts",
    "des sources indiquent",
    "selon certains spécialistes",
    "plusieurs analystes pensent",
    "des rapports suggèrent",
    "according to sources",
    "experts say",
    "insiders say",
    "many specialists"
]
DRAMATISATION = [
    "crise majeure",
    "catastrophe imminente",
    "menace historique",
    "situation explosive",
    "choc politique",
    "crise sans précédent",
    "unprecedented crisis",
    "historic threat",
    "major collapse"
]
GENERALISATION = [
    "tout le monde sait",
    "les citoyens pensent",
    "les gens comprennent",
    "les Français savent",
    "everyone knows",
    "people understand",
    "everyone realizes"
]
NATURALISATION = [
    "il n'y a pas d'alternative",
    "c'est la seule solution",
    "c'est inévitable",
    "nous devons agir",
    "unavoidable",
    "necessary reform",
    "no alternative"
]
ENNEMI_ABSTRAIT = [
    "certaines forces",
    "des intérêts puissants",
    "certains groupes",
    "des acteurs étrangers",
    "hostile forces",
    "external actors"
]
# -----------------------------
# Helpers pour les nouveaux modules
# -----------------------------
def unique_keep_order(items):
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out

def contains_term(text: str, term: str) -> bool:
    escaped = re.escape(term.lower())
    if " " in term or "-" in term or "'" in term:
        pattern = escaped
    else:
        pattern = rf"\b{escaped}\b"
    return re.search(pattern, text.lower()) is not None

# -----------------------------
# Détection page index / multi-liens
# -----------------------------
def detect_index_or_multilink_page(text: str, url: str = ""):
    if not text or not text.strip():
        return {
            "is_index_page": False,
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune structure de page index détectée."
        }

    t = text.lower()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    short_lines = [l for l in lines if len(l.split()) <= 9]

    url_hits = re.findall(r"https?://|www\.|\.fr|\.com|\.org|\.gouv|\.eu", t)

    index_markers = [
        "voir aussi",
        "articles liés",
        "lire aussi",
        "communiqués",
        "actualités",
        "toutes les actualités",
        "point de situation",
        "mise à jour",
        "dossier",
        "page suivante",
        "archives",
        "rubrique",
        "accueil",
        "sommaire",
    ]

    marker_hits = unique_keep_order(
        [m for m in index_markers if contains_term(t, m)]
    )

    line_ratio = len(short_lines) / len(lines) if lines else 0
    url_density = len(url_hits) / max(len(text.split()), 1)

    raw_score = (
        line_ratio * 0.45 +
        min(url_density * 8, 0.35) +
        min(len(marker_hits) * 0.08, 0.25)
    )

    score = min(raw_score, 1.0)

    is_index_page = score >= 0.45 or (line_ratio > 0.65 and len(lines) >= 12)

    if is_index_page:
        interpretation = (
            "Page de navigation ou page multi-liens détectée : le texte semble composé "
            "principalement de titres, rubriques ou liens. L’analyse doit être prudente."
        )
    else:
        interpretation = "Le texte ne semble pas être principalement une page index ou multi-liens."

    return {
        "is_index_page": is_index_page,
        "score": round(score, 3),
        "markers": marker_hits + url_hits[:10],
        "interpretation": interpretation
    } 
# -----------------------------
# Filtre anti-pages non articles
# -----------------------------
BAD_ARTICLE_DOMAINS = [
    "depositphotos", "shutterstock", "gettyimages", "istockphoto",
    "alamy", "dreamstime", "adobestock", "123rf", "pinterest",
    "facebook", "instagram", "youtube", "tiktok",
]

BAD_ARTICLE_WORDS = [
    "images libres de droit",
    "photos libres de droit",
    "stock photo",
    "royalty free",
    "banque d'images",
    "current page requires javascript",
    "javascript",
    "connexion",
    "créez un compte",
    "tarifs",
    "vidéos",
    "musique et sons",
]

def is_bad_article_candidate(url: str = "", title: str = "", snippet: str = "") -> bool:
    raw = f"{url} {title} {snippet}".lower()

    if any(domain in raw for domain in BAD_ARTICLE_DOMAINS):
        return True

    if any(word in raw for word in BAD_ARTICLE_WORDS):
        return True

    return False


# -----------------------------
# Normalisation des termes
# -----------------------------

def normalize_term(term: Optional[str]) -> Optional[str]:
    if not term:
        return None

    t = term.lower().strip()
    t = re.sub(r"[^\wÀ-ÿ'\- ]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()

    # enlever articles fréquents
    t = re.sub(r"^(les|des|du|de la|de l|de|la|le|l|un|une)\s+", "", t)

    words = t.split()
    normalized_words = []

    for w in words:
        if w in IRREGULAR_NORMALIZATIONS:
            w = IRREGULAR_NORMALIZATIONS[w]
        elif len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        normalized_words.append(w)

    t = " ".join(normalized_words).strip()
    return t if t else None
    from typing import Optional

def normalize_text_for_markers(text: str) -> str:
    if not text:
        return ""

    return (
        text.lower()
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("“", '"')
        .replace("”", '"')
        .replace("«", '"')
        .replace("»", '"')
        .replace("\u00a0", " ")
    )
# -----------------------------
# Extraction sujet / prédicat
# -----------------------------

def extract_categorical_terms(sentence: str):
    s = sentence.lower().strip()
    s = re.sub(r"[^\wÀ-ÿ'\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # enlever les marqueurs conclusifs en tête de phrase
    s = re.sub(
        r"^(donc|ainsi|par conséquent|il s'ensuit que|il s’ensuit que|cela montre que|cela prouve que)\s+",
        "",
        s
    )

    patterns = [
        r"^(tous les|toutes les|tous|toutes|chaque)\s+(.+?)\s+sont\s+(.+)$",
        r"^(aucun|nul)\s+(.+?)\s+n[’']?est\s+(.+)$",
        r"^(aucun|nul)\s+(.+?)\s+ne\s+sont\s+pas\s+(.+)$",
        r"^(certains|quelques|plusieurs)\s+(.+?)\s+sont\s+(.+)$",
        r"^(certains|quelques|plusieurs)\s+(.+?)\s+ne\s+sont\s+pas\s+(.+)$",
    ]

    for pattern in patterns:
        m = re.match(pattern, s)
        if m:
            subject = normalize_term(m.group(2))
            predicate = normalize_term(m.group(3))
            return subject, predicate

    return None, None


# -----------------------------
# Détection proposition aristotélicienne
# -----------------------------

def detect_aristotelian_proposition(sentence: str) -> Optional[str]:
    s = sentence.lower().strip()

    # E : universelle négative
    if any(contains_term(s, w) for w in SYLLOGISTIC_MARKERS["E"]):
        return "E"

    # O : particulière négative
    if any(contains_term(s, w) for w in SYLLOGISTIC_MARKERS["O"]) and " pas " in f" {s} ":
        return "O"

    # I : particulière affirmative
    if any(contains_term(s, w) for w in SYLLOGISTIC_MARKERS["I"]):
        return "I"

    # A : universelle affirmative
    if any(contains_term(s, w) for w in SYLLOGISTIC_MARKERS["A"]) and " pas " not in f" {s} ":
        return "A"

    return None
# -----------------------------
# Détection syllogismes simples
# -----------------------------

def detect_syllogisms_from_claims(claims: List[Claim]) -> List[Dict]:
    syllogisms = []
    conclusion_markers = [
        "donc",
        "par conséquent",
        "ainsi",
        "il s'ensuit que",
        "il s’ensuit que",
        "cela montre que",
        "cela prouve que",
    ]

    for i in range(len(claims) - 2):
        c1 = claims[i]
        c2 = claims[i + 1]
        c3 = claims[i + 2]

        c3_lower = c3.text.lower().strip()

        has_conclusion_marker = any(
            contains_term(c3_lower, marker) or c3_lower.startswith(marker + " ")
            for marker in conclusion_markers
        )

        # On accepte aussi les triplets catégoriques même sans "donc"
        if not has_conclusion_marker:
            if not (c1.aristotelian_type and c2.aristotelian_type and c3.aristotelian_type):
                continue

        # Il faut au moins les deux prémisses bien extraites
        if not all([
            c1.subject_term, c1.predicate_term,
            c2.subject_term, c2.predicate_term
        ]):
            continue

        p1s = normalize_term(c1.subject_term)
        p1p = normalize_term(c1.predicate_term)
        p2s = normalize_term(c2.subject_term)
        p2p = normalize_term(c2.predicate_term)
        cs = normalize_term(c3.subject_term) if c3.subject_term else None
        cp = normalize_term(c3.predicate_term) if c3.predicate_term else None

        terms_p1 = {p1s, p1p}
        terms_p2 = {p2s, p2p}
        common_terms = {t for t in terms_p1.intersection(terms_p2) if t}

        if not common_terms:
            syllogisms.append({
                "premise_1": c1.text,
                "premise_2": c2.text,
                "conclusion": c3.text,
                "middle_term": None,
                "figure": None,
                "form": f"{c1.aristotelian_type or '-'}-{c2.aristotelian_type or '-'}-{c3.aristotelian_type or '-'}",
                "status": "no_middle_term_detected"
            })
            continue

        middle_term = sorted(common_terms, key=len, reverse=True)[0]

        figure = None
        if p1s == middle_term and p2p == middle_term:
            figure = "Figure 1 probable"
        elif p1p == middle_term and p2p == middle_term:
            figure = "Figure 2 probable"
        elif p1s == middle_term and p2s == middle_term:
            figure = "Figure 3 probable"
        elif p1p == middle_term and p2s == middle_term:
            figure = "Figure 4 probable"

        form = f"{c1.aristotelian_type or '-'}-{c2.aristotelian_type or '-'}-{c3.aristotelian_type or '-'}"

        status = "possible_syllogism"
        if form == "A-A-A" and figure == "Figure 1 probable":
            status = "valid_like_barbara"
        elif form == "E-A-E" and figure == "Figure 1 probable":
            status = "valid_like_celarent"
        elif form == "A-I-I" and figure == "Figure 1 probable":
            status = "valid_like_darii"
        elif form == "E-I-O" and figure == "Figure 1 probable":
            status = "valid_like_ferio"

        conclusion_terms = {cs, cp}
        premise_extremes = {t for t in {p1s, p1p, p2s, p2p} if t != middle_term}

        if not cs or not cp:
            status = "weak_conclusion_link"
        elif not conclusion_terms.intersection(premise_extremes):
            status = "weak_conclusion_link"

        syllogisms.append({
            "premise_1": c1.text,
            "premise_2": c2.text,
            "conclusion": c3.text,
            "middle_term": middle_term,
            "figure": figure,
            "form": form,
            "status": status,
            "p1_terms": {"subject": p1s, "predicate": p1p},
            "p2_terms": {"subject": p2s, "predicate": p2p},
            "c_terms": {"subject": cs, "predicate": cp},
        })

    return syllogisms

# -----------------------------
# Détection sophismes syllogistiques
# -----------------------------

def detect_syllogistic_fallacies(syllogisms: List[Dict]) -> List[Dict]:
    fallacies = []

    valid_statuses = {
        "valid_like_barbara",
        "valid_like_celarent",
        "valid_like_darii",
        "valid_like_ferio",
    }

    for s in syllogisms:
        form = s.get("form", "")
        figure = s.get("figure", "")
        status = s.get("status", "")

        # 1) Si le syllogisme est reconnu comme valide, aucun sophisme
        if status in valid_statuses:
            continue

        # 2) Aucun terme moyen partagé
        if status == "no_middle_term_detected":
            fallacies.append({
                "type": "missing_middle_term",
                "description": "Le raisonnement ne partage aucun terme moyen entre les prémisses.",
                "syllogism": s
            })
            continue

        # 3) Conclusion mal reliée aux extrêmes
        if status == "weak_conclusion_link":
            fallacies.append({
                "type": "weak_conclusion_link",
                "description": "La conclusion ne reprend pas correctement les extrêmes des prémisses.",
                "syllogism": s
            })
            continue

        # 4) Toute structure syllogistique non reconnue comme valide
        # doit, pour l’instant, être considérée comme sophistique ou invalide
        fallacies.append({
            "type": "invalid_or_unvalidated_form",
            "description": f"Forme syllogistique non validée : {form} / {figure if figure else 'figure indéterminée'}.",
            "syllogism": s
        })

    return fallacies

# -----------------------------
# Détection enthymèmes
# -----------------------------

def detect_enthymemes_from_claims(claims: List[Claim]) -> List[Dict]:
    enthymemes = []

    conclusion_markers = [
        "donc",
        "par conséquent",
        "ainsi",
        "il s'ensuit que",
        "il s’ensuit que",
        "cela montre que",
        "cela prouve que",
        
    # ajouts
        "il devient donc nécessaire",
        "il devient nécessaire",
        "il faut donc",
        "nous devons donc",
        "rester passif reviendrait",
    ]

    for i, c in enumerate(claims):
        text_lower = c.text.lower().strip()

        has_conclusion_marker = any(
            contains_term(text_lower, marker) or text_lower.startswith(marker + " ")
            for marker in conclusion_markers
        )

        if not has_conclusion_marker:
            continue

        context_before = claims[max(0, i - 2):i]

        if len(context_before) == 0:
            continue

        explicit_premises = sum(
            1 for x in context_before
            if x.aristotelian_type or x.subject_term or x.predicate_term
        )

        # Si deux prémisses explicites précèdent déjà la conclusion,
        # ce n’est probablement pas un enthymème
        if explicit_premises >= 2:
            continue

        weak_logical_shape = (
            c.aristotelian_type is not None
            or c.subject_term is not None
            or c.predicate_term is not None
            or " doit " in f" {text_lower} "
            or " doivent " in f" {text_lower} "
            or " est " in f" {text_lower} "
            or " sont " in f" {text_lower} "
        )

        if not weak_logical_shape:
            continue

        enthymemes.append({
            "conclusion": c.text,
            "form": c.aristotelian_type if c.aristotelian_type else "-",
            "subject": c.subject_term if c.subject_term else "-",
            "predicate": c.predicate_term if c.predicate_term else "-",
            "context": [x.text for x in context_before],
            "status": "possible_enthymeme",
        })

    return enthymemes

def classify_claim_type(sentence: str) -> List[str]:
    s = sentence.lower().strip()
    claim_types = []

    # normatif
    normative_terms = [
        "injuste", "immoral", "honteux", "scandaleux", "légitime",
        "illégitime", "dangereux", "toxique", "acceptable", "inacceptable",
        "raciste", "xénophobe", "fasciste", "complotiste"
    ]
    if any(contains_term(s, term) for term in normative_terms):
        claim_types.append("normative")

    # interprétatif
    interpretative_terms = [
        "révèle", "montre que", "signifie", "traduit", "témoigne de",
        "indique que", "laisse penser", "semble montrer", "suggère que"
    ]
    if any(contains_term(s, term) for term in interpretative_terms):
        claim_types.append("interpretative")

    # testimonial
    testimonial_patterns = [
        r"\bje\b", r"\bj'ai\b", r"\bmon quartier\b", r"\bchez moi\b",
        r"\bnous avons vu\b", r"\bj'ai vu\b", r"\bj'ai constaté\b"
    ]
    if any(re.search(p, s) for p in testimonial_patterns):
        claim_types.append("testimonial")

    # causal
    causal_terms = [
        "à cause de", "en raison de", "provoque", "entraîne",
        "explique", "cause", "responsable de", "conduit à"
    ]
    if any(contains_term(s, term) for term in causal_terms):
        claim_types.append("causal")

    # prédictif
    predictive_terms = [
        "va être", "vont être", "sera", "seront", "d'ici", "bientôt",
        "finira par", "dans les années à venir", "à l'avenir", "dans le futur"
    ]
    if any(contains_term(s, term) for term in predictive_terms):
        claim_types.append("predictive")

    # généralisant
    generalizing_terms = [
        "toujours",
        "jamais",
        "tout le monde",
        "personne",
        "aucun",
        "tous les",
        "toutes les"
    ]
    if any(contains_term(s, term) for term in generalizing_terms):
        claim_types.append("generalizing")

    # factuel quantifié
    if re.search(r"\d+(?:[.,]\d+)?%?", s):
        claim_types.append("quantitative")

    # si rien
    if not claim_types:
        claim_types.append("factual_or_undetermined")

    return unique_keep_order(claim_types)

def compute_sentence_red_flags(sentence: str) -> List[str]:
    s = sentence.lower()
    flags = []

    if any(contains_term(s, t) for t in ["toujours", "jamais", "tout le monde", "aucun"]):
        flags.append("generalization")

    if any(contains_term(s, t) for t in ["cela prouve que", "cela montre que", "à cause de", "donc forcément"]):
        flags.append("false_causality")

    if any(contains_term(s, t) for t in ["il est évident que", "sans aucun doute", "il est certain que"]):
        flags.append("absolute_certainty")

    if any(contains_term(s, t) for t in ["on nous cache", "ils veulent", "complot", "plan caché"]):
        flags.append("hidden_intent")

    if any(contains_term(s, t) for t in ["invasion", "submersion", "trahison", "ennemi du peuple"]):
        flags.append("propaganda")

    return unique_keep_order(flags)

def small_claim_epistemic_adjustment(sentence: str, claim_types: List[str], sentence_red_flags: List[str], absolutism: int) -> tuple[float, str]:
    words = len(sentence.split())

    severe_flags = {
        "generalization",
        "false_causality",
        "absolute_certainty",
        "hidden_intent",
        "propaganda",
    }

    if words > 18:
        return 0.0, ""

    if any(flag in severe_flags for flag in sentence_red_flags):
        return 0.0, ""

    if absolutism >= 2:
        return 0.0, ""

    if "normative" in claim_types:
        return 2.0, "Jugement normatif : ne doit pas être pénalisé comme un fait brut."
    if "interpretative" in claim_types:
        return 1.5, "Affirmation interprétative : demande contexte et pluralité de lectures."
    if "testimonial" in claim_types:
        return 1.2, "Affirmation testimoniale : valeur vécue reconnue, sans portée générale automatique."

    return 0.0, ""

def detect_syllogisms(sentences: List[str]) -> List[Dict]:
    syllogisms = []

    conclusion_markers = [
        "donc",
        "par conséquent",
        "ainsi",
        "il s'ensuit que",
        "cela montre que",
        "cela prouve que"
    ]

    for i, s in enumerate(sentences):
        s_lower = s.lower()

        if any(contains_term(s_lower, marker) for marker in conclusion_markers):
            context = sentences[max(0, i - 2): i + 1]

            syllogisms.append({
                "type": "inference_possible",
                "conclusion": s,
                "context": context
            })

    return syllogisms

def compute_factual_sobriety_bonus(sentence: str, claim_types: List[str], risk: float, red_flags: List[str]):
    words = len(sentence.split())

    toxic_flags = {
        "generalization",
        "false_causality",
        "absolute_certainty",
        "hidden_intent",
        "propaganda",
    }

    if words > 22:
        return 0.0, ""

    if any(flag in toxic_flags for flag in red_flags):
        return 0.0, ""

    if risk >= 7:
        return 0.0, ""

    if "quantitative" in claim_types or "factual_or_undetermined" in claim_types:
        return 1.8, "Affirmation courte et sobre : peu de signaux rhétoriques ou manipulatoires."

    return 0.0, ""

# -----------------------------
# Cohérence discursive / nouveaux modules
# -----------------------------
LOGICAL_CONNECTORS = [
    "car", "donc", "ainsi", "puisque", "parce que",
    "cependant", "pourtant", "toutefois", "néanmoins",
    "en effet", "or", "alors", "mais",
    "de plus", "en outre", "par conséquent", "dès lors"
]

DISCURSIVE_CONTRADICTION_PATTERNS = [
    r"\btoujours\b.{0,120}\bjamais\b",
    r"\bjamais\b.{0,120}\btoujours\b",
    r"\btout\b.{0,120}\bsauf\b",
    r"\brien\b.{0,120}\bmais\b",
    r"\baucun\b.{0,120}\bmais\b",
    r"\bobligatoire\b.{0,120}\bfacultatif\b",
    r"\bimpossible\b.{0,120}\bpossible\b"
]
STOPWORDS_FR_EXTENDED = {
    "le", "la", "les", "un", "une", "des", "du", "de", "d", "et", "ou",
    "à", "au", "aux", "en", "dans", "sur", "pour", "par", "avec", "sans",
    "ce", "cet", "cette", "ces", "qui", "que", "quoi", "dont", "où",
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles",
    "est", "sont", "était", "être", "a", "ont", "avait", "avoir",
    "ne", "pas", "plus", "se", "sa", "son", "ses", "leur", "leurs",
    "comme", "dans", "sur", "sous", "entre", "vers", "chez", "après",
    "avant", "aussi", "encore", "très", "moins", "tout", "tous",
    "toute", "toutes", "cela", "celui", "celle", "ceux", "celles",
    "ainsi", "alors", "donc", "mais", "or"
}
IMPLICIT_PREMISE_MARKERS = {
    "generalisation": [
        "toujours", "jamais", "tout le monde", "personne", "tous", "aucun",
        "inévitablement", "nécessairement", "everyone knows", "nobody can deny"
    ],
    "naturalisation": [
        "il est évident que", "il est clair que", "de toute évidence",
        "on sait que", "l'histoire montre que", "la réalité est simple",
        "it is clear that", "it is obvious that", "history shows that"
    ],
    "autorite_vague": [
        "les experts", "les spécialistes", "les chercheurs",
        "selon des experts", "selon certains spécialistes",
        "des études montrent", "le consensus scientifique",
        "experts say", "studies show", "scientific consensus"
    ],
    "conclusion_forcee": [
        "donc", "ainsi", "par conséquent", "dès lors",
        "cela prouve que", "cela montre que", "ce qui démontre que",
        "therefore", "this proves that", "this shows that"
    ],
    "injonction_conditionnelle": [
        "si rien n'est fait",
        "si rien n’est fait",
        "si nous ne faisons rien",
        "si personne n'agit",
        "si aucune mesure n'est prise",
        "si rien ne change",
        "il faut agir",
        "il faut réagir",
        "il faut intervenir",
        "nous devons agir",
        "nous devons réagir",
        "agir immédiatement",
        "réagir immédiatement"
    ]
}
LOGIC_CONFUSION_MARKERS = {
    "causalite_abusive": [
        "cela prouve que", "cela montre que", "c'est pourquoi",
        "ce qui explique que", "ce qui démontre que", "donc la cause",
        "this proves that", "this shows that", "that is why"
    ],
    "extrapolation": [
        "donc tous", "donc toujours", "donc jamais",
        "par conséquent tout", "il faut en conclure que",
        "therefore all", "therefore always", "necessarily all"
    ],
    "prediction_absolue": [
        "inévitablement", "forcément", "il est certain que",
        "il est impossible que", "finira par", "conduira nécessairement à",
        "inevitably", "certainly", "it is impossible that"
    ]
}
SCIENTIFIC_SIMULATION_MARKERS = {
    "references_vagues": [
        "des études montrent", "la science prouve", "les chercheurs disent",
        "les scientifiques ont démontré", "plusieurs recherches montrent",
        "according to studies", "science proves", "research shows",
    ],

    "technicite_rhetorique": [
        "système", "structure", "dynamique", "modèle",
        "mécanisme", "processus", "paradigme",
        "system", "structure", "dynamics", "model", "mechanism", "process",
    ],

    "chiffres_sans_source": [
        "pour cent",
        "une étude récente",
        "plusieurs recherches",
        "des statistiques montrent",
        "recent study",
        "statistics show",
    ]
}

SCIENTIFIC_SIMULATION_MARKERS["technicite_rhetorique"] += [
    "cycle de vie",
    "empreinte carbone",
    "kilowattheure",
    "neutralité carbone",
    "stockage à long terme",
    "recyclage partiel",
    "combustibles usés",
    "circuit fermé",
    "rejets thermiques",
    "biodiversité",
    "artificialisation des sols",
    "production stable",
    "production prévisible",
]

def tokenize_words(text: str):
    return re.findall(r"\b[\wÀ-ÿ'-]+\b", text.lower())

def split_paragraphs(text: str):
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts and text.strip():
        parts = [text.strip()]
    return parts

def extract_content_words(words):
    return [w for w in words if w not in STOPWORDS_FR_EXTENDED and len(w) > 3]

def top_keywords_from_text(text: str, n: int = 8):
    words = tokenize_words(text)
    content_words = extract_content_words(words)
    freq = Counter(content_words)
    return [w for w, _ in freq.most_common(n)]

def interpret_discursive_coherence(score: float) -> str:
    if score < 5:
        return "Cohérence discursive faible"
    elif score < 9:
        return "Cohérence discursive limitée"
    elif score < 13:
        return "Cohérence discursive correcte"
    elif score < 17:
        return "Cohérence discursive solide"
    return "Cohérence discursive très forte"

def paragraph_overlap_score(paragraphs):
    if len(paragraphs) < 2:
        return 2.0

    overlaps = []
    para_keywords = [set(top_keywords_from_text(p, 8)) for p in paragraphs]

    for i in range(len(para_keywords) - 1):
        a = para_keywords[i]
        b = para_keywords[i + 1]
        if not a or not b:
            overlaps.append(0)
            continue

        inter = len(a.intersection(b))
        union = len(a.union(b))
        overlaps.append(inter / union if union else 0)

    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0

    if avg_overlap >= 0.35:
        return 4.0
    elif avg_overlap >= 0.20:
        return 3.0
    elif avg_overlap >= 0.10:
        return 2.0
    elif avg_overlap > 0:
        return 1.0
    return 0.0

def topic_shift_penalty(paragraphs):
    if len(paragraphs) < 2:
        return 0.0

    penalties = 0.0
    para_keywords = [set(top_keywords_from_text(p, 8)) for p in paragraphs]

    for i in range(len(para_keywords) - 1):
        a = para_keywords[i]
        b = para_keywords[i + 1]

        if not a or not b:
            penalties += 1.0
            continue

        common = len(a.intersection(b))
        if common == 0:
            penalties += 1.5
        elif common == 1:
            penalties += 0.5

    return min(penalties, 4.0)

def compute_discursive_coherence(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "label": "Cohérence discursive faible",
            "logic_score": 0.0,
            "stability_score": 0.0,
            "length_score": 0.0,
            "paragraph_score": 0.0,
            "contradiction_penalty": 0.0,
            "topic_shift_penalty": 0.0,
            "top_keywords": []
        }

    text_lower = text.lower().strip()
    words = tokenize_words(text_lower)
    word_count = len(words)
    paragraphs = split_paragraphs(text)

    logic_hits = sum(1 for connector in LOGICAL_CONNECTORS if contains_term(text_lower, connector))
    logic_score = min(logic_hits * 1.2, 5.0)

    content_words = extract_content_words(words)
    freq = Counter(content_words)
    top_keywords = freq.most_common(6)
    repeated_keywords = sum(1 for _, count in top_keywords if count >= 2)
    stability_score = min(repeated_keywords * 1.2, 4.0)

    if word_count < 40:
        length_score = 0.8
    elif word_count < 80:
        length_score = 2.0
    elif word_count < 140:
        length_score = 3.0
    elif word_count < 220:
        length_score = 4.0
    else:
        length_score = 5.0

    paragraph_score = paragraph_overlap_score(paragraphs)

    contradiction_hits = 0
    for pattern in DISCURSIVE_CONTRADICTION_PATTERNS:
        if re.search(pattern, text_lower, flags=re.DOTALL):
            contradiction_hits += 1
    contradiction_penalty = min(contradiction_hits * 2.0, 4.0)

    shift_penalty = topic_shift_penalty(paragraphs)

    raw_score = logic_score + stability_score + length_score + paragraph_score - contradiction_penalty - shift_penalty

    # -----------------------------
    # Correction : cohérence structurelle vs orientation
    # -----------------------------
    sentence_count = max(len([s for s in re.split(r"[.!?]+", text) if s.strip()]), 1)
    
    if sentence_count > 3:
        raw_score += 1.5
    
    if logic_hits > 1:
        raw_score += 1.0
    
    if sentence_count > 3:
        raw_score = max(raw_score, 7.5)

    if contradiction_hits > 1:
        raw_score -= 1.5
    
    score = clamp(raw_score, 0.0, 20.0)

    return {
        "score": round(score, 1),
        "label": interpret_discursive_coherence(score),
        "logic_score": round(logic_score, 1),
        "stability_score": round(stability_score, 1),
        "length_score": round(length_score, 1),
        "paragraph_score": round(paragraph_score, 1),
        "contradiction_penalty": round(contradiction_penalty, 1),
        "topic_shift_penalty": round(shift_penalty, 1),
        "top_keywords": top_keywords,
    }

def compute_implicit_premises(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "details": {},
            "markers": [],
            "interpretation": "Aucune prémisse implicite détectée."
        }

    t = normalize_text_for_markers(text)

    score = 0
    details = {}
    markers = []

    for category, terms in IMPLICIT_PREMISE_MARKERS.items():
        hits = [
            term for term in terms
            if contains_term(t, term)
        ]

        details[category] = len(hits)
        markers.extend(hits)

        if category == "injonction_conditionnelle":
            score += len(hits) * 3
        else:
            score += len(hits)

    score = min(score * 2, 20)
    ratio = score / 20

    if ratio < 0.20:
        interpretation = "Peu de prémisses implicites détectées."
    elif ratio < 0.40:
        interpretation = "Le texte contient quelques prémisses implicites."
    elif ratio < 0.70:
        interpretation = "Le texte repose partiellement sur des prémisses présentées comme évidentes."
    else:
        interpretation = "Le texte repose fortement sur des prémisses implicites non démontrées."

    return {
        "score": round(ratio, 3),
        "details": details,
        "markers": unique_keep_order(markers),
        "interpretation": interpretation,
    }

def compute_logic_confusion(text: str):
    if not text or not text.strip():
        return {"score": 0.0, "details": {}, "markers": [], "interpretation": "Aucune confusion logique saillante détectée."}

    t = text.lower()
    score = 0
    details = {}
    markers = []

    for category, terms in LOGIC_CONFUSION_MARKERS.items():
        hits = [term for term in terms if contains_term(t, term)]
        details[category] = len(hits)
        markers.extend(hits)
        score += len(hits)

    score = min(score * 2, 20)
    ratio = score / 20

    if ratio < 0.20:
        interpretation = "Peu de confusions logiques détectées."
    elif ratio < 0.40:
        interpretation = "Le texte présente quelques simplifications logiques."
    elif ratio < 0.70:
        interpretation = "Le texte présente plusieurs confusions logiques notables."
    else:
        interpretation = "Le texte repose fortement sur des inférences fragiles ou abusives."

    return {
        "score": round(ratio, 3),
        "details": details,
        "markers": unique_keep_order(markers),
        "interpretation": interpretation,
    }

def compute_scientific_simulation(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "details": {},
            "markers": [],
            "interpretation": "Aucune simulation scientifique saillante détectée."
        }

    t = text.lower()
    score = 0
    details = {}
    markers = []

    for category, terms in SCIENTIFIC_SIMULATION_MARKERS.items():
        hits = [term for term in terms if contains_term(t, term) or term in t]
        details[category] = len(hits)
        markers.extend(hits)
        score += len(hits)

    percent_matches = re.findall(r"\b\d+(?:[.,]\d+)?\s*%", text)
    if percent_matches:
        details["pourcentages"] = len(percent_matches)
        markers.extend([f"pourcentage sans source explicite : {p}" for p in percent_matches[:5]])
        score += min(len(percent_matches), 3)
    else:
        details["pourcentages"] = 0

    score = min(score * 2, 20)
    ratio = score / 20

    if ratio < 0.20:
        interpretation = "Peu de marqueurs de scientificité rhétorique détectés."
    elif ratio < 0.40:
        interpretation = "Le texte mobilise quelques codes d’objectivité scientifique."
    elif ratio < 0.70:
        interpretation = "Le texte utilise nettement une scientificité rhétorique."
    else:
        interpretation = "Le texte simule fortement l’objectivité scientifique sans support identifiable."

    return {
        "score": round(ratio, 3),
        "details": details,
        "markers": unique_keep_order(markers),
        "interpretation": interpretation,
    }

def detect_short_form_mode(text: str):
    words = tokenize_words(text)
    word_count = len(words)

    if word_count < 25:
        return {
            "is_short_form": True,
            "word_count": word_count,
            "label": "Mode aphorisme / texte court",
            "interpretation": "Texte très court : les métriques factuelles et discursives doivent être lues avec prudence."
        }

    return {
        "is_short_form": False,
        "word_count": word_count,
        "label": "Texte standard",
        "interpretation": "Longueur suffisante pour une lecture discursive plus stable."
    }
# -----------------------------
# Nouvelles bibliothèques rhétoriques
# -----------------------------
CAUSAL_OVERREACH_TERMS = [
    "donc",
    "par conséquent",
    "ce qui prouve que",
    "cela montre que",
    "la preuve que",
    "c'est pour cela que",
    "donc forcément",
    "depuis que",
    "suite à",
    "à cause de",
    "en raison de",
    "cela explique",
    "ce qui explique que",
    "ce qui entraîne",
    "ce qui conduit à",
    "ce qui provoque",
]

VAGUE_AUTHORITY_TERMS = [
    "selon des experts",
    "selon des spécialistes",
    "des scientifiques disent",
    "des experts affirment",
    "des études montrent",
    "plusieurs études",
    "selon une étude récente",
    "selon certaines études",
    "selon plusieurs études",
    "selon des chercheurs",
    "selon certains chercheurs",
    "selon plusieurs chercheurs",
    "plusieurs chercheurs",
    "plusieurs experts",
    "certains experts",
    "de nombreux experts",
    "de nombreux spécialistes",
    "plusieurs analystes",
    "des rapports suggèrent",
    "les données montrent",
    "les données indiquent",
    "le consensus scientifique",
    "les experts disent", 
    "des sources affirment", 
    "selon des sources",
    "des spécialistes", 
    "des rapports confirment", 
    "sources internes"
]

VAGUE_AUTHORITY_TERMS += [
    "les études montrent",
    "les scénarios de transition énergétique montrent",
    "les scénarios établis par",
    "l'agence internationale de l'énergie",
    "l’agence internationale de l’énergie",
    "réseau de transport d'électricité",
    "réseau de transport d’électricité",
]

# -----------------------------
# Généralisation abusive
# -----------------------------
GENERALIZATION_TERMS = [
    "les médias",
    "les politiciens",
    "les scientifiques",
    "les experts",
    "les immigrés",
    "les élites",
    "les journalistes",
    "les gouvernements",
    "ils veulent",
    "ils disent",
    "ils savent",
    "tout le monde sait",
    "tout le monde voit"
]
# =========================================================
# MODULES DISCURSIFS COMPLÉMENTAIRES
# =========================================================

VICTIMIZATION_TERMS = [
    "on veut nous faire taire",
    "nous sommes censurés",
    "on nous empêche de parler",
    "ils veulent nous réduire au silence",
    "nous sommes persécutés",
]

POLARIZATION_TERMS = [
    "les bons contre les mauvais",
    "le bien contre le mal",
    "les patriotes contre les traîtres",
    "les honnêtes gens contre les corrompus",
]

SIMPLIFICATION_TERMS = [
    "la seule raison",
    "la seule cause",
    "tout vient de",
    "il suffit de",
    "tout s'explique par",
]

FRAME_SHIFT_TERMS = [
    "la vraie question",
    "le vrai problème",
    "ce n'est pas la question",
    "la question n'est pas là",
]

FRAME_SHIFT_TERMS += [
    "souveraineté énergétique",
    "sécurité économique",
    "indépendance nationale",
    "au-delà de l'électricité",
    "idées reçues",
    "réalités factuelles",
]

ATTACK_TERMS = [
    "mensonge",
    "manipulation",
    "propagande",
    "corrompu",
    "absurde",
    "ridicule",
]

ARGUMENT_TERMS = [
    "car",
    "donc",
    "ainsi",
    "puisque",
    "en effet",
    "par conséquent",
]

# -----------------------------
# Ennemi abstrait
# -----------------------------
ABSTRACT_ENEMY_TERMS = [
    "le système",
    "les élites",
    "l'oligarchie",
    "les puissants",
    "les globalistes",
    "les forces en place",
    "l'establishment",
    "les intérêts financiers",
    "les dirigeants"
]

# -----------------------------
# Certitude absolue
# -----------------------------
CERTAINTY_TERMS = [
    "il est évident que",
    "il est clair que",
    "c'est indiscutable",
    "sans aucun doute",
    "la vérité est que",
    "il est certain que",
    "personne ne peut nier",
    "il est incontestable",
    "la preuve que",

    # ajouts utiles
    "il est absolument certain",
    "absolument certain",
    "aucun doute",
    "c'est certain",
    "c'est évident",
    "évident",
    "évidemment",
    "indiscutable",
    "incontestable",
    "indéniable",
    "de toute évidence",
    "cela prouve que",
    "preuve irréfutable",
    "il ne fait aucun doute",
    "nous allons vers",
    "inévitablement",
    "inévitable",
]

EMOTIONAL_DICT = {
    # émotion directe
    "choc": 0.55,
    "incroyable": 0.35,
    "terrible": 0.55,
    "peur": 0.60,
    "panique": 0.75,
    "honte": 0.55,
    "scandale": 0.65,
    "trahison": 0.65,

    # menace / crise
    "menace": 0.55,
    "danger": 0.55,
    "crise": 0.50,
    "urgent": 0.60,
    "urgence": 0.60,
    "catastrophe": 0.80,
    "désastre": 0.75,
    "effondrement": 0.80,
    "destruction": 0.75,

    # émotion géopolitique froide
    "mortelle": 0.70,
    "mourir": 0.70,
    "survie": 0.75,
    "guerre": 0.65,
    "paix": 0.35,
    "encerclement": 0.70,
    "tournant": 0.45,
    "réveil brutal": 0.75,
    "brutal": 0.55,

    # mobilisation collective
    "bataille": 0.60,
    "destin": 0.45,
    "maîtres de notre destin": 0.65,
    "valeurs": 0.35,
    "disparaître": 0.70,
    "disparaîtra": 0.70,
}

# -----------------------------
# Ajouts émotionnels
# -----------------------------
EMOTIONAL_DICT.update({
    "indispensable": 0.35,
    "souveraineté": 0.40,
    "sécurité": 0.35,
    "indépendance nationale": 0.45,
    "solution concrète": 0.35,
    "énergie du passé": 0.35,
})

# -----------------------------
# Faux consensus
# -----------------------------
CONSENSUS_TERMS = [
    "tout le monde sait",
    "tout le monde comprend",
    "il est clair pour tous",
    "personne ne doute",
    "personne ne peut nier",
    "chacun sait",
    "il est évident pour tous",
    "les experts s'accordent",
    "tout le monde voit bien",
]
CONSENSUS_TERMS += [
    "tout le monde voit désormais",
    "tout le monde voit",
    "chacun peut constater",
    "tout le monde peut constater",
    "il suffit d'ouvrir les yeux",
    "tout le monde sait désormais",
    "ceux qui disent la vérité",
    "ceux qui ouvrent les yeux",
    "personne ne mentionne",
]
# -----------------------------
# Opposition binaire
# -----------------------------
BINARY_OPPOSITION_TERMS = [
    "eux contre nous",
    "nous contre eux",
    "le peuple contre",
    "les élites contre",
    "les honnêtes contre",
    "les patriotes contre",
    "les traîtres",
    "les ennemis du peuple",
    "ceux qui sont avec nous",
    "ceux qui sont contre nous",

    # ajouts utiles
    "d'un côté",
    "d’un côté",
    "de l'autre",
    "de l’autre",
    "d'un côté ceux",
    "d’un côté ceux",
    "de l'autre ceux",
    "de l’autre ceux",
    "il n'y a pas de position intermédiaire",
    "pas de position intermédiaire",
    "refuser de choisir",
    "c'est déjà choisir",
    "c’est déjà choisir",
    "ceux qui ouvrent les yeux",
    "ceux qui refusent de voir",
    "ceux qui veulent préserver",
    "ceux qui participent",

    # cas comparatifs / oppositions thématiques
    "gaz à effet de serre ou déchets nucléaires",
    "dérèglement du climat ou danger nucléaire",
    "plutôt que les énergies fossiles",
    "proposer l'énergie nucléaire plutôt que",
    "proposer l’énergie nucléaire plutôt que",
    "remplacer un problème par un autre",
    "alors que les énergies renouvelables",
]

BINARY_OPPOSITION_STRONG_TERMS = [
    "eux contre nous",
    "nous contre eux",
    "le peuple contre",
    "les élites contre",
    "les patriotes contre",
    "les traîtres",
    "les ennemis du peuple",
    "gaz à effet de serre ou déchets nucléaires",
    "dérèglement du climat ou danger nucléaire",
    "remplacer un problème par un autre",
]

BINARY_OPPOSITION_WEAK_TERMS = [
    "plutôt que les énergies fossiles",
    "proposer l'énergie nucléaire plutôt que",
    "proposer l’énergie nucléaire plutôt que",
    "alors que les énergies renouvelables",
]
# -----------------------------
# Qualifications normatives
# -----------------------------
QUALIFICATIONS_NORMATIVES = [
    "raciste", "racisme", "xénophobe", "xénophobie",
    "fasciste", "fascisme", "nazi", "nazisme",
    "extrémiste", "extrémisme", "complotiste", "complotisme",
    "conspirationniste", "révisionniste", "populiste", "démagogue",
    "islamophobe", "antisémite", "homophobe", "transphobe",
    "misogyne", "sexiste", "suprémaciste", "identitaire",
    "radical", "fanatique", "toxique", "dangereux", "haineux",
    "criminel", "immoral", "pseudo-scientifique", "charlatan",
    "fake news", "infox", "désinformation", "propagande",
    "endoctrinement", "délire", "paranoïa", "hystérique",
]

JUDGMENT_MARKERS = [
    "clairement", "évidemment", "manifestement",
    "incontestablement", "indéniablement",
    "sans conteste", "sans aucun doute",
    "de toute évidence", "il est évident que",
    "notoirement", "tristement célèbre",
    "bien connu pour", "réputé pour",
    "qualifié de", "considéré comme",
    "assimilé à", "associé à", "accusé de",
]

NARRATIVE_PRESSURE_MARKERS = [
    "il est évident", "il est certain", "sans aucun doute",
    "il ne fait aucun doute", "il faut agir", "immédiatement",
    "avant qu'il ne soit trop tard", "crise majeure",
    "catastrophe", "effondrement", "menace", "danger",
    "la seule solution", "la seule conclusion", "nous allons vers"
]

CONCLUSION_MARKERS = [
    "donc", "ainsi", "par conséquent", "cela prouve",
    "la conclusion est", "il s'ensuit", "c'est pourquoi"
]

REASON_MARKERS = [
    "car", "parce que", "puisque", "en raison de",
    "étant donné", "du fait que", "cela s'explique"
]

NUANCE_MARKERS = [
    "cependant", "toutefois", "néanmoins", "pourtant",
    "en revanche", "il faut nuancer", "cela dépend",
    "dans certains cas", "certains estiment", "d'autres pensent"
]

ASSERTION_MARKERS = [
    "est", "sont", "doit", "doivent", "va", "vont",
    "toujours", "jamais", "aucun", "tous", "personne"
]
# -----------------------------
# Ajouts nucléaire / discours écologico-technocratique
# -----------------------------

QUALIFICATIONS_NORMATIVES += [
  
    "véritable fléau",
    "excessivement dangereux",
    "excessivement dangereuse",
    "plus sûres",
    "pas propre",
    "remplacer la peste par le choléra",
]

EMOTIONAL_DICT.update({
    "fléau": 0.65,
    "véritable fléau": 0.75,
    "peste": 0.70,
    "choléra": 0.70,
    "danger nucléaire": 0.65,
    "excessivement dangereuse": 0.65,
    "fatidique": 0.45,
    "malin plaisir": 0.55,
    "chiffon rouge": 0.50,
})

ATTACK_TERMS += [
    "petite musique",
    "orchestrée",
    "orchestré",
    "promoteurs",
    "promoteurs de l'industrie nucléaire",
    "promoteurs de l’industrie nucléaire",
    "prennent un malin plaisir",
    "agitent le chiffon rouge",
    "chiffon rouge",
]

FRAME_SHIFT_TERMS += [
    "ce n'est pas pour autant",
    "ce n’est pas pour autant",
    "en réalité",
    "et ce n'est pas tout",
    "et ce n’est pas tout",
    "le problème ?",
]

BINARY_OPPOSITION_TERMS += [
    "gaz à effet de serre ou déchets nucléaires",
    "dérèglement du climat ou danger nucléaire",
    "plutôt que les énergies fossiles",
    "proposer l'énergie nucléaire plutôt que",
    "proposer l’énergie nucléaire plutôt que",
    "remplacer un problème par un autre",
    "alors que les énergies renouvelables",
]

NARRATIVE_PRESSURE_MARKERS += [
    "véritable fléau",
    "quantités démesurées",
    "plusieurs milliers d'années",
    "générations futures",
    "peste par le choléra",
    "remplacer la peste par le choléra",
    "prennent un malin plaisir",
    "agitent le chiffon rouge",
]


def detect_normative_charges(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "normative_terms": [],
            "judgment_markers": [],
            "interpretation": "Aucune qualification normative détectée."
        }

    t = text.lower()

    normative_hits = unique_keep_order(
        [term for term in QUALIFICATIONS_NORMATIVES if contains_term(t, term)]
    )
    marker_hits = unique_keep_order(
        [term for term in JUDGMENT_MARKERS if contains_term(t, term)]
    )

    raw_score = len(normative_hits) * 1.5 + len(marker_hits) * 0.8
    score = min(raw_score / 10, 1.0)

    if score < 0.15:
        interpretation = "Le texte reste principalement descriptif."
    elif score < 0.35:
        interpretation = "Quelques qualifications normatives sont détectées."
    elif score < 0.55:
        interpretation = "Le texte mélange faits et jugements de valeur."
    elif score < 0.75:
        interpretation = "Le texte présente plusieurs jugements comme des évidences."
    else:
        interpretation = "Le texte est saturé de qualifications normatives présentées comme des faits."

    return {
        "score": round(score, 3),
        "normative_terms": normative_hits,
        "judgment_markers": marker_hits,
        "interpretation": interpretation,
    }
# -----------------------------
# Glissement sémantique
# -----------------------------
SEMANTIC_SHIFT_MARKERS = [
    "invasion",
    "submersion",
    "effondrement",
    "dictature sanitaire",
    "tyrannie",
    "système corrompu",
    "oligarchie",
    "propagande officielle",
    "mensonge d'état",

    # ajouts
    "vérité interdite",
    "vérités interdites",
    "débat n'est plus libre",
    "débat n’est plus libre",
    "présenté comme normal",
    "évolution normale",
    "en réalité",
    "transformation profonde",
    "inversion des valeurs",
    "ce qui est présenté comme",
    "ce qui est moralement juste",
    "le bien est devenu suspect",
    "le mal est toléré",
    "destruction",
    "dérive",
    "ordre juste",
]
SEMANTIC_SHIFT_MARKERS += [
    "submersion organisée",
    "médias officiels",
    "nier l'évidence",
    "nier l’évidence",
    "autorités cherchent à cacher",
    "stratégie globale",
    "rester dans le déni",
    "choix simple",
    "effondrement progressif",
    "présentée comme un progrès inévitable",
    "présenté comme de la tolérance",
    "dissolution collective",
    "malaise identitaire",
    "transformation culturelle radicale",
    "manipulation collective",
    "extrémiste",
    "ennemis du système",
    "ceux qui disent la vérité",
    "ceux qui ouvrent les yeux",
]


def detect_semantic_shift(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucun glissement sémantique détecté."
        }

    t = normalize_text_for_markers(text)

    markers = []

    # -----------------------------
    # 1) Marqueurs lexicaux directs
    # -----------------------------
    for w in SEMANTIC_SHIFT_MARKERS:
        if contains_term(t, w) or w in t:
            markers.append(w)

    # -----------------------------
    # 2) Structures de recadrage (clé)
    # -----------------------------
    STRUCTURES = [
        "ce qui est présenté comme",
        "en réalité",
        "en fait",
        "en vérité",
        "ce qu'on appelle",
        "ce que l'on appelle",
        "soi-disant",
        "prétendument",
    ]

    for s in STRUCTURES:
        if s in t:
            markers.append(s)

    # -----------------------------
    # 3) Opposition sémantique (ex : normal → dérive)
    # -----------------------------
    if ("normal" in t or "naturel" in t) and (
        "dérive" in t or "destruction" in t or "effondrement" in t
    ):
        markers.append("renversement sémantique")

    # -----------------------------
    # 4) Recadrage global du problème
    # -----------------------------
    if (
        ("crise" in t or "évolution" in t or "situation" in t)
        and ("submersion" in t or "stratégie globale" in t or "effondrement" in t)
    ):
        markers.append("recadrage du problème en menace globale")

        # Requalification d’un terme positif en menace
    if (
        ("tolérance" in t or "diversité" in t or "ouverture" in t or "progrès" in t)
        and (
            "masquer" in t
            or "dissolution" in t
            or "destruction" in t
            or "effondrement" in t
            or "menace" in t
        )
    ):
        markers.append("requalification d’un terme positif en menace")

    # Structure : X n’est pas Y mais Z
    if (
        ("n'est pas" in t or "n’est pas" in t)
        and ("mais" in t or "en réalité" in t)
    ):
        markers.append("renversement interprétatif")

    # -----------------------------
    # 4) Nettoyage
    # -----------------------------
    markers = unique_keep_order(markers)

    # -----------------------------
    # 5) Score
    # -----------------------------
    score = clamp(len(markers) * 1.2, 0, 20)
    ratio = score / 20

    # -----------------------------
    # 6) Interprétation
    # -----------------------------
    if ratio < 0.20:
        interpretation = "Peu de glissements sémantiques détectés."
    elif ratio < 0.40:
        interpretation = "Quelques recadrages lexicaux sont présents."
    elif ratio < 0.70:
        interpretation = "Le texte opère plusieurs glissements sémantiques notables."
    else:
        interpretation = "Le discours recadre fortement le réel par un lexique orienté."

    return {
        "score": round(ratio, 3),
        "markers": markers,
        "interpretation": interpretation
    }


# -----------------------------
# Prémisses idéologiques implicites
# -----------------------------
IDEOLOGICAL_PREMISE_MARKERS = [
    "il est évident que",
    "il est clair que",
    "il est bien connu que",
    "il est largement admis",
    "il est généralement admis",
    "largement considéré comme",
    "considéré comme",
    "la plupart des experts",
    "les experts s'accordent",
    "le consensus scientifique",
    "selon les spécialistes",
    "il ne fait aucun doute que",
    "de toute évidence",
    "it is widely accepted",
    "it is widely believed",
    "experts agree",
    "scientific consensus",
    "it is clear that",
]
IDEOLOGICAL_FRAMING_PATTERNS = [
    "ceux qui disent la vérité",
    "les honnêtes citoyens",
    "les élites corrompues",
    "le système",
    "les médias participent",
    "les autorités ont menti",
    "ceux qui ouvrent les yeux",
    "ennemis du système",
    "notre disparition",
    "on nous cache",
    "vérité censurée",
]

def detect_ideological_premises(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune prémisse implicite détectée."
        }

    t = text.lower()

    base_hits = [
        m for m in IDEOLOGICAL_PREMISE_MARKERS
        if contains_term(t, m)
    ]
    
    framing_hits = [
        m for m in IDEOLOGICAL_FRAMING_PATTERNS
        if contains_term(t, m)
    ]
    
    hits = unique_keep_order(base_hits + framing_hits)

    score = min(len(hits) / 6, 1.0)

    if score < 0.2:
        interpretation = "Peu de prémisses implicites détectées."
    elif score < 0.4:
        interpretation = "Le texte contient quelques prémisses implicites."
    elif score < 0.7:
        interpretation = "Le texte repose partiellement sur des prémisses présentées comme évidentes."
    else:
        interpretation = "Le texte repose fortement sur des prémisses idéologiques implicites."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }


# -----------------------------
# Propagande narrative
# -----------------------------
PROPAGANDA_ENEMY_MARKERS = [
    "ennemi du peuple", "traîtres", "traître",
    "élite corrompue", "système corrompu",
    "complot mondial", "deep state", "globalistes",
    "invasion", "submersion", "remplacement",
]

PROPAGANDA_URGENCY_MARKERS = [
    "urgence absolue", "il est presque trop tard",
    "avant qu'il ne soit trop tard", "maintenant ou jamais",
    "danger imminent", "menace imminente",
    "point de non-retour", "survie",
]

PROPAGANDA_CERTAINTY_MARKERS = [
    "tout le monde sait", "personne ne peut nier",
    "il est évident que", "sans aucun doute",
    "la vérité est que", "cela prouve que",
]

PROPAGANDA_EMOTIONAL_MARKERS = [
    "honte", "trahison", "scandale", "crime",
    "catastrophe", "effondrement", "panique",
    "massacre", "destruction",
]


def detect_propaganda_narrative(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "enemy_terms": [],
            "urgency_terms": [],
            "certainty_terms": [],
            "emotional_terms": [],
            "interpretation": "Aucune structure narrative propagandiste saillante détectée.",
        }

    t = text.lower()

    enemy_hits = unique_keep_order([term for term in PROPAGANDA_ENEMY_MARKERS if contains_term(t, term)])
    urgency_hits = unique_keep_order([term for term in PROPAGANDA_URGENCY_MARKERS if contains_term(t, term)])
    certainty_hits = unique_keep_order([term for term in PROPAGANDA_CERTAINTY_MARKERS if contains_term(t, term)])
    emotional_hits = unique_keep_order([term for term in PROPAGANDA_EMOTIONAL_MARKERS if contains_term(t, term)])

    raw_score = (
        len(enemy_hits) * 1.5 +
        len(urgency_hits) * 1.4 +
        len(certainty_hits) * 1.4 +
        len(emotional_hits) * 1.0
    )

    score = min(raw_score / 10, 1.0)

    if score < 0.15:
        interpretation = "Le texte présente peu de structures propagandistes."
    elif score < 0.35:
        interpretation = "Le texte contient quelques procédés narratifs orientés."
    elif score < 0.55:
        interpretation = "Le texte présente une structuration narrative orientée notable."
    elif score < 0.75:
        interpretation = "Le texte combine plusieurs procédés typiques de propagande narrative."
    else:
        interpretation = "Le texte est fortement structuré par des mécanismes de propagande narrative."

    return {
        "score": round(score, 3),
        "enemy_terms": enemy_hits,
        "urgency_terms": urgency_hits,
        "certainty_terms": certainty_hits,
        "emotional_terms": emotional_hits,
        "interpretation": interpretation,
    }

def compute_modern_propaganda_score(result: dict) -> dict:
    rhetorical = result.get("rhetorical_scores", {})
    emotions = result.get("emotional_registers", {})

    base_score = result.get("propaganda_score", 0)

    modern_score = (
        base_score * 0.35
        + rhetorical.get("saturation_rhetorique", 0) * 0.15
        + rhetorical.get("soupcon_systemique", 0) * 0.15
        + rhetorical.get("attaque", 0) * 0.10
        + rhetorical.get("amplification", 0) * 0.10
        + emotions.get("colere", 0) * 0.10
        + emotions.get("peur", 0) * 0.05
    )

    if (
        rhetorical.get("soupcon_systemique", 0) > 0.45
        and rhetorical.get("saturation_rhetorique", 0) > 0.40
        and emotions.get("colere", 0) > 0.40
    ):
        modern_score += 0.10

    score = round(min(modern_score, 1.0), 3)

    if score < 0.15:
        interpretation = "Le texte ne présente pas de structure propagandiste marquée."
    elif score < 0.35:
        interpretation = "Le texte contient quelques procédés d’orientation narrative ou émotionnelle."
    elif score < 0.55:
        interpretation = "Le texte présente une orientation propagandiste modérée."
    elif score < 0.75:
        interpretation = "Le texte combine plusieurs mécanismes typiques d’une propagande discursive."
    else:
        interpretation = "Le texte est fortement structuré par des mécanismes propagandistes."

    return {
        "score": score,
        "interpretation": interpretation,
    }

def compute_causal_overreach(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune causalité abusive saillante détectée."
        }

    t = text.lower()
    hits = unique_keep_order([term for term in CAUSAL_OVERREACH_TERMS if contains_term(t, term)])
    score = min(len(hits) * 2.5 / 10, 1.0)

    if score < 0.20:
        interpretation = "Peu de glissements causaux détectés."
    elif score < 0.40:
        interpretation = "Le texte contient quelques raccourcis causaux."
    elif score < 0.70:
        interpretation = "Le texte présente plusieurs liens causaux fragiles."
    else:
        interpretation = "Le texte repose fortement sur des causalités affirmées sans démonstration suffisante."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }

def compute_vague_authority(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune autorité vague saillante détectée."
        }

    t = text.lower()
    hits = unique_keep_order([term for term in VAGUE_AUTHORITY_TERMS if contains_term(t, term)])
    score = min(len(hits) * 2.5 / 10, 1.0)

    if score < 0.20:
        interpretation = "Peu d'autorités vagues détectées."
    elif score < 0.40:
        interpretation = "Le texte invoque quelques autorités imprécises."
    elif score < 0.70:
        interpretation = "Le texte s'appuie nettement sur des autorités non spécifiées."
    else:
        interpretation = "Le texte repose fortement sur des autorités vagues ou non traçables."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }

def compute_emotional_intensity(result: dict):
    emotions = result.get("emotional_registers", {})

    if not emotions:
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune charge émotionnelle saillante détectée."
        }

    score = (
        emotions.get("peur", 0) * 0.22
        + emotions.get("colere", 0) * 0.26
        + emotions.get("urgence", 0) * 0.18
        + emotions.get("fatalisme", 0) * 0.12
        + emotions.get("victimisation", 0) * 0.12
        + emotions.get("exaltation", 0) * 0.10
    )

    markers = [
        name for name, value in emotions.items()
        if value > 0
    ]

    if score < 0.15:
        interpretation = "Le texte reste peu chargé émotionnellement."
    elif score < 0.35:
        interpretation = "Le texte contient une charge émotionnelle modérée."
    elif score < 0.60:
        interpretation = "Le texte mobilise une charge émotionnelle notable."
    else:
        interpretation = "Le texte repose fortement sur une intensité émotionnelle orientant la lecture."

    return {
        "score": round(min(score, 1.0), 3),
        "markers": markers,
        "interpretation": interpretation,
    }

def compute_generalization(text: str):

    text_lower = text.lower()

    hits = [t for t in GENERALIZATION_TERMS if contains_term(text_lower, t)]

    score = min(len(hits) * 2 / 10, 1.0)

    if score < 0.2:
        interpretation = "Peu de généralisation détectée."
    elif score < 0.5:
        interpretation = "Quelques généralisations apparaissent."
    else:
        interpretation = "Le discours simplifie le réel par catégories globales."

    return score, interpretation, hits

def compute_abstract_enemy(text: str):

    text_lower = text.lower()

    hits = [t for t in ABSTRACT_ENEMY_TERMS if contains_term(text_lower, t)]

    score = min(len(hits) * 2.5 / 10, 1.0)

    if score < 0.2:
        interpretation = "Pas de désignation d'ennemi abstrait."
    elif score < 0.5:
        interpretation = "Quelques adversaires flous apparaissent."
    else:
        interpretation = "Le discours construit un adversaire abstrait."

    return score, interpretation, hits

def compute_certainty(text: str):

    text_lower = text.lower()

    hits = [t for t in CERTAINTY_TERMS if contains_term(text_lower, t)]

    score = min(len(hits) * 2.5 / 10, 1.0)

    if score < 0.2:
        interpretation = "Discours relativement nuancé."
    elif score < 0.5:
        interpretation = "Certitude rhétorique modérée."
    else:
        interpretation = "Certitude absolue fortement affirmée."

    return score, interpretation, hits

def compute_false_consensus(text: str):
    if not text or not text.strip():
        return 0.0, "Aucun faux consensus significatif détecté.", []

    t = normalize_text_for_markers(text)

    base_hits = [
        term for term in CONSENSUS_TERMS
        if contains_term(t, term) or term in t
    ]

    strong_hits = [
        term for term in FALSE_CONSENSUS_STRONG_PATTERNS
        if contains_term(t, term) or term in t
    ]

    structural_hits = []

    # Vérité supposée partagée
    if (
        ("ceux qui disent la vérité" in t or "ceux qui ouvrent les yeux" in t)
        and ("censur" in t or "ridiculis" in t or "exclus" in t or "ennemis du système" in t)
    ):
        structural_hits.append("vérité supposée partagée par les lucides")

    # Silence supposé comme preuve
    if (
        ("personne ne mentionne" in t or "personne ne parle" in t or "on ne dit jamais" in t)
        and ("faits" in t or "réalité" in t or "vérité" in t or "conséquences" in t)
    ):
        structural_hits.append("silence collectif présenté comme preuve")

    # Groupe lucide contre groupe aveugle
    if (
        ("ceux qui ouvrent les yeux" in t or "ceux qui disent la vérité" in t)
        and ("système" in t or "médias" in t or "autorités" in t)
    ):
        structural_hits.append("groupe lucide présenté comme porteur de vérité")

    all_hits = unique_keep_order(base_hits + strong_hits + structural_hits)

    raw_score = (
        len(base_hits) * 0.22
        + len(strong_hits) * 0.35
        + len(structural_hits) * 0.35
    )

    score = min(raw_score, 1.0)

    if score < 0.15:
        interpretation = "Aucun faux consensus significatif détecté."
    elif score < 0.35:
        interpretation = "Le texte suggère légèrement une adhésion collective implicite."
    elif score < 0.60:
        interpretation = "Le texte met en scène un consensus supposé."
    else:
        interpretation = "Le texte s'appuie fortement sur un faux consensus rhétorique."

    return round(score, 3), interpretation, all_hits

def compute_binary_opposition(text: str):
    if not text or not text.strip():
        return 0.0, "Aucune opposition binaire significative détectée.", []

    t = normalize_text_for_markers(text)

    hits = [
        term for term in BINARY_OPPOSITION_TERMS
        if contains_term(t, term)
    ]

    # Bonus structurel : d'un côté / de l'autre
    if ("d'un côté" in t or "d’un côté" in t) and ("de l'autre" in t or "de l’autre" in t):
        hits.append("structure d’un côté / de l’autre")

    # Bonus structurel : soit / soit
    if t.count("soit") >= 2:
        hits.append("structure soit / soit")

    hits = unique_keep_order(hits)

    strong_hits = [
        h for h in hits
        if h in BINARY_OPPOSITION_STRONG_TERMS
    ]

    weak_hits = [
        h for h in hits
        if h in BINARY_OPPOSITION_WEAK_TERMS
    ]

    other_hits = [
        h for h in hits
        if h not in BINARY_OPPOSITION_STRONG_TERMS
        and h not in BINARY_OPPOSITION_WEAK_TERMS
    ]

    weighted_hits = (
        len(strong_hits) * 1.0
        + len(weak_hits) * 0.5
        + len(other_hits) * 0.7
    )

    word_count = max(len(t.split()), 1)
    length_factor = max(1.0, word_count / 250)

    density = weighted_hits / length_factor

    score = min(density * 0.25, 1.0)

    if score < 0.15:
        interpretation = "Aucune opposition binaire significative détectée."
    elif score < 0.35:
        interpretation = "Tendance légère à structurer le discours en camps opposés."
    elif score < 0.60:
        interpretation = "Opposition binaire marquée entre pôles ou options."
    else:
        interpretation = "Discours fortement structuré en camps antagonistes."

    return round(score, 3), interpretation, hits

# =========================================================
# VICTIMISATION STRATÉGIQUE
# =========================================================
VICTIMIZATION_TERMS = [
    "on nous empêche",
    "on nous interdit",
    "on nous censure",
    "nous sommes censurés",
    "censuré",
    "censurée",
    "censurés",
    "discrédité",
    "discréditée",
    "discrédités",
    "marginalisé",
    "marginalisée",
    "marginalisés",
    "réduit au silence",
    "faire taire",
    "empêcher de dire",
    "interdit de dire",
    "vérité interdite",
    "vérités interdites",
    "dès que quelqu'un ose",
    "ceux qui osent parler",
    "les lanceurs d'alerte",
    "persécuté",
    "persécutés",
    "stigmatisé",
    "stigmatisés",
]

def compute_victimization(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune victimisation stratégique saillante détectée."
        }

    t = normalize_text_for_markers(text)

    hits = [
        term for term in VICTIMIZATION_TERMS
        if contains_term(t, term) or term in t
    ]

    score = min(len(hits) * 0.28, 1.0)

    if score < 0.15:
        interpretation = "Peu de victimisation stratégique détectée."
    elif score < 0.35:
        interpretation = "Le texte suggère une mise en scène légère de persécution."
    elif score < 0.60:
        interpretation = "Le texte mobilise nettement une posture victimaire."
    else:
        interpretation = "Le discours repose fortement sur une victimisation stratégique."

    return {
        "score": round(score, 3),
        "markers": unique_keep_order(hits),
        "interpretation": interpretation,
    }
# =========================================================
# FRAME SHIFT
# =========================================================
def compute_frame_shift(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucun déplacement du cadre argumentatif détecté."
        }

    t = normalize_text_for_markers(text)

    hits = unique_keep_order([
        term for term in FRAME_SHIFT_TERMS
        if contains_term(t, term)
    ])

    # Marqueurs de transition / bascule
    shift_connectors = [
        "cependant",
        "pourtant",
        "malgré cela",
        "mais",
        "toutefois",
        "néanmoins",
        "en revanche",
        "il n'empêche que"
    ]
    # Marqueurs de nuance
    nuance_terms = [
        "nuancer",
        "prudence",
        "prudent",
        "prudente",
        "restent prudents",
        "reste prudent",
        "certains économistes",
        "certains experts",
        "pourraient",
        "semble",
        "possible"
    ]
    # Marqueurs de bascule forte
    certainty_or_threat_terms = [
        "il est absolument certain",
        "absolument certain",
        "crise majeure",
        "crise sociale majeure",
        "si rien n'est fait",
        "immédiatement",
        "urgence",
        "danger",
        "catastrophe",
        "effondrement"
    ]
    has_connector = any(term in t for term in shift_connectors)
    has_nuance = any(term in t for term in nuance_terms)
    has_certainty_or_threat = any(term in t for term in certainty_or_threat_terms)

    if has_connector and has_nuance and has_certainty_or_threat:
        hits.append("bascule nuance → certitude/menace")

    elif has_nuance and has_certainty_or_threat:
        hits.append("coexistence nuance prudente / conclusion forte")

    hits = unique_keep_order(hits)
    score = min(len(hits) * 0.12, 1.0)

    if score < 0.15:
        interpretation = "Peu de déplacement du cadre argumentatif."
    elif score < 0.35:
        interpretation = "Le texte contient quelques tentatives de déplacement du débat."
    elif score < 0.60:
        interpretation = "Le discours modifie régulièrement le cadre du débat."
    else:
        interpretation = "Le discours repose fortement sur un déplacement du cadre argumentatif."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }
# =========================================================
# ASYMÉTRIE ARGUMENTATIVE
# =========================================================
def compute_argument_asymmetry(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "attack_count": 0,
            "argument_count": 0,
            "interpretation": "Aucune asymétrie argumentative détectée."
        }

    text_lower = text.lower()

    attack_hits = [
        term for term in ATTACK_TERMS
        if contains_term(text_lower, term)
    ]

    argument_hits = [
        term for term in ARGUMENT_TERMS
        if contains_term(text_lower, term)
    ]

    attack_count = len(unique_keep_order(attack_hits))
    argument_count = len(unique_keep_order(argument_hits))

    # Sécurité : pas d’asymétrie d’attaque sans attaque réelle.
    if attack_count == 0:
        score = 0.0

    # Si le texte attaque mais n’argumente pas, score modéré, pas automatique à 100%.
    elif argument_count == 0:
        score = min(attack_count * 0.18, 0.65)

    else:
        ratio = attack_count / max(argument_count, 1)
        score = min(ratio * 0.22, 1.0)

    if score < 0.15:
        interpretation = "Le texte reste globalement équilibré argumentativement."
    elif score < 0.35:
        interpretation = "L’argumentation montre une légère asymétrie."
    elif score < 0.60:
        interpretation = "Le discours privilégie l’attaque plutôt que la démonstration."
    else:
        interpretation = "Forte asymétrie argumentative : rhétorique d’attaque dominante."

    return {
        "score": round(score, 3),
        "attack_count": attack_count,
        "argument_count": argument_count,
        "interpretation": interpretation,
    }
THREAT_AMPLIFICATION_MARKERS = [
    "crise majeure",
    "crise sociale majeure",
    "catastrophe",
    "catastrophique",
    "effondrement",
    "danger imminent",
    "grave menace",
    "menace",
    "menace existentielle",
    "chaos",
    "désastre",
    "désastreux",
    "désastreuse",
    "désastreuses",
    "urgence absolue",
    "urgent",
    "avant qu'il ne soit trop tard",
    "il sera trop tard",
    "si rien n'est fait",
    "conséquences désastreuses",
    "tout va empirer",
    "irréversible",
    
    # menace extrême
    "menace existentielle",
    "danger extrême",
    "danger mortel",
    "catastrophe imminente",
    "effondrement total",
    "destruction du pays",
    "survie nationale",
    "point de non-retour",
    "invasion massive",
    "submersion totale",
    "chaos généralisé",
    "crise terminale",
    "menace historique",
    "danger absolu",

    # menace froide / stratégique
    "notre europe est mortelle",
    "elle peut mourir",
    "peut mourir",
    "question de la paix et de la guerre",
    "paix et de la guerre",
    "situation d'encerclement",
    "encerclement",
    "ce monde-là est fini",
    "bataille pour notre survie",
    "notre survie",
    "le réveil doit être brutal",
    "réveil brutal",
    "à un tournant",
]

THREAT_AMPLIFICATION_MARKERS += [
    "danger nucléaire",
    "excessivement dangereuse",
    "véritable fléau",
]

def compute_threat_amplification(text: str):
    text_lower = normalize_text_for_markers(text)

    hits = [
        marker for marker in THREAT_AMPLIFICATION_MARKERS
        if contains_term(text_lower, marker)
    ]

    hits = unique_keep_order(hits)

    # Évite le double comptage : "danger" + "danger nucléaire"
    hits = [
        h for h in hits
        if not any(h != other and h in other for other in hits)
    ]

    weak_markers = {"danger", "urgence", "menace", "grave"}
    strong_hits = [h for h in hits if h not in weak_markers]
    weak_hits = [h for h in hits if h in weak_markers]

    raw_score = len(strong_hits) * 0.16 + len(weak_hits) * 0.05
    score = min(raw_score, 1.0)

    if score < 0.15:
        interpretation = "Aucune amplification de menace significative détectée."
    elif score < 0.35:
        interpretation = "Le texte contient quelques formulations alarmistes."
    elif score < 0.60:
        interpretation = "Le texte amplifie notablement la perception de menace."
    else:
        interpretation = "Le discours repose fortement sur une amplification dramatique de la menace."

    return round(score, 3), interpretation, hits

# -----------------------------
# 19) Fausse analogie
# -----------------------------
FALSE_ANALOGY_TERMS = [
    "comme si", "c'est comme", "c’est comme",
    "de la même manière que",
    "exactement comme",
    "rien de différent de",
    "comparable à",
    "similaire à",
    "équivalent à",
    "just like",
    "exactly like",
    "similar to",
    "equivalent to",

    # ajouts
    "comme dans",
    "comme sous",
    "exactement le même chemin",
    "le même chemin",
    "ce parallèle",
    "voir ce parallèle",
]

def compute_false_analogy(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune fausse analogie saillante détectée."
        }

    t = normalize_text_for_markers(text)

    hits = [
        term for term in FALSE_ANALOGY_TERMS
        if contains_term(t, term) or term in t
    ]

    # Structure analogique historique
    if (
        ("comme dans" in t or "comme sous" in t or "même chemin" in t or "parallèle" in t)
        and ("empire" in t or "rome" in t or "romain" in t or "histoire" in t or "civilisation" in t)
    ):
        hits.append("analogie historique simplificatrice")

    hits = unique_keep_order(hits)

    score = min(len(hits) * 0.20, 1.0)

    if score < 0.15:
        interpretation = "Peu d’analogies douteuses détectées."
    elif score < 0.35:
        interpretation = "Le texte contient quelques rapprochements simplificateurs."
    elif score < 0.60:
        interpretation = "Le texte s’appuie sur plusieurs analogies fragiles."
    else:
        interpretation = "Le discours repose fortement sur des analogies trompeuses."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }
# -----------------------------
# 20) Surinterprétation factuelle
# -----------------------------
FACTUAL_OVERINTERPRETATION_TERMS = [
    "cela prouve que", "cela démontre que", "cela montre bien que",
    "la preuve que", "on voit bien que", "il faut en conclure que",
    "ce simple fait prouve", "ce fait montre que",
    "this proves that", "this demonstrates that", "this clearly shows that"
]

def compute_factual_overinterpretation(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune surinterprétation factuelle saillante détectée."
        }

    text_lower = text.lower()

    hits = [
        t for t in FACTUAL_OVERINTERPRETATION_TERMS
        if contains_term(text_lower, t) or t in text_lower
    ]

    accelerator_terms = [
        "donc forcément",
        "cela confirme définitivement",
        "cela démontre clairement",
        "on voit bien que",
        "la preuve absolue",
    ]

    accel_hits = [
        t for t in accelerator_terms
        if contains_term(text_lower, t) or t in text_lower
    ]

    all_hits = unique_keep_order(hits + accel_hits)

    raw_score = len(hits) * 0.28 + len(accel_hits) * 0.20
    score = min(raw_score, 1.0)

    if score < 0.15:
        interpretation = "Peu de surinterprétation factuelle détectée."
    elif score < 0.35:
        interpretation = "Le texte tire quelques conclusions un peu rapides."
    elif score < 0.60:
        interpretation = "Le texte surinterprète plusieurs éléments factuels."
    else:
        interpretation = "Le discours transforme fortement des faits partiels en conclusions globales."

    return {
        "score": round(score, 3),
        "markers": all_hits,
        "interpretation": interpretation,
    }
# -----------------------------
# 21) Dissonance interne
# -----------------------------
INTERNAL_DISSONANCE_PATTERNS = [
    r"\bil n'y a pas de preuve\b.{0,180}\bc'est certain\b",
    r"\bon ne sait pas\b.{0,180}\bil est évident\b",
    r"\bjamais\b.{0,120}\btoujours\b",
    r"\btoujours\b.{0,120}\bjamais\b",
    r"\baucun\b.{0,120}\btous\b",
    r"\btous\b.{0,120}\baucun\b",
    r"\bimpossible\b.{0,120}\bpossible\b",
    r"\bpossible\b.{0,120}\bimpossible\b",
]

NUANCE_DISSONANCE_TERMS = [
    "nuancer",
    "reste prudent",
    "restent prudents",
    "prudence",
    "certains économistes",
    "certains experts",
    "pourraient",
    "pourrait",
    "possible",
    "semble",
    "selon certains",
]
CERTAINTY_DISSONANCE_TERMS = [
    "il est absolument certain",
    "absolument certain",
    "sans aucun doute",
    "il est évident",
    "c'est évident",
    "indiscutable",
    "incontestable",
    "personne ne peut nier",
]
THREAT_DISSONANCE_TERMS = [
    "crise majeure",
    "crise sociale majeure",
    "danger imminent",
    "catastrophe",
    "effondrement",
    "désastre",
    "si rien n'est fait",
    "immédiatement",
]

def compute_internal_dissonance(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune dissonance interne saillante détectée."
        }

    t = normalize_text_for_markers(text)
    strong_hits = []
    tension_hits = []
    
    for pattern in INTERNAL_DISSONANCE_PATTERNS:
        if re.search(pattern, t, flags=re.DOTALL):
            strong_hits.append(pattern)
    
    has_nuance = any(term in t for term in NUANCE_DISSONANCE_TERMS)
    has_certainty = any(term in t for term in CERTAINTY_DISSONANCE_TERMS)
    has_threat = any(term in t for term in THREAT_DISSONANCE_TERMS)
    
    if has_nuance and has_certainty:
        tension_hits.append("tension nuance / certitude absolue")
    
    if has_nuance and has_threat:
        tension_hits.append("tension prudence / dramatisation de menace")
    
    if "sans précédent" in t and ("comme" in t or "similaire" in t):
        tension_hits.append("tension sans précédent / comparaison historique")
    
    if "urgence" in t and ("calme" in t or "calmement" in t):
        tension_hits.append("tension urgence / calme")
    
    hits = unique_keep_order(strong_hits + tension_hits)
    
    score = min(
        len(strong_hits) * 0.28 +
        len(tension_hits) * 0.12,
        1.0
    )

    if score < 0.20:
        interpretation = "Peu de tensions internes détectées."
    elif score < 0.45:
        interpretation = "Le discours présente quelques tensions internes."
    elif score < 0.70:
        interpretation = "Le discours présente des contradictions ou tensions notables."
    else:
        interpretation = "Le discours est fortement traversé par des contradictions internes."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }
# -----------------------------
# 22) Saturation normative
# -----------------------------
SATURATION_NORMATIVE_TERMS = [
    "scandaleux", "inacceptable", "honteux", "immoral", "criminel",
    "odieux", "abject", "indigne", "dangereux", "toxique",
    "scandalous", "unacceptable", "shameful", "immoral", "criminal",

    # ajouts utiles
    "dérive",
    "submersion",
    "effondrement",
    "catastrophe",
    "danger",
    "déni",
    "contre le peuple",
    "civilisation",
    "stratégie globale",
    "autorités cherchent à cacher",
    "médias officiels",
    "nier l'évidence",
    "nier l’évidence",
]

def compute_normative_saturation(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune saturation normative saillante détectée."
        }

    t = normalize_text_for_markers(text)
    hits = [
        term for term in SATURATION_NORMATIVE_TERMS
        if contains_term(t, term) or term in t
    ]
    score = min(len(hits) * 0.065, 1.0)

    if score < 0.15:
        interpretation = "Le texte reste peu saturé de jugements normatifs."
    elif score < 0.35:
        interpretation = "Le texte contient quelques jugements moraux appuyés."
    elif score < 0.60:
        interpretation = "Le texte est nettement saturé de qualifications normatives."
    else:
        interpretation = "Le discours remplace largement l’analyse par le jugement moral."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }
# -----------------------------
# 23) Rigidité doxique
# -----------------------------
DOXIC_RIGIDITY_TERMS = [
    "il est évident que", "il est clair que", "sans aucun doute",
    "personne ne peut nier", "tout le monde sait", "c'est incontestable",
    "cela ne fait aucun doute", "il est absolument certain",
    "it is obvious", "there is no doubt", "everyone knows"
]

def compute_doxic_rigidity(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune rigidité doxique saillante détectée."
        }

    text_lower = text.lower()
    hits = [t for t in DOXIC_RIGIDITY_TERMS if contains_term(text_lower, t)]
    score = min(len(hits) * 2.5 / 10, 1.0)

    if score < 0.15:
        interpretation = "Le discours reste relativement révisable."
    elif score < 0.35:
        interpretation = "Le texte montre quelques marqueurs de rigidité assertive."
    elif score < 0.60:
        interpretation = "Le texte présente une rigidité doxique notable."
    else:
        interpretation = "Le discours apparaît fortement verrouillé par ses certitudes."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }
# -----------------------------
# 24) Surdétermination narrative
# -----------------------------
NARRATIVE_OVERDETERMINATION_TERMS = [
    "tout s'explique par", "tout vient de", "tout est lié à",
    "tout cela fait partie du plan", "rien n'arrive par hasard",
    "la cause de tout", "la clé de tout", "c'est toujours la même logique",
    "everything is explained by", "nothing happens by chance", "part of the plan"
]

def compute_narrative_overdetermination(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune surdétermination narrative saillante détectée."
        }

    text_lower = text.lower()
    hits = [t for t in NARRATIVE_OVERDETERMINATION_TERMS if contains_term(text_lower, t)]
    score = min(len(hits) * 3 / 10, 1.0)

    if score < 0.15:
        interpretation = "Le texte ne repose pas sur un récit totalisant marqué."
    elif score < 0.35:
        interpretation = "Le texte propose quelques explications globalisantes."
    elif score < 0.60:
        interpretation = "Le discours tend à ramener des faits multiples à un récit unique."
    else:
        interpretation = "Le texte repose fortement sur une narration totalisante."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }

MORAL_POLARIZATION_TERMS = [
    "les bons contre les mauvais",
    "le bien contre le mal",
    "les patriotes contre les traîtres",
    "les honnêtes gens contre les corrompus",
    "les purs contre les corrompus",
    "les justes contre les pervers",
    "les innocents contre les coupables",

    # formes souples
    "le bien",
    "le mal",
    "bien est devenu",
    "mal est toléré",
    "ce qui est juste",
    "ce qui est injuste",
    "moralement juste",
    "inversion des valeurs",
    "ordre juste",
    "défendre ce qui est juste",
]
MORAL_POLARIZATION_TERMS += [
    "valeurs saines",
    "élites corrompues",
    "honnêtes citoyens",
    "méprisent le peuple",
    "protège ceux qui détruisent",
]

def compute_moral_polarization(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune polarisation morale saillante détectée."
        }

    t = normalize_text_for_markers(text)

    hits = [
        term for term in MORAL_POLARIZATION_TERMS
        if contains_term(t, term) or term in t
    ]

    # Bonus si bien + mal apparaissent ensemble
    if "bien" in t and "mal" in t:
        hits.append("opposition bien / mal")

    # Bonus si juste + injuste apparaissent ensemble
    if "juste" in t and "injuste" in t:
        hits.append("opposition juste / injuste")

    # Bonus structurel : camp vertueux contre camp corrompu/dominant
    if (
        any(term in t for term in INGROUP_TERMS)
        and any(term in t for term in OUTGROUP_TERMS)
        and any(w in t for w in [
            "honnêtes",
            "valeurs saines",
            "corrompues",
            "corrompus",
            "méprisent",
            "protège ceux qui détruisent",
            "détruisent",
        ])
    ):
        hits.append("opposition morale groupe vertueux / groupe corrompu")

    hits = unique_keep_order(hits)

    score = min(len(hits) * 0.20, 1.0)

    if score < 0.15:
        interpretation = "Peu de polarisation morale détectée."
    elif score < 0.35:
        interpretation = "Le texte contient quelques oppositions morales simplifiées."
    elif score < 0.60:
        interpretation = "Le texte structure nettement le débat en camps moraux opposés."
    else:
        interpretation = "Le discours repose fortement sur une polarisation morale."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }
# -----------------------------
# Simplification stratégique
# -----------------------------
STRATEGIC_SIMPLIFICATION_TERMS = [
    "la seule raison",
    "la seule cause",
    "tout vient de",
    "il suffit de",
    "tout s'explique par",
    "uniquement à cause de",
    "simplement parce que",
    "c'est aussi simple que",
]

def compute_strategic_simplification(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune simplification stratégique saillante détectée."
        }

    text_lower = text.lower()
    hits = [t for t in STRATEGIC_SIMPLIFICATION_TERMS if contains_term(text_lower, t) or t in text_lower]
    score = min(len(hits) * 0.30, 1.0)

    if score < 0.15:
        interpretation = "Peu de simplification stratégique détectée."
    elif score < 0.35:
        interpretation = "Le texte contient quelques raccourcis explicatifs."
    elif score < 0.60:
        interpretation = "Le texte réduit plusieurs phénomènes complexes à des causes simples."
    else:
        interpretation = "Le discours repose fortement sur une simplification stratégique du réel."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }
# -----------------------------
# Sophismes aristotéliciens de base
# -----------------------------
PETITION_PATTERNS = [
    "c'est vrai parce que",
    "c'est vrai car",
    "c'est la vérité",
    "cela prouve que c'est vrai",
    "c'est évident parce que c'est évident",
    "c'est vrai parce que c'est évident",
    "c'est évident parce que c'est vrai",
    "si cela dérange, c'est que c'est vrai",
    "si certaines idées dérangent autant, c'est précisément parce qu'elles sont vraies",
    "la preuve, c'est que",
    "cela démontre ce que nous savons déjà",
    "les signes sont partout",
    "il suffit d'ouvrir les yeux",
    "cela démontre que",
    "cela prouve que",
    "cela confirme que",
    "nier l'évidence",
    "nier l’évidence",
    "tout le monde voit",
]
PETITION_PATTERNS += [
    "l'histoire montre toujours la même chose",
    "l’histoire montre toujours la même chose",
    "refuser de voir ce parallèle",
    "ignorer les leçons les plus évidentes du passé",
    "il est donc évident que",
]
CAUSALITY_PATTERNS = [
    "depuis que",
    "à cause de",
    "est responsable de",
    "a provoqué",
    "a causé",
    "est la cause de",
]
GENERALIZATION_PATTERNS = [
    "tous les",
    "toujours",
    "jamais",
    "tout le monde",
    "personne ne",
]
# -----------------------------
# Sophismes supplémentaires
# -----------------------------
AD_HOMINEM_PATTERNS = [
    "cet idiot",
    "cet incapable",
    "il est stupide",
    "il est ridicule",
    "on ne peut pas faire confiance à",
]
IGNORANCE_PATTERNS = [
    "personne n'a prouvé que",
    "on ne peut pas prouver que",
    "il n'existe aucune preuve que",
    "rien ne prouve que le contraire",
]
SLIPPERY_SLOPE_PATTERNS = [
    "si on accepte",
    "alors bientôt",
    "cela mènera à",
    "on finira par",
]
FEAR_APPEAL_PATTERNS = [
    "danger",
    "menace",
    "catastrophe",
    "désastre",
    "nous allons tous subir",
]
FALSE_ANALOGY_STRONG_PATTERNS = [
    "c'est comme",
    "exactement comme",
    "de la même manière que",
    "tout comme",
]
FALSE_ANALOGY_STRONG_PATTERNS += [
    "comme dans les dernières années de l'empire romain",
    "empire romain",
    "exactement le même chemin",
    "refuser de voir ce parallèle",
]
VAGUE_AUTHORITY_PATTERNS = [
    "les experts",
    "les scientifiques disent",
    "des études montrent",
    "certains spécialistes",
    "les chercheurs disent",
]
FALSE_DILEMMA_PATTERNS = [
    "soit",
    "il n'y a que deux choix",
    "avec nous ou contre nous",
    "vous devez choisir",
]
# -----------------------------
# Sophismes axiologiques / idéologiques
# -----------------------------
NORMATIVE_QUALIFICATION_PATTERNS = [
    "complotiste",
    "raciste",
    "xénophobe",
    "extrémiste",
    "antiscientifique",
    "populiste",
    "fasciste",
    "réactionnaire",
    "haineux",
    "dangereux",
]
IDEOLOGICAL_PREMISE_PATTERNS = [
    "il est évident que",
    "il est clair que",
    "tout le monde sait que",
    "il va de soi que",
    "il est largement admis que",
]
FALSE_CONSENSUS_STRONG_PATTERNS = [
    "personne n'ose le dire",
    "les médias cachent la vérité",
    "tout le monde sait mais personne ne dit rien",
    "les experts indépendants alertent",
    "on nous cache la vérité",
    "ceux qui ouvrent les yeux comprennent",

    "tout le monde voit désormais",
    "tout le monde voit",
    "nier l'évidence",
    "nier l’évidence",
    "les signes sont partout",
    "personne ne peut nier",
]
FALSE_CONSENSUS_STRONG_PATTERNS += [
    "tous les observateurs lucides",
    "observateurs lucides",
    "constatent désormais",
    "ceux qui continuent de nier cette réalité",
]
ARGUMENT_FROM_NATURE_PATTERNS = [
    "par nature",
    "naturellement",
    "il est naturel que",
    "il est contre-nature",
    "contre nature",
    "contre-nature",
    "nature humaine",
    "loi naturelle",
    "ordre naturel",
    "c'est naturel",
    "ce n'est pas naturel",
    "une société ne peut survivre si elle nie ses propres fondements",
    "tout système finit par se défendre",
]
ARGUMENT_FROM_NATURE_PATTERNS += [
    "structures plus naturelles",
    "plus naturelles",
    "fondements biologiques",
    "fondements biologiques et historiques",
    "loi presque naturelle",
    "loi naturelle",
]
# -----------------------------
# Détection texte historique / chronologique
# -----------------------------
HISTORICAL_MARKERS = [
    "en 1789", "en 1792", "en 1815", "en 1914", "en 1939",
    "au xixe siècle", "au xxe siècle", "durant", "pendant",
    "à cette époque", "le règne de", "la bataille de",
    "la révolution", "l'empire", "la guerre", "le traité",
    "chronologie", "événement", "date", "archives",
    "historique", "contexte historique"
]
def detect_historical_text_mode(text: str):
    if not text or not text.strip():
        return {
            "is_historical": False,
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucun régime historique détecté."
        }

    t = text.lower()

    date_hits = re.findall(r"\b(?:1[0-9]{3}|20[0-9]{2})\b", t)
    marker_hits = unique_keep_order(
        [m for m in HISTORICAL_MARKERS if contains_term(t, m)]
    )

    raw_score = len(date_hits) * 0.6 + len(marker_hits) * 1.2
    score = min(raw_score / 10, 1.0)

    is_historical = score >= 0.35 or len(date_hits) >= 4

    if not is_historical:
        interpretation = "Le texte ne semble pas relever principalement d’un régime historique."
    elif score < 0.60:
        interpretation = "Le texte présente une structure partiellement historique ou chronologique."
    else:
        interpretation = "Le texte relève fortement d’un régime historique ou chronologique."

    return {
        "is_historical": is_historical,
        "score": round(score, 3),
        "markers": marker_hits + date_hits[:10],
        "interpretation": interpretation
    }
# -----------------------------
# Cherry Picking / sélection biaisée
# -----------------------------
CHERRY_PICKING_PATTERNS = [
    "une étude montre",
    "une seule étude montre",
    "un exemple prouve",
    "ce cas prouve",
    "ce seul cas montre",
    "quelques cas montrent",
    "certains cas prouvent",
    "un témoignage prouve",
    "cet exemple démontre",
    "la preuve avec ce cas",
]
CHERRY_PICKING_OMISSION_MARKERS = [
    "sans parler du reste",
    "on oublie souvent que",
    "personne ne mentionne",
    "les médias cachent",
    "on ne vous dit pas que",
]
CHERRY_PICKING_PATTERNS += [
    "des exemples montrent",
    "certains exemples montrent",
    "quelques exemples prouvent",
    "certains cas récents le prouvent",
    "certains cas récents le montrent",
    "plusieurs cas le prouvent",
    "il suffit de voir",
    "on le voit avec",
    "cela se voit avec",
    "prenons un exemple",
    "comme par exemple",
]
CHERRY_PICKING_OMISSION_MARKERS += [
    "on ignore volontairement",
    "on passe sous silence",
    "ce qu'on ne dit jamais",
    "ce que l'on ne dit jamais",
    "les chiffres qu'on cache",
    "les données qu'on oublie",
]
CHERRY_PICKING_PATTERNS += [
    "une seule étude sérieuse suffit",
    "quelques cas récents prouvent",
    "quelques cas récents le prouvent",
]
def detect_cherry_picking(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "matches": [],
            "omission_markers": [],
            "structural_markers": [],
            "markers": [],
            "interpretation": "Aucune sélection biaisée saillante détectée."
        }

    t = normalize_text_for_markers(text)

    matches = [
        p for p in CHERRY_PICKING_PATTERNS
        if contains_term(t, p) or p in t
    ]

    omission_hits = [
        p for p in CHERRY_PICKING_OMISSION_MARKERS
        if contains_term(t, p) or p in t
    ]

    structural_hits = []

    if (
        ("un exemple" in t or "un cas" in t or "un témoignage" in t)
        and ("donc" in t or "cela prouve" in t or "cela montre" in t)
    ):
        structural_hits.append("généralisation à partir d’un cas")

    if "comme par exemple" in t and ("donc" in t or "ainsi" in t):
        structural_hits.append("enchaînement exemple → conclusion")

    if (
        ("quelques cas" in t or "certains cas" in t or "une seule étude" in t)
        and ("prouvent" in t or "prouve" in t or "suffit" in t)
    ):
        structural_hits.append("cas ou étude isolée utilisée comme preuve")

    all_markers = unique_keep_order(matches + omission_hits + structural_hits)

    raw_score = (
        len(matches) * 0.25 +
        len(omission_hits) * 0.35 +
        len(structural_hits) * 0.35
    )
    
    score = min(raw_score, 1.0)

    if score < 0.15:
        interpretation = "Peu de sélection biaisée détectée."
    elif score < 0.35:
        interpretation = "Le texte semble s’appuyer sur quelques exemples isolés."
    elif score < 0.60:
        interpretation = "Le texte présente plusieurs indices de sélection partielle des faits."
    else:
        interpretation = "Le discours semble fortement structuré par une sélection biaisée des exemples ou des preuves."

    return {
        "score": round(score, 3),
        "matches": matches,
        "omission_markers": omission_hits,
        "structural_markers": structural_hits,
        "markers": all_markers,
        "interpretation": interpretation,
    }

def detect_petition_principii(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "matches": [],
            "markers": [],
            "interpretation": "Aucune pétition de principe saillante détectée."
        }

    t = normalize_text_for_markers(text)

    matches = [
        p for p in PETITION_PATTERNS
        if contains_term(t, p) or p in t
    ]

    if (
        ("si certaines idées dérangent" in t or "si cela dérange" in t)
        and ("vraies" in t or "vrai" in t)
    ):
        matches.append("ce qui dérange serait vrai parce que cela dérange")

    if (
        ("il est évident" in t or "c'est évident" in t)
        and ("cela prouve" in t or "cela montre" in t or "donc" in t)
    ):
        matches.append("évidence utilisée comme démonstration")

    matches = unique_keep_order(matches)

    score = min(len(matches) * 0.25, 1.0)

    if score < 0.15:
        interpretation = "Aucune pétition de principe saillante détectée."
    elif score < 0.35:
        interpretation = "Le texte contient une circularité argumentative légère."
    elif score < 0.60:
        interpretation = "Le texte présente une pétition de principe notable."
    else:
        interpretation = "Le raisonnement repose fortement sur une conclusion répétée comme preuve."

    return {
        "score": round(score, 3),
        "matches": matches,
        "markers": matches,
        "interpretation": interpretation
    }

def detect_false_causality_basic(text: str):
    text_lower = text.lower()
    matches = [p for p in CAUSALITY_PATTERNS if contains_term(text_lower, p) or p in text_lower]
    return {
        "score": min(len(matches) * 0.4, 1.0),
        "matches": matches,
        "interpretation": "Lien causal affirmé plus vite qu’il n’est démontré." if matches else "Aucune fausse causalité saillante détectée."
    }

def detect_hasty_generalization(text: str):
    text_lower = text.lower()
    matches = [p for p in GENERALIZATION_PATTERNS if contains_term(text_lower, p) or p in text_lower]
    return {
        "score": min(len(matches) * 0.3, 1.0),
        "matches": matches,
        "interpretation": "Passage abusif de quelques cas à une règle générale." if matches else "Aucune généralisation abusive saillante détectée."
    }

def detect_vague_authority_basic(text: str):
    text_lower = text.lower()
    matches = [p for p in VAGUE_AUTHORITY_PATTERNS if contains_term(text_lower, p) or p in text_lower]
    return {
        "score": min(len(matches) * 0.5, 1.0),
        "matches": matches,
        "interpretation": "Autorité invoquée sans source précise." if matches else "Aucune autorité vague saillante détectée."
    }

def detect_false_dilemma(text: str):
    text_lower = text.lower()

    matches = [
        p for p in FALSE_DILEMMA_PATTERNS
        if contains_term(text_lower, p) or p in text_lower
    ]

    nuance_markers = [
        "plusieurs options",
        "plusieurs facteurs",
        "plusieurs solutions",
        "doivent être distingués",
        "ne signifie pas nécessairement",
        "éviter deux excès",
        "d'autres options",
        "d’autres options",
        "nuancer",
        "cependant",
        "toutefois",
        "néanmoins",
    ]

    nuance_hits = [
        marker for marker in nuance_markers
        if contains_term(text_lower, marker)
    ]

    raw_score = len(matches) * 0.25
    nuance_reduction = min(len(nuance_hits) * 0.07, 0.35)

    score = max(0.0, min(raw_score - nuance_reduction, 1.0))

    if score <= 0.05 and matches and nuance_hits:
        interpretation = (
            "Des oppositions binaires existent, mais elles sont compensées "
            "par des marqueurs d’ouverture ou de nuance."
        )
    elif score >= 0.60:
        interpretation = "Réduction forte du réel à deux options."
    elif score >= 0.35:
        interpretation = "Réduction artificielle du réel à deux options."
    elif score >= 0.15:
        interpretation = "Simplification binaire légère ou partielle."
    else:
        interpretation = "Aucun faux dilemme saillant détecté."

    return {
        "score": round(score, 3),
        "matches": matches,
        "nuance_markers": nuance_hits,
        "nuance_count": len(nuance_hits),
        "interpretation": interpretation,
    }

def detect_ad_hominem(text: str):
    text_lower = text.lower()
    matches = [p for p in AD_HOMINEM_PATTERNS if p in text_lower]
    return {
        "score": min(len(matches) * 0.5, 1.0),
        "matches": matches,
        "interpretation": "Attaque contre la personne plutôt que contre l’argument." if matches else "Aucun ad hominem saillant détecté."
    }

def detect_argument_from_ignorance(text: str):
    text_lower = text.lower()
    matches = [p for p in IGNORANCE_PATTERNS if p in text_lower]
    return {
        "score": min(len(matches) * 0.5, 1.0),
        "matches": matches,
        "interpretation": "Conclusion tirée de l’absence de preuve." if matches else "Aucun argument d’ignorance détecté."
    }


def detect_slippery_slope(text: str):
    text_lower = text.lower()
    matches = [p for p in SLIPPERY_SLOPE_PATTERNS if p in text_lower]
    return {
        "score": min(len(matches) * 0.4, 1.0),
        "matches": matches,
        "interpretation": "Projection catastrophiste en chaîne." if matches else "Aucune pente glissante détectée."
    }


def detect_fear_appeal(text: str):
    text_lower = text.lower()
    matches = [p for p in FEAR_APPEAL_PATTERNS if p in text_lower]
    return {
        "score": min(len(matches) * 0.3, 1.0),
        "matches": matches,
        "interpretation": "Argument basé sur la peur plutôt que sur l’analyse." if matches else "Aucun appel à la peur détecté."
    }


def detect_false_analogy_strong(text: str):
    text_lower = text.lower()
    matches = [p for p in FALSE_ANALOGY_STRONG_PATTERNS if p in text_lower]
    return {
        "score": min(len(matches) * 0.4, 1.0),
        "matches": matches,
        "interpretation": "Comparaison trompeuse servant de raccourci argumentatif." if matches else "Aucune analogie trompeuse détectée."
    }

def detect_normative_qualification(text: str):
    text_lower = text.lower()
    matches = [p for p in NORMATIVE_QUALIFICATION_PATTERNS if contains_term(text_lower, p) or p in text_lower]
    return {
        "score": min(len(matches) * 0.35, 1.0),
        "matches": matches,
        "interpretation": "Des qualifications normatives servent de substitut à l’argumentation." if matches else "Aucune qualification normative déguisée détectée."
    }


def detect_ideological_premise(text: str):
    text_lower = text.lower()
    matches = [p for p in IDEOLOGICAL_PREMISE_PATTERNS if contains_term(text_lower, p) or p in text_lower]
    return {
        "score": min(len(matches) * 0.4, 1.0),
        "matches": matches,
        "interpretation": "Le raisonnement repose sur des prémisses idéologiques implicites." if matches else "Aucune prémisse idéologique implicite détectée."
    }

def detect_false_consensus_strong(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "matches": [],
            "markers": [],
            "interpretation": "Aucun faux consensus renforcé détecté."
        }

    t = normalize_text_for_markers(text)

    matches = [
        p for p in FALSE_CONSENSUS_STRONG_PATTERNS
        if contains_term(t, p) or p in t
    ]

    if (
        any(p in t for p in ["tout le monde", "personne ne peut nier", "chacun sait", "les signes sont partout"])
        and any(p in t for p in ["cela prouve", "ce qui démontre", "preuve", "évidence"])
    ):
        matches.append("consensus supposé utilisé comme preuve")

    matches = unique_keep_order(matches)

    score = min(len(matches) * 0.45, 1.0)

    if score < 0.15:
        interpretation = "Aucun faux consensus renforcé détecté."
    elif score < 0.35:
        interpretation = "Le texte suggère un consensus présenté comme évidence."
    elif score < 0.60:
        interpretation = "Le texte met en scène un consensus supposé comme preuve."
    else:
        interpretation = "Le discours transforme fortement un accord supposé en preuve argumentative."

    return {
        "score": round(score, 3),
        "matches": matches,
        "markers": matches,
        "interpretation": interpretation
    }

def detect_argument_from_nature(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "matches": [],
            "interpretation": "Aucun argument de nature détecté."
        }

    t = normalize_text_for_markers(text)

    matches = [
        p for p in ARGUMENT_FROM_NATURE_PATTERNS
        if contains_term(t, p) or p in t
    ]

    score = min(len(matches) * 0.35, 1.0)

    return {
        "score": round(score, 3),
        "matches": unique_keep_order(matches),
        "interpretation": (
            "Le caractère naturel ou contre-naturel est utilisé comme argument de vérité ou de valeur."
            if matches else
            "Aucun argument de nature détecté."
        )
    }
DESCRIPTIVE_NORMATIVE_CONFUSION_PATTERNS = [
    "donc il faut",
    "donc nous devons",
    "cela prouve qu'il faut",
    "cela montre qu'il faut",
    "par conséquent nous devons",
    "il faut agir",
    "nous devons agir",
    "il est nécessaire de",
    "il est nécessaire d'agir"
    "il est nécessaire d’interdire"
    "il est nécessaire d’imposer"
    "il devient nécessaire de",
    "il devient nécessaire d",
    "il est désormais nécessaire de",
    "cela signifie qu'il faut",
    "cela implique que nous devons",
    "soit nous réagissons",
    "si rien n'est fait",
    "si rien n’est fait",
]
DESCRIPTIVE_NORMATIVE_CONFUSION_PATTERNS += [
    "nous devons revenir",
    "il est donc évident que nous devons",
    "il est donc évident que nous devons revenir",
]

def detect_descriptive_normative_confusion(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "matches": [],
            "markers": [],
            "nuance_markers": [],
            "nuance_count": 0,
            "interpretation": "Aucune confusion descriptif / normatif détectée."
        }

    t = normalize_text_for_markers(text)

    matches = [
        p for p in DESCRIPTIVE_NORMATIVE_CONFUSION_PATTERNS
        if contains_term(t, p) or p in t
    ]

    if (
        any(w in t for w in [
            "crise", "danger", "menace", "dérive", "destruction",
            "catastrophe", "effondrement", "submersion"
        ])
        and any(w in t for w in [
            "il faut", "nous devons", "on doit", "nécessaire",
            "agir", "réagir", "si rien n'est fait", "si rien n’est fait"
        ])
    ):
        matches.append("constat alarmiste transformé en obligation")

    if (
        "nécessaire d'agir" in t
        or "nécessaire d’agir" in t
        or "avant qu'il ne soit trop tard" in t
        or "avant qu’il ne soit trop tard" in t
        or "rester passif" in t
    ):
        matches.append("injonction issue d’un constat alarmiste")

    analytical_nuance_markers = [
        "plusieurs facteurs",
        "plusieurs options",
        "doivent être distingués",
        "ne signifie pas nécessairement",
        "peut rester",
        "analyse rigoureuse",
        "comprendre",
        "à quel coût",
        "avec quelles perspectives",
        "selon quelle stratégie",
        "cependant",
        "toutefois",
        "néanmoins",
        "éviter deux excès",
    ]

    nuance_hits = [
        m for m in analytical_nuance_markers
        if contains_term(t, m)
    ]

    matches = unique_keep_order(matches)

    raw_score = len(matches) * 0.30
    nuance_reduction = min(len(nuance_hits) * 0.06, 0.35)

    score = max(0.0, min(raw_score - nuance_reduction, 1.0))

    if score <= 0.05 and matches and nuance_hits:
        interpretation = (
            "Un passage du descriptif vers le normatif est repéré, mais il est "
            "fortement compensé par des marqueurs d’analyse, de nuance ou de méthode."
        )
    elif score < 0.15:
        interpretation = "Aucune confusion descriptif / normatif détectée."
    elif score < 0.35:
        interpretation = "Le texte contient un léger glissement du constat vers l’injonction."
    elif score < 0.60:
        interpretation = "Le texte transforme plusieurs constats en prescriptions."
    else:
        interpretation = "Le discours glisse fortement de la description vers l’injonction normative."

    return {
        "score": round(score, 3),
        "matches": matches,
        "markers": matches,
        "nuance_markers": nuance_hits,
        "nuance_count": len(nuance_hits),
        "interpretation": interpretation
    }

# -----------------------------
# Manipulation statistique
# -----------------------------

STATISTICAL_MANIPULATION_MARKERS = [
    "les chiffres parlent d'eux-mêmes",
    "augmentation spectaculaire",
    "explosion des chiffres",
    "hausse massive",
    "effondrement statistique",
    "les statistiques prouvent",
    "les données montrent clairement",
    "les chiffres sont incontestables",
    "selon les chiffres",
    "les courbes explosent",
    "record historique",
    "jamais vu",
    "sans précédent",
    "x fois plus",
    "%",
]

def detect_statistical_manipulation(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune manipulation statistique notable détectée."
        }

    t = normalize_text_for_markers(text)

    markers = []

    # -----------------------------
    # 1) marqueurs directs
    # -----------------------------
    for m in STATISTICAL_MANIPULATION_MARKERS:
        if contains_term(t, m) or m in t:
            markers.append(m)

    # -----------------------------
    # 2) chiffres sans contexte
    # -----------------------------
    numbers = re.findall(r"\d+(?:[\.,]\d+)?\s*%?", text)

    context_words = [
        "source",
        "étude",
        "rapport",
        "selon",
        "données",
        "échantillon",
        "sur",
        "population",
        "entre",
        "depuis",
        "jusqu'à",
        "jusqu’a",
    ]

    has_context = any(w in t for w in context_words)

    if len(numbers) >= 2 and not has_context:
        markers.append("chiffres sans contexte méthodologique")

    # -----------------------------
    # 3) pourcentages alarmistes
    # -----------------------------
    if "%" in text and any(
        w in t for w in [
            "explosion",
            "catastrophe",
            "effondrement",
            "submersion",
            "invasion",
            "crise"
        ]
    ):
        markers.append("statistiques utilisées pour dramatisation")

    markers = unique_keep_order(markers)

    score = min(len(markers) * 0.25, 1.0)

    if score < 0.15:
        interpretation = "Peu d’usage problématique des statistiques détecté."
    elif score < 0.35:
        interpretation = "Quelques usages statistiques peuvent orienter la perception."
    elif score < 0.60:
        interpretation = "Le texte utilise plusieurs procédés statistiques fragiles ou orientés."
    else:
        interpretation = "Le discours s’appuie fortement sur des statistiques présentées de manière orientée."

    return {
        "score": round(score, 3),
        "markers": markers,
        "interpretation": interpretation,
    }

# -----------------------------
# Comparaison trompeuse
# -----------------------------

MISSING_REFERENCE_MARKERS = [
    "selon une étude",
    "selon des chiffres",
    "les données montrent",
    "les statistiques montrent",
    "des experts affirment",
    "une étude récente",
    "une étude choc",
    "des chercheurs affirment",
    "des spécialistes estiment",
    "les chiffres prouvent",
]

def detect_misleading_comparison(text: str):

    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": (
                "Aucune comparaison trompeuse notable détectée."
            )
        }

    t = normalize_text_for_markers(text)

    markers = []

    # -----------------------------
    # 1) Marqueurs réellement orientants
    # -----------------------------
    strong_markers = [
        "x fois plus",
        "deux fois plus",
        "trois fois plus",
        "plus que jamais",
        "moins que jamais",
        "record historique",
        "niveau jamais atteint",
        "explosion comparée à",
        "beaucoup plus que",
        "bien plus que",
        "nettement supérieur",
        "nettement inférieur",
    ]

    for m in strong_markers:
        if contains_term(t, m):
            markers.append(m)

    # -----------------------------
    # 2) Comparaisons sans référentiel
    # -----------------------------
    comparison_terms = [
        "plus",
        "moins",
        "supérieur",
        "inférieur",
        "davantage",
    ]

    reference_terms = [
        "par rapport à",
        "comparé à",
        "selon",
        "source",
        "étude",
        "moyenne",
        "en 2020",
        "en 2021",
        "en 2022",
        "en 2023",
        "en 2024",
    ]

    comparison_hits = sum(
        1 for w in comparison_terms
        if f" {w} " in f" {t} "
    )

    reference_hits = sum(
        1 for w in reference_terms
        if contains_term(t, w)
    )

    if comparison_hits >= 3 and reference_hits == 0:
        markers.append("comparaisons sans référentiel clair")

    # -----------------------------
    # 3) Amplification comparative
    # -----------------------------
    if (
        any(w in t for w in [
            "jamais",
            "historique",
            "sans précédent"
        ])
        and any(w in t for w in [
            "plus",
            "moins",
            "hausse",
            "baisse"
        ])
    ):
        markers.append("comparaison amplifiée")

    # -----------------------------
    # 4) Réduction par nuance
    # -----------------------------
    nuance_markers = [
        "plusieurs facteurs",
        "plusieurs options",
        "doivent être distingués",
        "ne signifie pas nécessairement",
        "cependant",
        "toutefois",
        "néanmoins",
        "nuancer",
        "éviter deux excès",
    ]

    nuance_hits = [
        m for m in nuance_markers
        if contains_term(t, m)
    ]

    markers = unique_keep_order(markers)

    raw_score = len(markers) * 0.18
    nuance_reduction = min(len(nuance_hits) * 0.06, 0.30)

    score = max(0.0, min(raw_score - nuance_reduction, 1.0))

    # -----------------------------
    # Interprétation
    # -----------------------------
    if score <= 0.05 and markers and nuance_hits:
        interpretation = (
            "Certaines comparaisons existent, mais elles sont fortement "
            "contextualisées ou nuancées."
        )

    elif score < 0.15:
        interpretation = (
            "Peu de comparaisons problématiques détectées."
        )

    elif score < 0.35:
        interpretation = (
            "Quelques comparaisons peuvent orienter la perception."
        )

    elif score < 0.60:
        interpretation = (
            "Le texte utilise plusieurs comparaisons fragiles "
            "ou insuffisamment contextualisées."
        )

    else:
        interpretation = (
            "Le discours repose fortement sur des comparaisons "
            "potentiellement trompeuses."
        )

    return {
        "score": round(score, 3),
        "markers": markers,
        "nuance_markers": nuance_hits,
        "nuance_count": len(nuance_hits),
        "interpretation": interpretation,
    }

MISSING_REFERENCE_MARKERS = [
    "selon une étude",
    "selon des chiffres",
    "les données montrent",
    "les statistiques montrent",
    "des experts affirment",
    "une étude récente",
    "une étude choc",
    "des chercheurs affirment",
    "des spécialistes estiment",
    "les chiffres prouvent",
]

def detect_missing_reference_data(text: str):

    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune donnée sans référentiel détectée."
        }

    t = normalize_text_for_markers(text)

    markers = [
        m for m in MISSING_REFERENCE_MARKERS
        if contains_term(t, m)
    ]

    score = min(len(markers) * 0.20, 1.0)

    if score < 0.15:
        interpretation = "Les données semblent suffisamment contextualisées."
    elif score < 0.35:
        interpretation = "Quelques données manquent de référentiel clair."
    elif score < 0.60:
        interpretation = "Plusieurs affirmations reposent sur des données peu contextualisées."
    else:
        interpretation = "Le discours utilise fortement des données sans référentiel précis."

    return {
        "score": round(score, 3),
        "markers": markers,
        "interpretation": interpretation,
    }

# -----------------------------
# Cohérence trompeuse avancée
# -----------------------------

ADVANCED_DECEPTIVE_COHERENCE_MARKERS = [
    "ceux qui disent la vérité",
    "ouvrir les yeux",
    "le système refuse",
    "les médias manipulent",
    "les autorités mentent",
    "personne ne mentionne",
    "tout est lié",
    "on nous cache",
    "ce n'est pas un hasard",
    "si on nous critique",
    "cela prouve que nous avons raison",
    "la preuve qu'ils ont peur",
    "on cherche à nous faire taire",
    "les élites corrompues",
    "les honnêtes citoyens",
    "avant qu'il ne soit trop tard",
    "avant qu’il ne soit trop tard",
]

def compute_advanced_deceptive_coherence(text: str):

    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": (
                "Aucune cohérence trompeuse avancée détectée."
            )
        }

    t = normalize_text_for_markers(text)

    markers = []

    # -----------------------------
    # 1) Marqueurs directs
    # -----------------------------
    for m in ADVANCED_DECEPTIVE_COHERENCE_MARKERS:
        if contains_term(t, m) or m in t:
            markers.append(m)

    # -----------------------------
    # 2) Cohérence + certitude
    # -----------------------------
    if (
        ("donc" in t or "ainsi" in t or "par conséquent" in t)
        and (
            "il est certain" in t
            or "absolument certain" in t
            or "évident" in t
        )
    ):
        markers.append("enchaînement logique fortement affirmatif")

    # Projection fortement affirmée
    if (
        any(w in t for w in [
            "va remplacer",
            "va provoquer",
            "conduira à",
            "mènera à",
            "d'ici",
            "d’ici",
            "crise majeure",
            "révolution sans précédent",
        ])
        and (
            "absolument certain" in t
            or "certain" in t
            or "inévitable" in t
        )
    ):
        markers.append("projection persuasive fortement affirmée")

    # -----------------------------
    # 3) Auto-validation narrative
    # -----------------------------
    if (
        ("censur" in t or "ridiculis" in t or "attaqu" in t)
        and (
            "preuve" in t
            or "cela montre" in t
            or "cela prouve" in t
        )
    ):
        markers.append("récit auto-validant")

    # -----------------------------
    # 4) Opposition structurante
    # -----------------------------
    if (
        ("eux" in t or "élites" in t or "système" in t)
        and (
            "nous" in t
            or "citoyens" in t
            or "patriotes" in t
        )
    ):
        markers.append("polarisation cohérente structurante")

    # Cohérence catastrophiste fluide
    catastrophe_terms = [
        "danger",
        "menace",
        "effondrement",
        "catastrophe",
        "chaos",
        "désastre",
        "submersion",
        "invasion",
    ]
    
    method_terms = [
        "rapport",
        "étude",
        "expert",
        "selon",
    ]
    
    nuance_terms = [
        "ne signifie pas nécessairement",
        "plusieurs facteurs",
        "plusieurs options",
        "doivent être distingués",
        "peut rester",
        "analyse rigoureuse",
        "cependant",
        "toutefois",
        "néanmoins",
        "éviter deux excès",
    ]
    
    has_catastrophe = any(w in t for w in catastrophe_terms)
    has_method = any(w in t for w in method_terms)
    has_nuance = any(w in t for w in nuance_terms)
    
    if has_catastrophe and has_method and not has_nuance:
        markers.append("cohérence catastrophiste argumentée")

    # -----------------------------
    # Nettoyage
    # -----------------------------
    markers = unique_keep_order(markers)
    
    nuance_hits = [
        m for m in [
            "ne signifie pas nécessairement",
            "plusieurs facteurs",
            "plusieurs options",
            "doivent être distingués",
            "peut rester",
            "analyse rigoureuse",
            "cependant",
            "toutefois",
            "néanmoins",
            "éviter deux excès",
        ]
        if contains_term(t, m)
    ]
    
    # -----------------------------
    # Score
    # -----------------------------
    raw_score = len(markers) * 0.18
    nuance_reduction = min(len(nuance_hits) * 0.04, 0.25)
    
    score = max(0.0, min(raw_score - nuance_reduction, 1.0))

    # -----------------------------
    # Interprétation
    # -----------------------------
    if score < 0.15:
        interpretation = (
            "Aucune cohérence trompeuse avancée détectée."
        )

    elif score < 0.35:
        interpretation = (
            "Le texte présente quelques structures cohérentes mais fragiles."
        )

    elif score < 0.60:
        interpretation = (
            "Le discours paraît cohérent tout en reposant partiellement "
            "sur des mécanismes orientés."
        )

    else:
        interpretation = (
            "Le discours combine plusieurs mécanismes de cohérence "
            "persuasive pouvant masquer une faible robustesse démonstrative."
        )

    return {
        "score": round(score, 3),
        "markers": markers,
        "nuance_markers": nuance_hits,
        "nuance_count": len(nuance_hits),
        "interpretation": interpretation,
    }

# -----------------------------
# Enthymèmes implicites complexes
# -----------------------------

COMPLEX_ENTHYMEME_MARKERS = [
    "ceux qui disent la vérité",
    "ceux qui ouvrent les yeux",
    "il devient donc nécessaire",
    "nécessaire d'agir",
    "nécessaire d’agir",
    "rester passif reviendrait",
    "cela prouve que",
    "cela montre que",
    "donc il faut",
    "donc nous devons",
    "il faut agir",
    "nous devons agir",
]

def compute_complex_enthymemes(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucun enthymème complexe notable détecté."
        }

    t = normalize_text_for_markers(text)

    markers = [
        m for m in COMPLEX_ENTHYMEME_MARKERS
        if contains_term(t, m) or m in t
    ]

    if (
        ("censur" in t or "ridiculis" in t or "exclus" in t)
        and ("vérité" in t or "ouvrir les yeux" in t)
        and ("agir" in t or "nécessaire" in t)
    ):
        markers.append("vérité censurée → nécessité d’agir")

    if (
        ("système" in t or "médias" in t or "autorités" in t)
        and ("menti" in t or "manipulation" in t or "cache" in t)
        and ("donc" in t or "nécessaire" in t or "agir" in t)
    ):
        markers.append("système trompeur → action nécessaire")

    markers = unique_keep_order(markers)

    score = min(len(markers) * 0.20, 1.0)

    if score < 0.15:
        interpretation = "Aucun enthymème complexe notable détecté."
    elif score < 0.35:
        interpretation = "Le texte contient quelques raisonnements implicites."
    elif score < 0.60:
        interpretation = "Le texte repose partiellement sur des prémisses implicites enchaînées."
    else:
        interpretation = "Le discours repose fortement sur des enthymèmes complexes ou des prémisses cachées."

    return {
        "score": round(score, 3),
        "markers": markers,
        "interpretation": interpretation,
    }

# -----------------------------
# Auto-validation narrative
# -----------------------------

SELF_VALIDATING_NARRATIVE_MARKERS = [
    "si on nous critique",
    "cela prouve que",
    "c'est bien la preuve",
    "c’est bien la preuve",
    "on cherche à nous faire taire",
    "les médias censurent",
    "les autorités mentent",
    "ils ont peur de la vérité",
    "ouvrir les yeux",
    "ceux qui disent la vérité",
    "vérité dérange",
    "si cela est censuré",
    "la preuve qu'ils ont peur",
    "la preuve qu’ils ont peur",
    "on veut nous empêcher",
    "ridiculisés",
    "censurés",
]

def compute_self_validating_narrative(text: str):

    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": (
                "Aucune structure auto-validante détectée."
            )
        }

    t = normalize_text_for_markers(text)

    markers = []

    # -----------------------------
    # 1) Marqueurs directs
    # -----------------------------
    for m in SELF_VALIDATING_NARRATIVE_MARKERS:
        if contains_term(t, m) or m in t:
            markers.append(m)

    # -----------------------------
    # 2) Critique devient preuve
    # -----------------------------
    if (
        ("critique" in t or "attaqu" in t or "ridiculis" in t or "censur" in t)
        and (
            "preuve" in t
            or "cela montre" in t
            or "cela prouve" in t
        )
    ):
        markers.append("critique transformée en validation")

    # -----------------------------
    # 3) Opposition = confirmation
    # -----------------------------
    if (
        ("système" in t or "élites" in t or "médias" in t)
        and (
            "ont peur" in t
            or "veulent empêcher" in t
            or "cachent la vérité" in t
        )
    ):
        markers.append("opposition interprétée comme confirmation")

    # -----------------------------
    # 4) Boucle auto-référentielle
    # -----------------------------
    if (
        ("vérité" in t)
        and (
            "censure" in t
            or "silence" in t
            or "interdit" in t
        )
    ):
        markers.append("boucle narrative auto-validante")

    # -----------------------------
    # Nettoyage
    # -----------------------------
    markers = unique_keep_order(markers)

    # -----------------------------
    # Score
    # -----------------------------
    score = min(len(markers) * 0.20, 1.0)

    # -----------------------------
    # Interprétation
    # -----------------------------
    if score < 0.15:
        interpretation = (
            "Aucune structure auto-validante détectée."
        )

    elif score < 0.35:
        interpretation = (
            "Le texte contient quelques mécanismes d’auto-validation narrative."
        )

    elif score < 0.60:
        interpretation = (
            "Le discours transforme partiellement la contradiction "
            "ou la critique en validation implicite."
        )

    else:
        interpretation = (
            "Le discours repose fortement sur une logique "
            "auto-validante ou circulaire."
        )

    return {
        "score": round(score, 3),
        "markers": markers,
        "interpretation": interpretation,
    }
    
    
def detect_aristotelian_fallacies(text: str):
    petition = detect_petition_principii(text)
    descriptive_normative_confusion = detect_descriptive_normative_confusion(text)
    false_causality = detect_false_causality_basic(text)
    generalization = detect_hasty_generalization(text)
    vague_authority = detect_vague_authority_basic(text)
    false_dilemma = detect_false_dilemma(text)

    ad_hominem = detect_ad_hominem(text)
    ignorance = detect_argument_from_ignorance(text)
    slippery_slope = detect_slippery_slope(text)
    fear_appeal = detect_fear_appeal(text)
    false_analogy_strong = detect_false_analogy_strong(text)

    normative_qualification = detect_normative_qualification(text)
    ideological_premise = detect_ideological_premise(text)
    false_consensus_strong = detect_false_consensus_strong(text)
    argument_from_nature = detect_argument_from_nature(text)
    
    score = (
        petition["score"]
        + false_causality["score"]
        + generalization["score"]
        + vague_authority["score"]
        + false_dilemma["score"]
        + ad_hominem["score"]
        + ignorance["score"]
        + slippery_slope["score"]
        + fear_appeal["score"]
        + false_analogy_strong["score"]
        + normative_qualification["score"]
        + ideological_premise["score"]
        + false_consensus_strong["score"]
        + argument_from_nature["score"]
        + descriptive_normative_confusion["score"]
    ) / 15

    return {
        "score": round(score, 3),

        "petition": petition,
        "false_causality": false_causality,
        "generalization": generalization,
        "vague_authority": vague_authority,
        "false_dilemma": false_dilemma,

        "ad_hominem": ad_hominem,
        "ignorance": ignorance,
        "slippery_slope": slippery_slope,
        "fear_appeal": fear_appeal,
        "false_analogy_strong": false_analogy_strong,

        "normative_qualification": normative_qualification,
        "ideological_premise": ideological_premise,
        "false_consensus_strong": false_consensus_strong,
        "argument_from_nature": argument_from_nature,
        "descriptive_normative_confusion": descriptive_normative_confusion,
    }
    
    gravity = result.get("cognitive_gravity", 0)
    stability = result.get("cognitive_stability", round(1 - gravity, 3))
    
    regime = (
        result.get("brain_profile")
        or result.get("dominant_regime")
        or result.get("cognitive_regime")
        or "Non déterminé"
    )
    
    result["emotional_intensity_score"] = emotional_result["score"]
    result["emotional_intensity_markers"] = emotional_result["markers"]
    result["emotional_intensity_interpretation"] = emotional_result["interpretation"]

    argument_density_result = compute_argument_density(result.get("text", ""))

    result["argument_density_score"] = argument_density_result["score"]
    result["argument_density_label"] = argument_density_result["label"]
    result["argument_density_units"] = argument_density_result["units"]
    result["argument_density_markers"] = argument_density_result["markers"]
    result["argument_density_word_count"] = argument_density_result["word_count"]
    result["argument_density_interpretation"] = argument_density_result["interpretation"]

    G = result["G"]
    N = result["N"]
    D = result["D"]
    M = result["M"]
    ME = result["ME"]

    closure_raw = (D / (G + N)) if (G + N) > 0 else 2.0
    closure_gauge = clamp01(closure_raw / 1.5)

    IR = (
        result["normative_score"] * 1.2 +
        result["propaganda_score"] * 1.4 +
        result["emotional_intensity_score"] * 1.2 +
        result["certainty_score"] * 1.3 +
        result["false_consensus_score"] * 1.1 +
        result["binary_opposition_score"] * 1.1 +
        result["threat_amplification_score"] * 1.3 +
        result["vague_authority_score"] * 1.0
    ) / 9.6

    IL = (
        result["logic_confusion_score"] * 1.4 +
        result["causal_overreach_score"] * 1.3 +
        result["factual_overinterpretation_score"] * 1.3 +
        result["false_analogy_score"] * 1.1 +
        result["internal_dissonance_score"] * 1.2 +
        result["scientific_simulation_score"] * 1.0
    ) / 7.3

    IC = (
        result["premise_score"] * 1.2 +
        result["ideological_premise_score"] * 1.3 +
        result["semantic_shift_score"] * 1.2 +
        result["doxic_rigidity_score"] * 1.5 +
        result["narrative_overdetermination_score"] * 1.4 +
        closure_gauge * 1.6
    ) / 8.2

    strategic_index = clamp01(
        (ME / 20) * 0.40 +
        IR * 0.20 +
        IL * 0.20 +
        IC * 0.20
    )

    closure_index = clamp01(
        IC * 0.50 +
        (D / 10) * 0.30 +
        (1 - min((G + N) / 20, 1.0)) * 0.20
    )

    if strategic_index < 0.30 and closure_index < 0.35 and M > 0:
        profile = "Discours équilibré"
    elif strategic_index < 0.45 and closure_index >= 0.35 and M <= 3:
        profile = "Mécroyance probable"
    elif strategic_index >= 0.45 and strategic_index < 0.70 and IR >= 0.45:
        profile = "Manipulation rhétorique"
    elif strategic_index >= 0.70 and IC >= 0.50 and IL >= 0.45:
        profile = "Mensonge stratégique"
    else:
        profile = "Structure mixte ou ambiguë"

      
def analyze_claim(sentence: str) -> Claim:
    s = sentence.lower()

    has_number = bool(re.search(r"\d+", sentence))
    has_date = bool(
        re.search(
            r"\d{4}|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre",
            sentence,
            re.I,
        )
    )
    has_named_entity = bool(re.search(r"[A-Z][a-z]+ [A-Z][a-z]+|[A-Z]{2,}", sentence))
    has_source_cue = any(cue in s for cue in SOURCE_CUES)

    absolutism = sum(1 for word in ABSOLUTIST_WORDS if contains_term(s, word))
    emotional_charge = sum(1 for word in EMOTIONAL_WORDS if contains_term(s, word))

    claim_types = classify_claim_type(sentence)
    sentence_red_flags = compute_sentence_red_flags(sentence)
    aristotelian_type = detect_aristotelian_proposition(sentence)
    subject_term, predicate_term = extract_categorical_terms(sentence)

    # Vérifiabilité brute
    v_score = clamp(
        (has_number * 3) +
        (has_date * 4) +
        (has_named_entity * 2.5) +
        (has_source_cue * 3),
        0,
        20
    )

    # Risque rhétorique
    r_score = clamp((absolutism * 7) + (emotional_charge * 7), 0, 20)

    # Pénalité normative
    normative_hits = sum(
        1 for term in QUALIFICATIONS_NORMATIVES
        if contains_term(s, term)
    )

    judgment_hits = sum(
        1 for term in JUDGMENT_MARKERS
        if contains_term(s, term)
    )

    premise_hits = sum(
        1 for term in IDEOLOGICAL_PREMISE_MARKERS
        if contains_term(s, term)
    )

    normative_penalty = min(
        normative_hits * 2.5 +
        judgment_hits * 1.5 +
        premise_hits * 1.5,
        10
    )

    # On ne pénalise plus de la même manière les énoncés
    # normatifs / interprétatifs / testimoniaux
    if not any(t in claim_types for t in ["normative", "interpretative", "testimonial"]):
        v_score = clamp(v_score - normative_penalty, 0, 20)

    # Correctif petites phrases non mensongères
    short_adjustment, epistemic_note = small_claim_epistemic_adjustment(
        sentence,
        claim_types,
        sentence_red_flags,
        absolutism
    )

    # Bonus de sobriété factuelle
    sobriety_bonus, sobriety_note = compute_factual_sobriety_bonus(
        sentence,
        claim_types,
        r_score,
        sentence_red_flags
    )

    total_adjustment = round(short_adjustment + sobriety_bonus, 2)
    v_score = clamp(v_score + total_adjustment, 0, 20)

    if epistemic_note and sobriety_note:
        epistemic_note = epistemic_note + " " + sobriety_note
    elif sobriety_note:
        epistemic_note = sobriety_note

    if v_score < 5:
        status = T["very_fragile"]
    elif v_score < 12:
        status = T["to_verify"]
    else:
        status = T["rather_verifiable"]

    return Claim(
        text=sentence,
        has_number=has_number,
        has_date=has_date,
        has_named_entity=has_named_entity,
        has_source_cue=has_source_cue,
        absolutism=absolutism,
        emotional_charge=emotional_charge,
        verifiability=v_score,
        risk=r_score,
        status=status,
        claim_types=claim_types,
        epistemic_note=epistemic_note,
        short_adjustment=total_adjustment,
        aristotelian_type=aristotelian_type,
        subject_term=subject_term,
        predicate_term=predicate_term,
        middle_term_candidate=None,
    )

def compute_red_flag_penalties(metrics: dict) -> dict:
    red_flags = []
    credibility_penalty = 0.0
    lie_boost = 0.0

    def add_flag(name, cred, lie, reason):
        nonlocal credibility_penalty, lie_boost
        red_flags.append({
            "name": name,
            "cred_penalty": cred,
            "lie_boost": lie,
            "reason": reason,
        })
        credibility_penalty += cred
        lie_boost += lie

    # -----------------------------
    # Pseudo-savoir élevé
    # -----------------------------
    pseudo_savoir = metrics.get("drift_pseudo_savoir", 0)

    if pseudo_savoir > 5:
        penalty = round((pseudo_savoir - 5) * 0.5, 2)
        add_flag(
            "Pseudo-savoir élevé",
            penalty,
            0.3,
            "Accumulation de savoirs mal intégrés ou mal compris."
        )

    if metrics["G"] < 2 and metrics["vague_authority_score"] >= 0.30:
        add_flag(
            "Autorité sans ancrage",
            1.8,
            0.8,
            "Le texte invoque des experts ou études sans base documentaire suffisante."
        )

    if metrics["certainty_score"] >= 0.35 and metrics["doxic_rigidity_score"] >= 0.35:
        add_flag(
            "Certitude saturée",
            1.6,
            1.2,
            "Le discours affirme plus qu’il ne démontre."
        )

    if metrics["causal_overreach_score"] >= 0.35 and metrics["factual_overinterpretation_score"] >= 0.35:
        add_flag(
            "Causalité surinterprétée",
            1.8,
            1.4,
            "Des conclusions causales sont tirées trop vite."
        )

    if metrics["propaganda_score"] >= 0.40 and metrics["emotional_intensity_score"] >= 0.35:
        add_flag(
            "Pression émotionnelle orientée",
            1.5,
            1.5,
            "La charge émotionnelle soutient une structure orientée."
        )

    if metrics["false_consensus_score"] >= 0.30 and metrics["binary_opposition_score"] >= 0.30:
        add_flag(
            "Polarisation artificielle",
            1.2,
            1.3,
            "Le texte fabrique des camps et un consensus supposé."
        )

    if metrics["internal_dissonance_score"] >= 0.30:
        add_flag(
            "Contradiction interne",
            2.0,
            1.8,
            "Le texte contient des tensions ou contradictions internes."
        )

    if metrics["semantic_shift_score"] >= 0.30 and metrics["ideological_premise_score"] >= 0.30:
        add_flag(
            "Recadrage idéologique",
            1.4,
            1.1,
            "Le lexique oriente l’interprétation en amont de la preuve."
        )

    if (
        metrics["vague_authority_score"] >= 0.30
        and metrics["factual_overinterpretation_score"] >= 0.30
        and metrics["certainty_score"] >= 0.20
    ):
        add_flag(
            "Projection spectaculaire fragile",
            2.2,
            1.5,
            "Le texte avance une projection forte à partir d’un ancrage documentaire insuffisant."
        )

    return {
        "flags": red_flags,
        "credibility_penalty": round(min(credibility_penalty, 8.0), 2),
        "lie_boost": round(min(lie_boost, 6.0), 2),
    }
# -----------------------------
# compute cognitive drifts
# -----------------------------
def compute_cognitive_drifts(G, N, D):
    M = (G + N) - D

    drift_mecroyance = max(0, -M)
    drift_pseudo_savoir = max(0, (G + D) - N)
    drift_intuition_dogmatique = max(0, (N + D) - G)

    dominant_value = max(
        drift_mecroyance,
        drift_pseudo_savoir,
        drift_intuition_dogmatique
    )

    average_value = (
        drift_mecroyance +
        drift_pseudo_savoir +
        drift_intuition_dogmatique
    ) / 3

    global_drift = round(dominant_value * 0.6 + average_value * 0.4, 2)

    values = {
        "mecroyance": round(drift_mecroyance, 2),
        "pseudo_savoir": round(drift_pseudo_savoir, 2),
        "intuition_dogmatique": round(drift_intuition_dogmatique, 2),
    }

    dominant = max(values, key=values.get)

    if dominant == "mecroyance":
        interpretation = "Dérive dominante : mécroyance."
    elif dominant == "pseudo_savoir":
        interpretation = "Dérive dominante : pseudo-savoir."
    else:
        interpretation = "Dérive dominante : intuition dogmatique."

    return {
        "drift_mecroyance": values["mecroyance"],
        "drift_pseudo_savoir": values["pseudo_savoir"],
        "drift_intuition_dogmatique": values["intuition_dogmatique"],
        "global_cognitive_drift": global_drift,
        "cognitive_drift_interpretation": interpretation,
    }


def classify_cognitive_regime(result: dict) -> dict:
    M = result["M"]
    ME = result["ME"]
    rp = result["rhetorical_pressure"]

    if ME > 2 and rp > 0.5:
        regime = "Manipulation stratégique"
    elif result["drift_pseudo_savoir"] > result["drift_mecroyance"]:
        regime = "Pseudo-savoir"
    else:
        regime = "Mécroyance"

    result["cognitive_regime"] = regime
    return result


def compute_cognitive_gravity(result):
    lie = min(1, max(0, result.get("lie_gauge", 0)))
    rhetoric = min(1, max(0, result.get("rhetorical_pressure", 0)))
    propaganda = min(1, max(0, result.get("propaganda_score", 0) / 10))
    dissonance = min(1, max(0, result.get("factual_dissonance", 0)))
    closure = min(1, max(0, result.get("cognitive_closure", 0) / 10))

    hard_fact_inverse = 1 - min(1, max(0, result.get("hard_fact_score", 0) / 20))

    gravity = (
        lie * 0.25 +
        rhetoric * 0.20 +
        propaganda * 0.20 +
        dissonance * 0.20 +
        closure * 0.10 +
        hard_fact_inverse * 0.05
    )

    return round(min(1, max(0, gravity)), 3)

def compute_global_penalties(result: dict) -> dict:
    """
    Agrège les fragilités déjà détectées.
    Ne modifie pas le noyau G-N-D-M.
    """

    red_flags_count = len(result.get("red_flags", []))

    penalty = 0.0

    # 1) Red flags généraux
    penalty += min(red_flags_count * 0.25, 2.0)

    # 2) Dérives discursives déjà calculées
    penalty += result.get("normative_score", 0) * 0.6
    penalty += result.get("premise_score", 0) * 0.7
    penalty += result.get("propaganda_score", 0) * 0.8
    penalty += result.get("logic_confusion_score", 0) * 0.7
    penalty += result.get("scientific_simulation_score", 0) * 0.6
    
    # 3) Sophismes simples
    penalty += result.get("petition_score", 0) * 0.5
    penalty += result.get("false_causality_basic_score", 0) * 0.6
    penalty += result.get("hasty_generalization_score", 0) * 0.5
    penalty += result.get("false_dilemma_score", 0) * 0.5
    
    # 4) Verrouillage / manipulation
    penalty += result.get("doxic_rigidity_score", 0) * 0.7
    penalty += result.get("narrative_overdetermination_score", 0) * 0.6
    penalty += result.get("moral_polarization_score", 0) * 0.6
    penalty += result.get("strategic_simplification_score", 0) * 0.6
    penalty += result.get("argument_asymmetry_score", 0) * 0.5
    
    # Plafond plus doux
    penalty = round(min(penalty, 4.0), 2)

    if penalty < 1:
        label = "Faible"
        interpretation = "Les fragilités détectées ne modifient que faiblement la crédibilité globale."
    elif penalty < 2.5:
        label = "Modérée"
        interpretation = "Plusieurs fragilités discursives diminuent partiellement la confiance accordable au texte."
    elif penalty < 4:
        label = "Élevée"
        interpretation = "Le texte accumule assez de signaux problématiques pour réduire nettement son score final."
    else:
        label = "Critique"
        interpretation = "La structure discursive présente une forte accumulation de signaux de fermeture, de manipulation ou de raisonnement fragile."

    return {
        "penalty_index": penalty,
        "penalty_label": label,
        "penalty_interpretation": interpretation,
        "red_flags_penalty_count": red_flags_count,
    }

def compute_secondary_alert_pressure(result: dict) -> float:
    weighted_signals = [
        result.get("propaganda_score", 0) * 1.4,
        result.get("argument_asymmetry_score", 0) * 1.2,
        result.get("emotional_intensity_score", 0) * 1.0,
        result.get("normative_score", 0) * 1.1,
        result.get("premise_score", 0) * 1.1,
        result.get("coherence_trompeuse_score", 0) * 1.3,
        result.get("logic_confusion_score", 0) * 1.0,
        result.get("scientific_simulation_score", 0) * 1.0,
        result.get("hasty_generalization_score", 0) * 1.0,
        result.get("false_dilemma_score", 0) * 0.9,
        result.get("dissonance_score", 0) * 1.2,
    ]

    total_weight = (
        1.4 + 1.2 + 1.0 + 1.1 + 1.1 +
        1.3 + 1.0 + 1.0 + 1.0 + 0.9 + 1.2
    )

    pressure = sum(weighted_signals) / total_weight

    return round(min(pressure, 1.0), 3)

def compute_brain_indices(result: dict) -> dict:
    """
    Cerveau DOXA v2 — agrégation générale des jauges.
    Calcule gravité, stabilité et profil dominant.
    """

    def clamp01(x):
        return max(0.0, min(1.0, x))

    def g(key, default=0.0):
        return result.get(key, default) or 0.0

    # -----------------------------
    # 1) Noyau cognitif
    # -----------------------------
    M = g("M")
    ME = g("ME")
    hard_fact = g("hard_fact_score", 10)

    fact_fragility = 1 - clamp01(hard_fact / 20)
    lie_pressure = clamp01(g("lie_gauge", ME / 20))

    closure = clamp01(
        max(
            g("cognitive_closure") / 10 if g("cognitive_closure") > 1 else g("cognitive_closure"),
            g("closure_index")
        )
    )

    core_pressure = clamp01(
        fact_fragility * 0.35 +
        lie_pressure * 0.35 +
        closure * 0.30
    )

    # -----------------------------
    # 2) Pression discursive
    # -----------------------------
    propaganda = g("propaganda_score")
    if propaganda > 1:
        propaganda = propaganda / 10
    
    certainty = g("strong_certainty_score")
    if certainty > 1:
        certainty = certainty / 100
    
    narrative_propaganda = g("narrative_propaganda_score")
    if narrative_propaganda > 1:
        narrative_propaganda = narrative_propaganda / 100
    
    discursive_pressure = clamp01(
        g("rhetorical_pressure") * 0.30 +
        propaganda * 0.25 +
        g("emotional_intensity_score") * 0.15 +
        certainty * 0.15 +
        narrative_propaganda * 0.15
    )

    # -----------------------------
    # 3) Raisonnement / logique
    # -----------------------------
    reasoning_pressure = clamp01(
        g("internal_dissonance_score") * 0.15 +
        g("misleading_coherence_score") * 0.20 +
        g("advanced_misleading_coherence_score") * 0.15 +
        g("logic_confusion_score") * 0.12 +
        g("causal_overreach_score") * 0.12 +
        g("false_analogy_score") * 0.12 +
        g("logical_jump_score") * 0.07 +
        g("cherry_picking_score") * 0.07
    )

    # -----------------------------
    # 4) Idéologie / cadrage
    # -----------------------------
    ideological_pressure = clamp01(
        g("premise_score") * 0.15 +
        g("ideological_premise_score") * 0.12 +
        g("semantic_shift_score") * 0.12 +
        g("false_consensus_score") * 0.10 +
        g("false_consensus_strong_score") * 0.10 +
        g("binary_opposition_score") * 0.10 +
        g("moral_polarization_score") * 0.08 +
        g("victimization_score") * 0.06 +
        g("narrative_overdetermination_score") * 0.07 +
        g("normative_qualification_score") * 0.10 +
        g("scientificity_rhetoric_score") * 0.10
    )

    # -----------------------------
    # 5) Réalité / statistiques
    # -----------------------------
    real_anchor_score = g("real_anchor_score", 10)
    weak_anchor = 1 - clamp01(real_anchor_score / 20)

    reality_pressure = clamp01(
        weak_anchor * 0.40 +
        g("statistical_manipulation_score") * 0.25 +
        g("misleading_comparison_score") * 0.15 +
        g("missing_reference_score") * 0.10 +
        g("data_without_reference_score") * 0.10
    )

    # -----------------------------
    # 6) Bonus compensateur
    # -----------------------------
    bonus = clamp01(g("cognitive_bonus"))

    # -----------------------------
    # Gravité finale
    # -----------------------------
    gravity = clamp01(
        core_pressure * 0.28 +
        discursive_pressure * 0.22 +
        reasoning_pressure * 0.20 +
        ideological_pressure * 0.18 +
        reality_pressure * 0.12
        - bonus * 0.12
    )

    stability = clamp01(1 - gravity)

    # -----------------------------
    # Profil dominant
    # -----------------------------
    pressures = {
        "Pression cognitive": core_pressure,
        "Pression discursive": discursive_pressure,
        "Fragilité logique": reasoning_pressure,
        "Cadrage idéologique": ideological_pressure,
        "Faible ancrage réel": reality_pressure,
    }

    dominant_family = max(pressures, key=pressures.get)

    if gravity < 0.20:
        profile = "Discours équilibré"
    elif dominant_family == "Pression discursive" and discursive_pressure > 0.45:
        profile = "Manipulation rhétorique"
    elif dominant_family == "Fragilité logique" and reasoning_pressure > 0.45:
        profile = "Raisonnement instable"
    elif dominant_family == "Cadrage idéologique" and ideological_pressure > 0.45:
        profile = "Cadrage idéologique dominant"
    elif dominant_family == "Faible ancrage réel" and reality_pressure > 0.45:
        profile = "Cohérence autoporteuse fragile"
    elif ME > M:
        profile = "Mensonge stratégique possible"
    elif M >= ME:
        profile = "Mécroyance dominante"
    else:
        profile = "Structure mixte ou ambiguë"

    return {
        "core_pressure": round(core_pressure, 3),
        "discursive_pressure_brain": round(discursive_pressure, 3),
        "reasoning_pressure_brain": round(reasoning_pressure, 3),
        "ideological_pressure_brain": round(ideological_pressure, 3),
        "reality_pressure_brain": round(reality_pressure, 3),
        "brain_dominant_family": dominant_family,

        "gravity": round(gravity, 3),
        "stability": round(stability, 3),
        "cognitive_gravity": round(gravity, 3),
        "cognitive_stability": round(stability, 3),

        "brain_profile": profile,
        "dominant_regime": profile,
    }

# -----------------------------
# Indice de baratinage
# -----------------------------
def compute_baratinage_score(result):
    """
    Estime dans quelle mesure un discours produit
    une impression de maîtrise supérieure
    à ce que sa démonstration explicite semble soutenir.
    """

    # Facteurs augmentant l'indice
    CF = result.get("strong_certainty_score", 0)
    CE = result.get("deceptive_coherence", 0)
    ACE = result.get("advanced_deceptive_coherence_score", 0)
    RP = result.get("rhetorical_pressure", 0)
    NP = result.get("narrative_pressure_score", 0)
    PI = result.get("premise_score", 0)
    CS = result.get("certainty_score", 0)

    # Facteurs réduisant l'indice
    HF = result.get("hard_fact_score", 0) / 20
    AR = result.get("bonus_anchor", 0)
    RV = result.get("bonus_revisability", 0)
    BC = result.get("bonus_coherence", 0)
    AS = result.get("argument_support_count", 0) * 0.08
    AN = result.get("argument_nuances_count", 0) * 0.06

    # -----------------------------
    # Calcul heuristique principal
    # -----------------------------
    raw_heuristic = (
        CF
        + CE
        + ACE
        + RP
        + NP
        + PI
        + CS
    ) - (
        HF
        + AR
        + RV
        + BC
        + AS
        + AN
    )

    # -----------------------------
    # Modulateur DOXA léger
    # IB ≈ (G + 2D) − N
    # -----------------------------
    G = HF

    D = (
        result.get("strong_certainty_score", 0)
        + result.get("certainty_score", 0)
    ) / 2

    N = (
        result.get("bonus_anchor", 0)
        + result.get("bonus_revisability", 0)
        + result.get("bonus_coherence", 0)
    ) / 3

    doxa_baratinage = (G + (2 * D)) - N

    # Poids volontairement faible
    raw = raw_heuristic + (doxa_baratinage * 0.15)

    # Normalisation
    score = max(0.0, min(raw / 6, 1.0))

    # Interprétation
    if score < 0.15:
        label = "Faible"
        color = "#22c55e"
        interpretation = (
            "La démonstration paraît dominer l’effet discursif."
        )

    elif score < 0.35:
        label = "Modéré"
        color = "#eab308"
        interpretation = (
            "Le discours produit une certaine impression de maîtrise, "
            "mais celle-ci reste partiellement soutenue."
        )

    elif score < 0.65:
        label = "Élevé"
        color = "#f97316"
        interpretation = (
            "L’impression de maîtrise semble dépasser la démonstration visible."
        )

    else:
        label = "Très élevé"
        color = "#dc2626"
        interpretation = (
            "Le discours paraît produire une forte impression de maîtrise "
            "mal soutenue par la démonstration explicite."
        )

    return {
        "baratinage_score": round(score, 3),
        "baratinage_raw": round(raw, 3),
        "baratinage_raw_heuristic": round(raw_heuristic, 3),
        "baratinage_doxa_modulator": round(doxa_baratinage, 3),
        "baratinage_label": label,
        "baratinage_color": color,
        "baratinage_interpretation": interpretation,
    }

# -----------------------------
# Effet placebo étendu
# -----------------------------
def compute_extended_placebo_effect(result):
    """
    Mesure dans quelle mesure un vécu,
    une impression ou une cohérence perçue
    devient une preuve auto-validante.
    """

    # -----------------------------
    # Variables théoriques
    # M = (N + 2D) - G
    # -----------------------------

    EX = max(
        result.get("factual_overinterpretation_score", 0),
        result.get("self_validating_score", 0),
        result.get("false_causality_basic_score", 0),
        result.get("causal_overreach_score", 0),
    )
    
    G = result.get("hard_fact_score", 0) / 20
    
    D = (
        result.get("strong_certainty_score", 0)
        + result.get("certainty_score", 0)
    ) / 2
    
    N = (
        result.get("bonus_anchor", 0)
        + result.get("bonus_coherence", 0)
        + result.get("bonus_revisability", 0)
    ) / 3
    
    theoretical_raw = ((N + (2 * D)) - G) * EX
    theoretical_score = max(0.0, min(1.0, theoretical_raw))

    # -----------------------------
    # Facteurs augmentant
    # -----------------------------

    CF = result.get("strong_certainty_score", 0)

    PI = result.get("premise_score", 0)

    CT = result.get("deceptive_coherence", 0)

    ACT = result.get(
        "advanced_deceptive_coherence_score",
        0
    )

    SC = max(
        result.get("causal_overreach_score", 0),
        result.get("false_causality_basic_score", 0)
    )

    ND = (
        result.get("narrative_overdetermination_score", 0)
        + result.get("narrative_pressure_score", 0)
    ) / 2

    # -----------------------------
    # Facteurs réduisant
    # -----------------------------

    AR = result.get("bonus_anchor", 0)

    RV = result.get("bonus_revisability", 0)

    BC = result.get("bonus_coherence", 0)

    CA = (
        result.get("argument_counterweight_count", 0)
        * 0.08
    )

    HF = result.get("hard_fact_score", 0) / 20

    heuristic_raw = (
        CF
        + PI
        + CT
        + ACT
        + SC
        + ND
    ) - (
        AR
        + RV
        + BC
        + CA
        + HF
    )

    heuristic_score = max(
        0.0,
        min(1.0, (heuristic_raw / 4) * max(EX, 0.25))
    )

    # -----------------------------
    # Fusion
    # -----------------------------

    final_score = (
        (theoretical_score * 0.60)
        +
        (heuristic_score * 0.40)
    )

    final_score = max(
        0.0,
        min(1.0, final_score)
    )

    # -----------------------------
    # Interprétation
    # -----------------------------

    if final_score < 0.25:

        label = "Faible"
        color = "#16a34a"

        interpretation = (
            "Le discours ne semble pas transformer fortement "
            "le vécu en preuve auto-validante."
        )

    elif final_score < 0.50:

        label = "Modéré"
        color = "#ca8a04"

        interpretation = (
            "Le discours présente une tendance limitée "
            "à valider une croyance par le ressenti."
        )

    elif final_score < 0.75:

        label = "Élevé"
        color = "#f97316"

        interpretation = (
            "Le discours semble convertir "
            "l'expérience en preuve subjective."
        )

    else:

        label = "Très élevé"
        color = "#dc2626"

        interpretation = (
            "Le discours paraît transformer "
            "le ressenti en certitude auto-validée."
        )

    return {
        "extended_placebo_raw": round(theoretical_raw, 2),
        "extended_placebo_theoretical_score": round(theoretical_score, 3),
        "extended_placebo_heuristic_score": round(heuristic_score, 3),
        "extended_placebo_score": round(final_score, 3),
        "extended_placebo_label": label,
        "extended_placebo_color": color,
        "extended_placebo_interpretation": interpretation,
    }
# -----------------------------
# Indice d’omission stratégique
# -----------------------------
def compute_omission_score(result):
    """
    Estime dans quelle mesure le discours semble
    sélectionner certains éléments au détriment
    du contexte utile à l’interprétation.
    """

    # Facteurs augmentant l'indice
    CP = result.get("cherry_picking_score", 0)
    
    DR = result.get("missing_reference_score", 0)
    
    PI = result.get("premise_score", 0)
    
    AA = result.get("argument_asymmetry_score", 0)
    
    CF = result.get("strong_certainty_score", 0)
    
    CC = result.get(
        "cognitive_closure_score",
        result.get("closure_score", 0)
    )
    
    MS = result.get("statistical_manipulation_score", 0)
    
    # Facteurs réduisant l'indice
    LM = result.get("limits_score", 0)
    
    RV = (
        result.get("revisability_score", 0)
        + result.get("bonus_revisability", 0)
    )
    
    AR = (
        result.get("reality_anchor_score", 0)
        + result.get("bonus_anchor", 0)
    )
    
    PX = result.get("precision_score", 0)
    
    CA = result.get("argument_counterweight_count", 0)

# -----------------------------
# Calcul heuristique principal
# -----------------------------
    raw_heuristic = (
        CP
        + (DR * 1.5)
        + PI
        + AA
        + CF
        + CC
        + (MS * 0.35)
    ) - (
        LM
        + RV
        + AR
        + PX
        + CA
    )

    # -----------------------------
    # Modulateur DOXA léger
    # MO ≈ (G + D) − 2N
    # -----------------------------

    G = (
        result.get("hard_fact_score", 0)
        + AR
    ) / 2

    D = (
        result.get("strong_certainty_score", 0)
        + result.get("cognitive_closure_score", 0)
    ) / 2

    N = (
        result.get("reality_anchor_score", 0)
        + result.get("revisability_score", 0)
    ) / 2

    doxa_omission = (G + D) - (2 * N)

    # Poids volontairement faible
    raw = raw_heuristic + (doxa_omission * 0.15)

    # Normalisation
    score = max(0.0, min(raw / 12, 1.0))

    # Interprétation
    if score < 0.15:

        label = "Faible"
        color = "#22c55e"

        interpretation = (
            "Le contexte présenté paraît relativement complet."
        )

    elif score < 0.50:

        label = "Modéré"
        color = "#eab308"

        interpretation = (
            "Quelques éléments semblent peu contextualisés."
        )

    elif score < 0.75:

        label = "Élevé"
        color = "#f97316"

        interpretation = (
            "Le discours paraît sélectionner certains éléments "
            "au détriment du contexte."
        )

    else:

        label = "Très élevé"
        color = "#dc2626"

        interpretation = (
            "Le discours semble fortement orienté "
            "par sélection du contexte."
        )

    return {
        "omission_score": round(score, 3),
        "omission_raw": round(raw, 3),
        "omission_raw_heuristic": round(raw_heuristic, 3),
        "omission_doxa_modulator": round(doxa_omission, 3),
        "omission_label": label,
        "omission_color": color,
        "omission_interpretation": interpretation,
    }

def compute_doxa_brain(result: dict) -> dict:
    """
    Synthèse finale du cerveau DOXA.
    Habillage final des indices déjà calculés.
    """
    
    gravity = result.get("cognitive_gravity", result.get("gravity", 0))
    gravity = max(0, min(gravity, 1))
    
    stability = result.get(
        "cognitive_stability",
        result.get("stability", 1 - gravity)
    )
    stability = max(0, min(stability, 1))

    M = result.get("M", 0)
    ME = result.get("ME", 0)
    hard_fact = result.get("hard_fact_score", 0)

    regime = result.get(
        "dominant_regime",
        "Non déterminé"
    )

    if gravity < 0.20:
        brain_state = "Stable"
        verdict = "Discours globalement stable"
        advice = "Le discours présente peu de signaux de dérive cognitive."
    elif gravity < 0.40:
        brain_state = "Sous tension"
        verdict = "Discours légèrement fragilisé"
        advice = "Quelques tensions existent : vérifier les sources et les prémisses."
    elif gravity < 0.60:
        brain_state = "Instable"
        verdict = "Discours cognitivement instable"
        advice = "La cohérence doit être recoupée avec les faits et les sources."
    elif gravity < 0.80:
        brain_state = "Critique"
        verdict = "Discours fortement problématique"
        advice = "Accumulation de signaux rhétoriques, factuels ou cognitifs préoccupants."
    else:
        brain_state = "Alerte maximale"
        verdict = "Discours à très forte gravité cognitive"
        advice = "Forte convergence de fermeture, manipulation ou désalignement cognitif."

    return {
        "brain_state": brain_state,
        "brain_verdict": verdict,
        "brain_advice": advice,
    
        # conserver les valeurs déjà calculées
        "gravity": round(gravity, 3),
        "stability": round(stability, 3),
    
        "cognitive_gravity": round(gravity, 3),
        "cognitive_stability": round(stability, 3),
    
        "dominant_regime": regime,
    
        # préserver familles DOXA
        "core_pressure":
            result.get("core_pressure", 0),
    
        "discursive_pressure_brain":
            result.get(
                "discursive_pressure_brain",
                0
            ),
    
        "reasoning_pressure_brain":
            result.get(
                "reasoning_pressure_brain",
                0
            ),
    
        "ideological_pressure_brain":
            result.get(
                "ideological_pressure_brain",
                0
            ),
    
        "reality_pressure_brain":
            result.get(
                "reality_pressure_brain",
                0
            ),
    
        "brain_dominant_family":
            result.get(
                "brain_dominant_family",
                "Non déterminée"
            ),
    
        "brain_summary": None
    }

# -----------------------------
# Pénalités mécroyance
# -----------------------------
def compute_mecroyance_penalties(result: dict) -> dict:
    penalty = 0.0
    lie_boost = 0.0
    flags = []

    def add_flag(name, cred, lie, reason):
        nonlocal penalty, lie_boost
        flags.append({
            "name": name,
            "cred_penalty": cred,
            "lie_boost": lie,
            "reason": reason,
        })
        penalty += cred
        lie_boost += lie

    pseudo = result.get("drift_pseudo_savoir", 0)
    intuition = result.get("drift_intuition_dogmatique", 0)
    mecroyance = result.get("drift_mecroyance", 0)

    if pseudo >= 3:
        add_flag(
            "Pseudo-savoir élevé",
            min((pseudo - 2) * 0.35, 2.0),
            0.4,
            "Le texte accumule des éléments de savoir insuffisamment intégrés."
        )

    if intuition >= 3:
        add_flag(
            "Intuition dogmatique élevée",
            min((intuition - 2) * 0.30, 1.8),
            0.3,
            "Le texte présente une conviction forte avec base documentaire limitée."
        )

    if mecroyance >= 3:
        add_flag(
            "Mécroyance structurelle",
            min((mecroyance - 2) * 0.40, 2.2),
            0.5,
            "La certitude dépasse le savoir articulé et la compréhension intégrée."
        )

    return {
        "flags": flags,
        "credibility_penalty": round(min(penalty, 4.0), 2),
        "lie_boost": round(min(lie_boost, 2.0), 2),
    }

def compute_deceptive_coherence(G, N, D, rhetorical_pressure, propaganda_score, hard_fact_score, text_length):
    """
    Détecte un texte apparemment cohérent mais fragile ou orienté.
    """

    coherence = min((G + N) / 20, 1)
    fragility = min((D / 10) + (1 - hard_fact_score / 20), 1)

    deceptive = (
        0.35 * coherence +
        0.25 * rhetorical_pressure +
        0.25 * propaganda_score +
        0.15 * fragility
    )

    length_factor = min(text_length / 250, 1)
    deceptive *= length_factor

    deceptive = min(max(round(deceptive, 3), 0), 1)

    if deceptive < 0.25:
        label = "Faible"
    elif deceptive < 0.50:
        label = "Modérée"
    elif deceptive < 0.75:
        label = "Élevée"
    else:
        label = "Très élevée"

    return deceptive, label

# =========================================================
# 🎨 Étalonnage visuel unifié des jauges
# =========================================================
def normalize_display_value(value: float) -> float:
    """Ramène une valeur 0–1 ou 0–20 vers 0–1."""
    if value is None:
        return 0.0
    return value / 20 if value > 1 else value


def color_scale_risk(value: float) -> tuple[str, str]:
    v = normalize_display_value(value)

    if v < 0.25:
        return "#16a34a", "🟢 Faible"
    elif v < 0.50:
        return "#84cc16", "🟡 Modéré"
    elif v < 0.75:
        return "#f97316", "🟠 Élevé"
    else:
        return "#dc2626", "🔴 Critique"

def color_scale_quality(value: float) -> tuple[str, str]:
    v = normalize_display_value(value)

    if v < 0.25:
        return "#dc2626", "🔴 Faible"
    elif v < 0.50:
        return "#f97316", "🟠 Fragile"
    elif v < 0.75:
        return "#ca8a04", "🟡 Correct"
    else:
        return "#16a34a", "🟢 Robuste"
        
def color_scale_warning_risk(value: float) -> tuple[str, str]:
    """
    Pour les jauges de risque sensible :
    même faible, le signal reste une vigilance, pas une structure saine.
    """
    v = normalize_display_value(value)

    if v < 0.25:
        return "#ca8a04", "🟡 Faible"
    elif v < 0.50:
        return "#f97316", "🟠 Modéré"
    elif v < 0.75:
        return "#ea580c", "🟠 Élevé"
    else:
        return "#dc2626", "🔴 Critique"

def interpret_generic_risk_gauge(label: str, value: float) -> str:
    v = normalize_display_value(value)
    color, level = color_scale_risk(v)
    return f"<b style='color:{color}'>{label}</b> — {level} ({round(v * 100, 1)}%)"

def interpret_generic_quality_gauge(label: str, value: float) -> str:
    v = normalize_display_value(value)
    color, level = color_scale_quality(v)
    return f"<b style='color:{color}'>{label}</b> — {level} ({round(v * 100, 1)}%)"

def interpret_warning_risk_gauge(label: str, value: float) -> str:
    v = normalize_display_value(value)
    color, level = color_scale_warning_risk(v)
    return f"<b style='color:{color}'>{label}</b> — {level} ({round(v * 100, 1)}%)"

# -------------------------------------------------
# Pénalité des jauges affichées
# -------------------------------------------------
def compute_display_gauge_penalty(result: dict) -> float:

    gauges = {
        "normative_score": 0.6,
        "premise_score": 0.7,
        "logic_confusion_score": 0.9,
        "aristotelian_fallacies_score": 1.0,
        "scientific_simulation_score": 0.8,
        "cherry_picking_score": 1.0,
        "false_analogy_score": 0.7,
        "normative_saturation_score": 0.8,
        "narrative_overdetermination_score": 0.7,
        "victimization_score": 0.6,
        "moral_polarization_score": 0.7,
        "strategic_simplification_score": 0.8,
        "frame_shift_score": 0.6,
        "argument_asymmetry_score": 0.7,
        "deceptive_coherence": 1.2,
    }

    penalty = 0.0
    details = []

    for key, weight in gauges.items():

        value = result.get(key, 0)

        if value is None:
            continue

        v = normalize_display_value(value)

        if v >= 0.25:

            p = round(v * weight, 2)

            penalty += p

            details.append({
                "gauge": key,
                "score": round(v, 3),
                "weight": weight,
                "penalty": p,
            })

    result["display_gauge_penalty_details"] = details

    return round(min(penalty, 5.0), 2)

# -----------------------------
# Dérive cognitive
# -----------------------------
def interpret_cognitive_drift(value: float):
    v = normalize_display_value(value)
    color, label = color_scale_risk(v)

    if v < 0.25:
        msg = "Stabilité cognitive élevée."
    elif v < 0.50:
        msg = "Certaines dérives perceptibles."
    elif v < 0.75:
        msg = "Tendance nette à la mécroyance ou au biais confirmatoire."
    else:
        msg = "Dérive cognitive forte : fermeture sur ses propres certitudes."

    return color, label, msg

def count_marker_occurrences(text, markers):
    t = text.lower()
    return sum(t.count(marker.lower()) for marker in markers)


def normalize_score(value, max_value=10):
    if max_value <= 0:
        return 0
    return round(min(value / max_value, 1), 3)


def label_level(score):
    if score < 0.25:
        return "Faible"
    elif score < 0.50:
        return "Modérée"
    elif score < 0.75:
        return "Élevée"
    else:
        return "Très élevée"

def compute_narrative_pressure(text):
    sentences = max(len(re.split(r"[.!?]+", text)), 1)
    markers = count_marker_occurrences(text, NARRATIVE_PRESSURE_MARKERS)

    score = min((markers / sentences) * 2.5, 1)

    return {
        "score": round(score, 3),
        "label": label_level(score),
        "markers": markers,
        "interpretation": "Le texte exerce une pression vers une conclusion." if score >= 0.4 else "Pression narrative limitée."
    }

def compute_logical_jump(text):
    conclusions = count_marker_occurrences(text, CONCLUSION_MARKERS)
    reasons = count_marker_occurrences(text, REASON_MARKERS)

    raw = max(conclusions - reasons, 0)
    score = min(raw / max(conclusions, 1), 1)

    return {
        "score": round(score, 3),
        "label": label_level(score),
        "conclusions": conclusions,
        "reasons": reasons,
        "interpretation": "Conclusion possiblement insuffisamment démontrée." if score >= 0.4 else "Enchaînement logique relativement progressif."
    }

def compute_argument_asymmetry(text):
    assertions = count_marker_occurrences(text, ASSERTION_MARKERS)
    nuances = count_marker_occurrences(text, NUANCE_MARKERS)

    raw = assertions / max(nuances + 1, 1)
    score = min(raw / 8, 1)

    return {
        "score": round(score, 3),
        "label": label_level(score),
        "assertions": assertions,
        "nuances": nuances,
        "interpretation": "Le discours paraît unilatéral ou peu révisable." if score >= 0.4 else "Présence suffisante de nuances ou d'équilibre."
    }

STRATEGIC_REASONING_MARKERS = [
    "cela commence par",
    "c’est pourquoi",
    "nous devons",
    "cela signifie",
    "face à",
    "dans ce contexte",
    "par conséquent",
    "à long terme",
    "capacité à",
    "cela suppose",
    "ce qui implique",
    "nous ne pouvons plus",
    "il y a la question",
]

def compute_argument_density(text):
    words = re.findall(r"\b[\wÀ-ÿ'-]+\b", text.lower())
    word_count = max(len(words), 1)

    reason_markers = count_marker_occurrences(text, REASON_MARKERS)
    conclusion_markers = count_marker_occurrences(text, CONCLUSION_MARKERS)
    nuance_markers = count_marker_occurrences(text, NUANCE_MARKERS)
    strategic_markers = count_marker_occurrences(text, STRATEGIC_REASONING_MARKERS)

    argumentative_units = (
        reason_markers
        + conclusion_markers
        + (nuance_markers * 0.35)
        + (strategic_markers * 0.75)
    )

    score = min((argumentative_units / word_count) * 22, 1)

    markers = []

    if reason_markers > 0:
        markers.append(f"Marqueurs de justification : {reason_markers}")

    if conclusion_markers > 0:
        markers.append(f"Marqueurs de conclusion : {conclusion_markers}")

    if nuance_markers > 0:
        markers.append(f"Marqueurs de nuance : {nuance_markers} × 0.35")

    if strategic_markers > 0:
        markers.append(f"Marqueurs de raisonnement stratégique : {strategic_markers} × 0.75")

    if score < 0.15:
        interpretation = "Le texte affirme davantage qu'il n'argumente explicitement."
    elif score < 0.35:
        interpretation = "Le texte contient une densité argumentative limitée."
    elif score < 0.60:
        interpretation = "Le texte présente une densité argumentative correcte."
    else:
        interpretation = "Le texte contient une forte densité argumentative."

    return {
        "score": round(score, 3),
        "label": label_level(score),
        "units": round(argumentative_units, 2),
        "markers": markers,
        "word_count": word_count,
        "interpretation": interpretation
    }

def compute_structural_diagnosis(
    narrative_pressure,
    logical_jump,
    argument_asymmetry,
    argument_density
):
    pressure = narrative_pressure["score"]
    jump = logical_jump["score"]
    asymmetry = argument_asymmetry["score"]
    density = argument_density["score"]

    risk = (
        pressure * 0.30 +
        jump * 0.30 +
        asymmetry * 0.25 +
        (1 - density) * 0.15
    )

    if risk < 0.25:
        label = "Structure argumentative stable"
        interpretation = "Le texte présente une structure argumentative relativement équilibrée."
    elif risk < 0.50:
        label = "Structure partiellement orientée"
        interpretation = "Le texte présente quelques signaux d’orientation ou de raccourci argumentatif."
    elif risk < 0.75:
        label = "Structure argumentative fragile"
        interpretation = "Le texte combine plusieurs signaux de pression, d’asymétrie ou de conclusion rapide."
    else:
        label = "Structure fortement verrouillante"
        interpretation = "Le texte pousse fortement vers une conclusion avec peu de contrepoids argumentatif."

    return {
        "score": round(risk, 3),
        "label": label,
        "interpretation": interpretation,
        "profile": {
            "pressure": pressure,
            "logical_jump": jump,
            "asymmetry": asymmetry,
            "density": density
        }
}

def compute_absolute_prediction(text):
    sentences = max(len([s for s in re.split(r"[.!?]+", text) if s.strip()]), 1)
    markers = count_marker_occurrences(text, ABSOLUTE_PREDICTION_MARKERS)

    score = min((markers / sentences) * 2.5, 1)

    return {
        "score": round(score, 3),
        "label": label_level(score),
        "markers": markers,
        "interpretation": (
            "Le texte formule des prédictions présentées comme certaines."
            if score >= 0.4
            else "Peu de prédictions affirmées comme inévitables."
        )
    }

def compute_threat_amplification_advanced(text):
    sentences = max(len([s for s in re.split(r"[.!?]+", text) if s.strip()]), 1)
    markers = count_marker_occurrences(text, THREAT_AMPLIFICATION_MARKERS)

    score = min((markers / sentences) * 2.8, 1)

    return {
        "score": round(score, 3),
        "label": label_level(score),
        "markers": markers,
        "interpretation": (
            "Le texte amplifie fortement une menace ou un danger."
            if score >= 0.4
            else "Peu d’amplification explicite de menace."
        )
    }

def compute_strong_certainty(text):
    t = normalize_text_for_markers(text)

    sentences = max(
        len([s for s in re.split(r"[.!?]+", text) if s.strip()]),
        1
    )

    found_markers = [
        marker for marker in STRONG_CERTAINTY_MARKERS
        if contains_term(t, marker)
    ]

    hedge_markers = [
        "pas nécessairement",
        "peut",
        "peuvent",
        "pourrait",
        "pourraient",
        "semble",
        "semblent",
        "plusieurs facteurs",
        "plusieurs options",
        "doivent être distingués",
        "à ce stade",
        "selon",
        "cependant",
        "toutefois",
        "néanmoins",
        "sans tenir compte",
        "devrait éviter",
    ]

    hedge_hits = [
        marker for marker in hedge_markers
        if contains_term(t, marker)
    ]

    marker_count = len(found_markers)

    raw_score = (marker_count / sentences) * 3.0

    hedge_reduction = min(len(hedge_hits) * 0.08, 0.45)

    score = max(0.0, min(raw_score - hedge_reduction, 1.0))
    
    if score <= 0.05 and hedge_hits and found_markers:
        interpretation = (
            "Des formulations assertives existent, mais elles sont fortement compensées "
            "par des marqueurs de nuance et de prudence."
        )
    elif score >= 0.4:
        interpretation = "Le texte emploie une certitude forte ou verrouillante."
    else:
        interpretation = "Peu de certitude forte composée détectée."
    
    return {
        "score": round(score, 3),
        "label": label_level(score),
        "markers": found_markers,
        "hedge_markers": hedge_hits,
        "marker_count": marker_count,
        "hedge_count": len(hedge_hits),
        "interpretation": interpretation,
    }
# =====================================================
# DÉTECTION DES DOMAINES CONCEPTUELS
# =====================================================
def contains_term(text: str, term: str) -> bool:
    return re.search(rf"\b{re.escape(term.lower())}\b", text.lower()) is not None

JOURNALISTIC_MARKERS = [
    "selon", "d'après", "rapport", "étude", "enquête",
    "article", "communiqué", "sondage", "journal", "presse",
    "média", "journaliste", "source", "porte-parole",
    "a déclaré", "a affirmé", "a indiqué", "a annoncé",
    "selon une étude", "selon le rapport", "d'après les données",
]
PHILOSOPHICAL_MARKERS = [
    "vérité", "réalité", "existence", "être", "essence",
    "conscience", "raison", "pensée", "savoir", "croyance",
    "doute", "concept", "principe", "idée", "notion",
    "morale", "éthique", "justice", "liberté", "devoir",
    "dans quelle mesure", "qu'est-ce que", "en ce sens",
]
RELIGIOUS_MARKERS = [
    "dieu", "divin", "foi", "religion", "croyant",
    "âme", "esprit", "sacré", "saint", "prière",
    "rite", "culte", "église", "mosquée", "temple",
    "prophète", "révélation", "évangile", "coran", "bible",
    "péché", "salut", "grâce", "paradis", "enfer",
]
GEOSTRATEGIC_MARKERS = [
    "souveraineté",
    "défense",
    "sécurité",
    "frontières",
    "puissance",
    "autonomie stratégique",
    "intérêts",
    "alliés",
    "otan",
    "investissement européen",
    "industrie",
    "prospérité",
    "guerre",
    "paix",
    "encerclement",
    "grandes puissances",
    "modèle économique",
    "défense européenne",
    "sécurité européenne",
    "puissance européenne",
    "intelligence artificielle",
    "biotechnologies",
    "énergie décarbonée",
    "espace",
]
POLITICAL_MARKERS = [
    "politique",
    "état",
    "gouvernement",
    "démocratie",
    "république",
    "nation",
    "europe",
    "président",
    "loi",
    "institution",
    "peuple",
    "économie",
]
# =========================================================
# ENCYCLOPÉDIQUE
# =========================================================
ENCYCLOPEDIC_MARKERS = [
    "désigne",
    "correspond à",
    "se définit comme",
    "est défini comme",
    "est un concept",
    "est une théorie",
    "fait référence à",
    "est caractérisé par",
    "désigne le fait de",
    "on appelle",
    "définit comme",
    "consiste en",
    "est composé de",
    "est constitué de",
    "est une notion",
    "renvoie à",
    "correspond au terme",
    "selon la définition",
    "dans ce contexte",
    "au sens de",
    "is defined as",
    "refers to",
    "consists of",
]
# =========================================================
# DÉFINITIONNEL / PÉDAGOGIQUE
# =========================================================
DEFINITION_MARKERS = [
    "par exemple",
    "en résumé",
    "en d'autres termes",
    "autrement dit",
    "on distingue",
    "on appelle",
    "il existe plusieurs",
    "se caractérise par",
    "peut être défini",
    "permet de comprendre",
    "vise à expliquer",
    "dans ce cas",
    "ce phénomène",
    "ce mécanisme",
    "explication",
    "définition",
    "notion",
    "concept",
    "pédagogique",
]
# =========================================================
# GÉOPOLITIQUE
# =========================================================
GEOPOLITICAL_MARKERS = [
    "bloc occidental",
    "bloc de l'est",
    "sphère d'influence",
    "équilibre des puissances",
    "relations internationales",
    "ordre mondial",
    "puissance régionale",
    "monde multipolaire",
    "civilisation",
    "territoire",
    "frontière",
    "migration",
    "soft power",
    "hard power",
    "alliance stratégique",
    "axe géopolitique",
    "expansion territoriale",
    "tensions internationales",
    "zone d'influence",
    "monde occidental",
    "bloc eurasiatique",
    "world order",
    "geopolitical",
]
# =========================================================
# ÉCOLOGIQUE
# =========================================================
ECOLOGICAL_MARKERS = [
    "réchauffement climatique",
    "biodiversité",
    "empreinte carbone",
    "transition énergétique",
    "écosystème",
    "effondrement climatique",
    "neutralité carbone",
    "développement durable",
    "émissions de carbone",
    "catastrophe climatique",
    "écologie",
    "climat",
    "pollution",
    "gaz à effet de serre",
    "dérèglement climatique",
    "planète",
    "ressources naturelles",
    "énergie renouvelable",
    "extinction des espèces",
    "climate change",
    "carbon emissions",
]
# =========================================================
# SOCIAL / SOCIOLOGIQUE
# =========================================================
SOCIAL_MARKERS = [
    "inégalités sociales",
    "classes sociales",
    "mobilité sociale",
    "violence sociale",
    "exclusion",
    "marginalisation",
    "discrimination",
    "cohésion sociale",
    "fracture sociale",
    "justice sociale",
    "milieu social",
    "conditions de vie",
    "minorité",
    "majorité",
    "société",
    "communauté",
    "groupe social",
    "précarité",
    "social inequality",
    "social exclusion",
]
# =========================================================
# BIOGRAPHIQUE
# =========================================================
BIOGRAPHICAL_MARKERS = [
    "né en",
    "née en",
    "mort en",
    "morte en",
    "décédé en",
    "décédée en",
    "sa vie",
    "son œuvre",
    "son parcours",
    "sa carrière",
    "il grandit",
    "elle grandit",
    "il devient",
    "elle devient",
    "biographie",
    "autobiographie",
    "mémoires",
    "parcours de vie",
    "portrait de",
    "figure historique",
]
# =========================================================
# FICTIONNEL / NARRATIF
# =========================================================
FICTION_MARKERS = [
    "roman",
    "personnage",
    "intrigue",
    "chapitre",
    "récit",
    "narrateur",
    "héros",
    "héroïne",
    "conte",
    "fiction",
    "nouvelle",
    "univers fictif",
    "histoire imaginaire",
    "scène",
    "dialogue",
    "protagoniste",
    "antagoniste",
    "quête",
    "drame",
    "aventure",
]
# =========================================================
# MYTHIQUE / SYMBOLIQUE
# =========================================================
MYTHIC_MARKERS = [
    "mythe",
    "légende",
    "symbole",
    "archétype",
    "quête initiatique",
    "rite",
    "destin",
    "héritage spirituel",
    "cosmique",
    "sacré",
    "divinité",
    "oracle",
    "prophétie",
    "monde invisible",
    "transcendance",
    "initiation",
]
def detect_conceptual_domains(text: str):
    t = text.lower()

    domains = {
        "journalistique": 0,
        "philosophique": 0,
        "religieux": 0,
        "geostrategique": 0,
        "politique": 0,
        "encyclopedique": 0,
        "definitionnel": 0,
        "geopolitique": 0,
        "ecologique": 0,
        "social": 0,
        "biographique": 0,
        "fictionnel": 0,
        "mythique": 0,
    }

    terms = {
        "journalistique": [],
        "philosophique": [],
        "religieux": [],
        "geostrategique": [],
        "politique": [],
    
        "encyclopedique": [],
        "definitionnel": [],
        "geopolitique": [],
        "ecologique": [],
        "social": [],
        "biographique": [],
        "fictionnel": [],
        "mythique": [],
    }
    
    for marker in JOURNALISTIC_MARKERS:
        if contains_term(t, marker):
            domains["journalistique"] += 1
            terms["journalistique"].append(marker)

    for marker in PHILOSOPHICAL_MARKERS:
        if contains_term(t, marker):
            domains["philosophique"] += 1
            terms["philosophique"].append(marker)

    for marker in RELIGIOUS_MARKERS:
        if contains_term(t, marker):
            domains["religieux"] += 1
            terms["religieux"].append(marker)

    for marker in GEOSTRATEGIC_MARKERS:
        if contains_term(t, marker):
            domains["geostrategique"] += 1
            terms["geostrategique"].append(marker)

    for marker in POLITICAL_MARKERS:
        if contains_term(t, marker):
            domains["politique"] += 1
            terms["politique"].append(marker)

    for marker in ENCYCLOPEDIC_MARKERS:
        if contains_term(t, marker):
            domains["encyclopedique"] += 1
            terms["encyclopedique"].append(marker)

    for marker in DEFINITION_MARKERS:
        if contains_term(t, marker):
            domains["definitionnel"] += 1
            terms["definitionnel"].append(marker)
    
    for marker in GEOPOLITICAL_MARKERS:
        if contains_term(t, marker):
            domains["geopolitique"] += 1
            terms["geopolitique"].append(marker)
    
    for marker in ECOLOGICAL_MARKERS:
        if contains_term(t, marker):
            domains["ecologique"] += 1
            terms["ecologique"].append(marker)
    
    for marker in SOCIAL_MARKERS:
        if contains_term(t, marker):
            domains["social"] += 1
            terms["social"].append(marker)
    
    for marker in BIOGRAPHICAL_MARKERS:
        if contains_term(t, marker):
            domains["biographique"] += 1
            terms["biographique"].append(marker)
    
    for marker in FICTION_MARKERS:
        if contains_term(t, marker):
            domains["fictionnel"] += 1
            terms["fictionnel"].append(marker)
    
    for marker in MYTHIC_MARKERS:
        if contains_term(t, marker):
            domains["mythique"] += 1
            terms["mythique"].append(marker)

    return domains, terms

# -----------------------------
# Discours rapporté / citations
# -----------------------------
def compute_reported_speech_ratio(text: str) -> dict:
    if not text:
        return {
            "score": 0.0,
            "ratio": 0.0,
            "markers": [],
            "interpretation": "Aucun discours rapporté détecté."
        }

    t = text.lower()
    words = re.findall(r"\b[\wÀ-ÿ'-]+\b", text)
    word_count = max(len(words), 1)

    quote_segments = re.findall(r"[«“\"](.+?)[»”\"]", text, flags=re.DOTALL)
    quote_words = sum(len(re.findall(r"\b[\wÀ-ÿ'-]+\b", q)) for q in quote_segments)

    reporting_markers = [
        "déclare", "déclarait", "affirme", "affirmait", "estime", "estimait",
        "explique", "expliquait", "souligne", "soulignait", "rappelle", "rappelait",
        "selon", "d'après", "pour", "interrogé", "invitée", "invité",
        "a jugé", "a précisé", "a déclaré", "avait déclaré", "considère"
    ]

    markers = [m for m in reporting_markers if m in t]

    quote_ratio = quote_words / word_count
    marker_ratio = min(len(markers) / 10, 1.0)

    score = min((quote_ratio * 1.8) + (marker_ratio * 0.5), 1.0)

    if score < 0.15:
        interpretation = "Le texte rapporte peu de propos extérieurs."
    elif score < 0.35:
        interpretation = "Le texte contient quelques éléments de discours rapporté."
    elif score < 0.60:
        interpretation = "Le texte rapporte fortement des propos ou positions extérieures."
    else:
        interpretation = "Le texte est largement structuré par des citations ou discours rapportés."

    return {
        "score": round(score, 3),
        "ratio": round(quote_ratio, 3),
        "markers": markers[:15],
        "interpretation": interpretation
    }
# =============================
# Ancrage au réel
# =============================

REAL_ANCHOR_EMPIRY = [
    "expérience", "expérimentation", "mesure", "mesuré", "observation",
    "observé", "test", "testé", "données", "protocole", "benchmark",
    "résultat", "validation", "validé", "détecté", "reproduit",
    "statistiquement significatif", "échantillon", "essai clinique",
    "simulation validée", "étude", "rapport", "chiffres", "pourcentage",
    "%", "selon", "économistes", "expert", "secteurs", "postes", "créés", 
    "emplois", "finance", "santé"
]
REAL_ANCHOR_REPRODUCIBILITY = [
    "méthode", "paramètres", "reproductible", "reproductibilité",
    "réplication", "répliqué", "protocole détaillé", "dataset",
    "jeu de données", "open source", "code source", "doi", "arxiv",
    "publication", "revue par les pairs", "littérature scientifique"
]
REAL_ANCHOR_FALSIFIABILITY = [
    "hypothèse", "modèle partiel", "approximation", "sous certaines conditions",
    "pourrait être faux", "pourrait être réfuté", "compatible avec",
    "marge d’erreur", "marge d'erreur", "résultats préliminaires",
    "selon les données actuelles", "limite du modèle", "pourraient", "pourrait", 
    "certains", "restent prudents", "il faut nuancer", "nuancer", "cependant"
]
REAL_ANCHOR_LIMITS = [
    "nous ne savons pas", "reste incomplet", "interprétation débattue",
    "hypothèse de travail", "limite actuelle", "nécessite validation",
    "nécessite davantage de recherches", "cadre spécifique",
    "dans cette classe de systèmes", "conditions de validité",
    "limites de cette approche"
]
SPECULATIVE_INFLATION_MARKERS = [
    "explique tout", "théorie du tout", "théorie unifiée",
    "structure cachée", "structure fondamentale du réel",
    "clé fondamentale", "clé de l’univers", "tout découle de",
    "aucune exception", "preuve finale", "preuve définitive",
    "révolution complète", "erreur historique majeure",
    "la vraie structure", "enfin expliqué", "peut enfin être expliqué",
    "description complète", "sans nouveaux paramètres",
    "tous les systèmes", "chaque système", "toujours", "jamais",
    "inévitablement", "nécessairement", "va remplacer", 
    "il est absolument certain", "crise sociale majeure", 
    "si rien n'est fait immédiatement", "révolution sans précédent", 
    "étude choc"
]

def count_real_anchor_markers(text, markers):
    t = text.lower()
    found = []

    for marker in markers:
        if marker.lower() in t:
            found.append(marker)

    return found

def normalize_component(count, divisor=4):
    """
    Transforme un nombre de marqueurs en score 0–5.
    """
    return min(5.0, count / divisor * 5)


def detect_real_anchor(text, result=None):
    """
    Mesure l'ancrage au réel d'un discours.

    A = (E + R + F + L) - S
    E = empirie
    R = reproductibilité
    F = falsifiabilité
    L = limites explicites
    S = spéculation extrapolative

    Score final normalisé sur 20.
    """

    empirical_markers = count_real_anchor_markers(text, REAL_ANCHOR_EMPIRY)
    reproducibility_markers = count_real_anchor_markers(text, REAL_ANCHOR_REPRODUCIBILITY)
    falsifiability_markers = count_real_anchor_markers(text, REAL_ANCHOR_FALSIFIABILITY)
    limits_markers = count_real_anchor_markers(text, REAL_ANCHOR_LIMITS)
    speculation_markers = count_real_anchor_markers(text, SPECULATIVE_INFLATION_MARKERS)

    E = normalize_component(len(empirical_markers), divisor=5)
    R = normalize_component(len(reproducibility_markers), divisor=4)
    F = normalize_component(len(falsifiability_markers), divisor=3)
    L = normalize_component(len(limits_markers), divisor=3)
    S = normalize_component(len(speculation_markers), divisor=4)

    # Bonus prudent si le texte contient des références académiques explicites
    academic_bonus = 0

    t = text.lower()
    if "doi" in t or "arxiv" in t or "revue par les pairs" in t:
        academic_bonus += 1.0

    if "protocole" in t and ("données" in t or "dataset" in t):
        academic_bonus += 0.8

    if "limite" in t or "hypothèse" in t:
        academic_bonus += 0.5

    raw_score = (E + R + F + L + academic_bonus) - S

    # Normalisation sur 20
    anchor_score = max(0, min(20, raw_score / 21 * 20))

    if anchor_score < 5:
        label = "Très faible"
        interpretation = (
            "Le discours est faiblement contraint par le réel : peu d’expérience, "
            "peu de reproductibilité ou forte extrapolation spéculative."
        )
    elif anchor_score < 10:
        label = "Fragile"
        interpretation = (
            "Le discours contient quelques appuis réels, mais ils restent insuffisants "
            "face à la portée des affirmations."
        )
    elif anchor_score < 15:
        label = "Modéré"
        interpretation = (
            "Le discours présente un ancrage partiel : certains éléments sont vérifiables, "
            "mais la démonstration reste incomplète."
        )
    elif anchor_score < 18:
        label = "Fort"
        interpretation = (
            "Le discours est fortement relié à des éléments empiriques, méthodologiques "
            "ou reproductibles."
        )
    else:
        label = "Très fort"
        interpretation = (
            "Le discours paraît fortement contraint par le réel : données, méthode, "
            "révisabilité et reproductibilité sont bien représentées."
        )

    # Couplage avec M et spéculation si result existe
    M = 0
    if result:
        M = result.get("M", 0)

    delta_reality = round((M + S) - anchor_score, 2)

    if delta_reality <= -5:
        delta_label = "Structure fortement ancrée"
        delta_interpretation = (
            "L’ancrage au réel domine nettement la spéculation et la mécroyance."
        )
    elif delta_reality <= 2:
        delta_label = "Zone révisable"
        delta_interpretation = (
            "Le discours conserve un équilibre entre cohérence, spéculation et contrainte du réel."
        )
    else:
        delta_label = "Cohérence autoporteuse possible"
        delta_interpretation = (
            "La cohérence ou la spéculation semblent dépasser l’ancrage empirique disponible."
        )

    return {
        "real_anchor_score": round(anchor_score, 2),
        "real_anchor_label": label,
        "real_anchor_interpretation": interpretation,

        "real_anchor_E": round(E, 2),
        "real_anchor_R": round(R, 2),
        "real_anchor_F": round(F, 2),
        "real_anchor_L": round(L, 2),
        "real_anchor_S": round(S, 2),

        "real_anchor_empirical_markers": empirical_markers,
        "real_anchor_reproducibility_markers": reproducibility_markers,
        "real_anchor_falsifiability_markers": falsifiability_markers,
        "real_anchor_limits_markers": limits_markers,
        "real_anchor_speculation_markers": speculation_markers,

        "delta_reality": delta_reality,
        "delta_reality_label": delta_label,
        "delta_reality_interpretation": delta_interpretation,
    }
    
def compute_cognitive_bonus(result: dict):
    """
    Module bonus :
    compense partiellement les pénalités
    lorsqu'un texte reste ouvert,
    cohérent et ancré au réel.
    """

    def clamp01(x):
        return max(0.0, min(1.0, x))

    # -----------------------------
    # 1) Ancrage au réel
    # -----------------------------
    anchor = result.get("real_anchor_score", 10) / 20

    # -----------------------------
    # 2) Révisabilité
    # -----------------------------
    nuance = min(
        len(result.get("nuance_markers", [])) / 10,
        1.0
    )

    uncertainty = min(
        len(result.get("uncertainty_markers", [])) / 10,
        1.0
    )

    counter = min(
        len(result.get("counter_argument_markers", [])) / 8,
        1.0
    )

    closure = result.get("closure_index", 0)

    revisability = clamp01(
        (
            nuance * 0.35 +
            uncertainty * 0.25 +
            counter * 0.25
        )
        -
        closure * 0.25
    )

    # -----------------------------
    # 3) Cohérence discursive
    # -----------------------------
    coherence = clamp01(
        (
            result.get("argument_density_score", 0) * 0.35
            +
            (
                1 -
                result.get(
                    "internal_dissonance_score",
                    0
                )
            ) * 0.35
            +
            (
                result.get(
                    "reasoning_score",
                    result.get(
                        "hard_fact_score",
                        10
                    ) / 20
                )
            ) * 0.30
        )
    )

    # -----------------------------
    # Bonus final
    # -----------------------------
    bonus = clamp01(
        anchor * 0.45
        +
        revisability * 0.30
        +
        coherence * 0.25
    )

    return {
        "bonus_anchor": round(anchor, 3),
        "bonus_revisability": round(revisability, 3),
        "bonus_coherence": round(coherence, 3),

        "cognitive_bonus": round(bonus, 3),

        "bonus_interpretation":
            "Compensation par ancrage réel, révisabilité et cohérence."
    }


def analyze_article(text: str) -> Dict:
    article = text
    words = text.split()
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 10]
    article_length = len(words)

    source_markers = len(re.findall(r"|".join(re.escape(c) for c in SOURCE_CUES), text.lower()))
    citation_like = len(re.findall(r'"|\'|«|»', text))
    nuance_markers = len(re.findall(r"|".join(re.escape(c) for c in NUANCE_MARKERS), text.lower()))

    G = clamp(source_markers * 1.1 + citation_like * 0.2, 0, 10)
    N = clamp(nuance_markers * 1.4 + (article_length / 140), 0, 10)
    
    discursive_analysis = compute_discursive_coherence(text)
    premise_analysis = compute_implicit_premises(text)
    logic_confusion_analysis = compute_logic_confusion(text)
    aristotelian_fallacies = detect_aristotelian_fallacies(text)
    descriptive_normative_confusion = detect_descriptive_normative_confusion(text)
    petition_analysis = detect_petition_principii(text)
    cherry_picking_analysis = detect_cherry_picking(text)
    scientific_simulation_analysis = compute_scientific_simulation(text)
    propaganda_analysis = detect_propaganda_narrative(text)
    short_form_analysis = detect_short_form_mode(text)
    historical_analysis = detect_historical_text_mode(text)
    index_page_analysis = detect_index_or_multilink_page(text)
    causal_overreach_analysis = compute_causal_overreach(text)
    vague_authority_analysis = compute_vague_authority(text)
    
    generalization_analysis = compute_generalization(text)
    abstract_enemy_analysis = compute_abstract_enemy(text)
    certainty_analysis = compute_certainty(text)
    false_consensus_analysis = compute_false_consensus(text)
    false_consensus_strong_analysis = detect_false_consensus_strong(text)
    binary_opposition_analysis = compute_binary_opposition(text)
    threat_amplification_analysis = compute_threat_amplification(text)
    semantic_shift_analysis = detect_semantic_shift(text)
    ideological_premise_analysis = detect_ideological_premises(text)

    false_analogy_analysis = compute_false_analogy(text)
    factual_overinterpretation_analysis = compute_factual_overinterpretation(text)
    internal_dissonance_analysis = compute_internal_dissonance(text)
    normative_saturation_analysis = compute_normative_saturation(text)
    doxic_rigidity_analysis = compute_doxic_rigidity(text)
    narrative_overdetermination_analysis = compute_narrative_overdetermination(text)

    victimization_analysis = compute_victimization(text)
    moral_polarization_analysis = compute_moral_polarization(text)
    strategic_simplification_analysis = compute_strategic_simplification(text)
    frame_shift_analysis = compute_frame_shift(text)

    absolute_prediction_analysis = compute_absolute_prediction(text)
    threat_amplification_advanced_analysis = compute_threat_amplification_advanced(text)
    strong_certainty_analysis = compute_strong_certainty(text)

    conceptual_domains, conceptual_terms = detect_conceptual_domains(text)
    
    rhetorical_scores = detect_rhetorical_structures(text)
    disc_type_rhetoric, disc_explanation_rhetoric, discourse_scores = detect_discourse_type_from_rhetoric(
        text,
        rhetorical_scores
    )
    emotional_registers = detect_emotional_registers(text)
    temp_result_for_emotion = {
        "emotional_registers": emotional_registers
    }

    emotional_intensity_analysis = compute_emotional_intensity(temp_result_for_emotion)
    statistical_manipulation_analysis = detect_statistical_manipulation(text)
    
    statistical_manipulation_analysis = detect_statistical_manipulation(text)
    misleading_comparison_analysis = detect_misleading_comparison(text)
    missing_reference_analysis = detect_missing_reference_data(text)
    advanced_deceptive_coherence_analysis = compute_advanced_deceptive_coherence(text)
    descriptive_normative_confusion_analysis = detect_descriptive_normative_confusion(text)
    reported_speech = compute_reported_speech_ratio(text)

    # -----------------------------
    # Jauges structurelles avancées
    # -----------------------------
    narrative_pressure_analysis = compute_narrative_pressure(text)
    logical_jump_analysis = compute_logical_jump(text)
    argument_asymmetry_analysis = compute_argument_asymmetry(text)
    argument_density_analysis = compute_argument_density(text)
    complex_enthymeme_analysis = compute_complex_enthymemes(text)
    self_validating_analysis = compute_self_validating_narrative(text)

    certainty = len(re.findall(r"certain|absolument|prouvé|évident|incontestable", text.lower()))
    emotional = len(re.findall(r"|".join(re.escape(w) for w in EMOTIONAL_WORDS), text.lower()))

    # -----------------------------
    # Nouvelle Doxa (D) recalibrée
    # -----------------------------
    D_raw = (
        certainty_analysis[0] * 0.30 +
        doxic_rigidity_analysis["score"] * 0.30 +
        normative_saturation_analysis["score"] * 0.15 +
        emotional_intensity_analysis["score"] * 0.15 +
        false_consensus_analysis[0] * 0.10
    )

    D = clamp(D_raw * 10, 0, 10)

    # -----------------------------
    # Indices dérivés recalibrés
    # -----------------------------
    G_drift = G * 0.5
    N_drift = N
    D_drift = D

    M = round((G_drift + N_drift) - D_drift, 1)

    drifts = compute_cognitive_drifts(
        G_drift,
        N_drift,
        D_drift
    )
    
    penalties = compute_red_flag_penalties({
        "G": G,
        "certainty_score": certainty_analysis[0],
        "vague_authority_score": vague_authority_analysis["score"],
        "causal_overreach_score": causal_overreach_analysis["score"],
        "factual_overinterpretation_score": factual_overinterpretation_analysis["score"],
        "propaganda_score": propaganda_analysis["score"],
        "emotional_intensity_score": emotional_intensity_analysis["score"],
        "false_consensus_score": false_consensus_analysis[0],
        "binary_opposition_score": binary_opposition_analysis[0],
        "internal_dissonance_score": internal_dissonance_analysis["score"],
        "semantic_shift_score": semantic_shift_analysis["score"],
        "ideological_premise_score": ideological_premise_analysis["score"],
        "doxic_rigidity_score": doxic_rigidity_analysis["score"],
        "drift_pseudo_savoir": drifts["drift_pseudo_savoir"],
    })

    V = clamp(G * 0.8 + N * 0.2, 0, 10)
    
    # modulation émotion par N (nous)
    emotional_effect = emotional_intensity_analysis["score"] * (1 - (N / 10))
    
    R = clamp(
        (
            D * 0.55 +
            emotional_effect * 10 * 0.20 +
            propaganda_analysis["score"] * 10 * 0.25
        ),
        0,
        10
    )
    
    improved = round((G + N + V) - (D + R), 1)

    # -----------------------------
    # Claims
    # -----------------------------
    claims = [analyze_claim(s) for s in sentences[:15]]

    syllogisms = detect_syllogisms_from_claims(claims)
    enthymemes = detect_enthymemes_from_claims(claims)

    # Fallback structurel pour enthymème implicite
    if not enthymemes:
        t = normalize_text_for_markers(text)

        if (
            ("il devient donc nécessaire" in t or "nécessaire d'agir" in t or "nécessaire d’agir" in t)
            and (
                "ceux qui disent la vérité" in t
                or "censur" in t
                or "autorités ont menti" in t
                or "personne ne mentionne" in t
                or "système" in t
            )
        ):
            enthymemes.append({
                "conclusion": "Il devient donc nécessaire d’agir avant qu’il ne soit trop tard.",
                "form": "-",
                "subject": "-",
                "predicate": "-",
                "context": [
                    "Le texte présuppose que la vérité est censurée ou cachée.",
                    "Le texte présuppose que le système ou les autorités empêchent la reconnaissance des faits."
                ],
                "status": "possible_enthymeme_structural",
            })

    inference_patterns = detect_syllogisms(sentences)

    fallacies = detect_syllogistic_fallacies(syllogisms)

    print("=== DEBUG CLAIMS ===")
    for c in claims:
        print({
            "text": c.text,
            "form": c.aristotelian_type,
            "subject": c.subject_term,
            "predicate": c.predicate_term
        })

    print("=== DEBUG SYLLOGISMS ===")
    print(syllogisms)

    print("=== DEBUG FALLACIES ===")
    print(fallacies)

    syllogism_signal = len(syllogisms)
    enthymeme_signal = len(enthymemes)
    fallacy_signal = len(fallacies)

    syllogism_label = "Aucun signal" if syllogism_signal == 0 else (
        "Signal faible" if syllogism_signal == 1 else
        "Signal modéré" if syllogism_signal <= 3 else
        "Signal fort"
    )

    enthymeme_label = "Aucun signal" if enthymeme_signal == 0 else (
        "Signal faible" if enthymeme_signal == 1 else
        "Signal modéré" if enthymeme_signal <= 3 else
        "Signal fort"
    )

    fallacy_label = "Aucun signal" if fallacy_signal == 0 else (
        "Signal faible" if fallacy_signal == 1 else
        "Signal modéré" if fallacy_signal <= 3 else
        "Signal fort"
    )
    
    avg_claim_verifiability = sum(c.verifiability for c in claims) / len(claims) if claims else 0
    avg_claim_risk = sum(c.risk for c in claims) / len(claims) if claims else 0
    source_quality = clamp(
        source_markers * 2
        - (emotional * 2)
        - (vague_authority_analysis["score"] * 8),
        0,
        20
    )

    red_flags = []
    if D > 8:
        red_flags.append("Doxa saturée")
    if emotional > 5:
        red_flags.append("Pathos excessif")
    if G < 2:
        red_flags.append("Désert documentaire")
    if article_length < 50:
        red_flags.append("Format indigent")

    mecroyance_penalties = compute_mecroyance_penalties({
        "drift_mecroyance": drifts["drift_mecroyance"],
        "drift_pseudo_savoir": drifts["drift_pseudo_savoir"],
        "drift_intuition_dogmatique": drifts["drift_intuition_dogmatique"],
    })

    total_credibility_penalty = (
        penalties["credibility_penalty"]
        + mecroyance_penalties["credibility_penalty"]
    )

    total_lie_boost = (
        penalties["lie_boost"]
        + mecroyance_penalties["lie_boost"]
    )

    hard_fact_score_raw = (
        (0.18 * G + 0.12 * N + 0.20 * V + 0.22 * source_quality + 0.18 * avg_claim_verifiability)
        - (0.16 * D + 0.12 * R + 0.18 * avg_claim_risk + total_credibility_penalty)
    )
    hard_fact_score = round(clamp(hard_fact_score_raw + 8, 0, 20), 1)
    short_epistemic_bonus = 0.0
    if claims:
        short_epistemic_bonus = sum(c.short_adjustment for c in claims) / len(claims)
        short_epistemic_bonus = min(short_epistemic_bonus, 1.5)

    hard_fact_score = round(clamp(hard_fact_score + short_epistemic_bonus, 0, 20), 1)

    political_pattern_score, political_results, matched_terms = detect_political_patterns(text)
    rhetorical_pressure = compute_rhetorical_pressure(political_results)

    # -----------------------------
    # Cohérence trompeuse
    # -----------------------------
    deceptive_coherence, deceptive_label = compute_deceptive_coherence(
        G,
        N,
        D,
        rhetorical_pressure,
        propaganda_analysis["score"],
        hard_fact_score,
        article_length
    )

    # -----------------------------
    # Score final fusion des jauges
    # -----------------------------
    HFS = hard_fact_score / 20

    OC = max(0.0, (G + N) / (G + N + D)) if (G + N + D) > 0 else 0.0

    discursive_pressure = min(
        1.0,
        propaganda_analysis["score"] + rhetorical_pressure
    )

    ID = max(0.1, 1 - discursive_pressure)

    final_credibility_score = round(
        20 * HFS * OC * ID,
        1
    )

    if final_credibility_score < 6:
        verdict = T["low_credibility"]
    elif final_credibility_score < 10:
        verdict = T["prudent_credibility"]
    elif final_credibility_score < 15:
        verdict = T["rather_credible"]
    else:
        verdict = T["strong_credibility"]

    strengths = []
    if source_markers >= 2:
        strengths.append(T["presence_of_source_markers"])
    if citation_like >= 2:
        strengths.append(T["verifiability_clues"])
    if nuance_markers >= 2:
        strengths.append(T["text_contains_nuances"])
    if source_quality >= 12:
        strengths.append(T["text_evokes_robust_sources"])
    if any(c.status == T["rather_verifiable"] for c in claims):
        strengths.append(T["some_claims_verifiable"])

    weaknesses = []
    if certainty >= 3:
        weaknesses.append(T["overly_assertive_language"])
    if emotional >= 2:
        weaknesses.append(T["notable_emotional_sensational_charge"])
    if source_markers == 0 and citation_like == 0:
        weaknesses.append(T["almost_total_absence_of_verifiable_elements"])
    if article_length < 80:
        weaknesses.append(T["text_too_short"])
    weaknesses.extend(red_flags)
    if sum(1 for c in claims if c.status == T["very_fragile"]) >= 2:
        weaknesses.append(T["multiple_claims_very_fragile"])

    ling = compute_linguistic_suspicion(text)
    L = ling["L"]

    ME_base = max(0, (2 * D) - (G + N))

    discursive_boost = sum([
        0,
        premise_analysis["score"] * 1.5,
        logic_confusion_analysis["score"] * 1.6,
        aristotelian_fallacies["score"] * 2.0,
        scientific_simulation_analysis["score"] * 1.2,
        propaganda_analysis["score"] * 2.5,
        cherry_picking_analysis["score"] * 1.6,
        false_consensus_analysis[0] * 1.2,
        factual_overinterpretation_analysis["score"] * 1.3
    ])

    ME = round((ME_base * L) + discursive_boost + total_lie_boost, 2)

    claims = [analyze_claim(sentence) for sentence in sentences[:15]]

    # -----------------------------
    # Score analogique du raisonnement
    # -----------------------------
    logical_connectors = len(re.findall(
        r"\b(car|donc|ainsi|cependant|pourtant|puisque|par conséquent|en effet|toutefois|néanmoins|or|mais|donc)\b",
        text.lower()
    ))

    sentence_count = max(1, len(sentences))

    connector_ratio = logical_connectors / sentence_count

    contradiction_signals = len(re.findall(
        r"\b(toujours.*sauf|jamais.*mais|certain.*pourtant|évident.*cependant|impossible.*mais)\b",
        text.lower()
    ))

    analogical_reasoning_score = (
        5
        + logical_connectors * 1.8
        + min(sentence_count, 8) * 0.35
        - contradiction_signals * 4
    )

    analogical_reasoning_score = round(
        clamp(analogical_reasoning_score, 0, 20),
        1
    )
        
    result = {
        "words": len(words),
        "sentences": len(sentences),
        "G": G,
        "N": N,
        "D": D,
        "M": M,
        "ME_base": ME_base,
        "ME": ME,
        "L": L,
        "normative_score": 0,
        "normative_terms": [],
        "normative_judgment_markers": [],
        "normative_interpretation": "",

        "semantic_shift_score": semantic_shift_analysis["score"],
        "semantic_shift_markers": semantic_shift_analysis["markers"],
        "semantic_shift_interpretation": semantic_shift_analysis["interpretation"],

        "ideological_premise_score": ideological_premise_analysis["score"],
        "ideological_premise_markers": ideological_premise_analysis["markers"],
        "ideological_premise_interpretation": ideological_premise_analysis["interpretation"],

        "discursive_coherence_score": discursive_analysis["score"],
        "discursive_coherence_label": discursive_analysis["label"],
        "discursive_coherence_details": discursive_analysis,

        "premise_score": premise_analysis["score"],
        "premise_markers": premise_analysis["markers"],
        "premise_interpretation": premise_analysis["interpretation"],
        "premise_details": premise_analysis["details"],

        "logic_confusion_score": logic_confusion_analysis["score"],
        "logic_confusion_markers": logic_confusion_analysis["markers"],
        "logic_confusion_interpretation": logic_confusion_analysis["interpretation"],
        "logic_confusion_details": logic_confusion_analysis["details"],

        "aristotelian_fallacies_score": aristotelian_fallacies["score"],

        "false_causality_basic_score": aristotelian_fallacies["false_causality"]["score"],
        "false_causality_basic_markers": aristotelian_fallacies["false_causality"]["matches"],
        "false_causality_basic_interpretation": aristotelian_fallacies["false_causality"]["interpretation"],

        "hasty_generalization_score": aristotelian_fallacies["generalization"]["score"],
        "hasty_generalization_markers": aristotelian_fallacies["generalization"]["matches"],
        "hasty_generalization_interpretation": aristotelian_fallacies["generalization"]["interpretation"],

        "vague_authority_basic_score": aristotelian_fallacies["vague_authority"]["score"],
        "vague_authority_basic_markers": aristotelian_fallacies["vague_authority"]["matches"],
        "vague_authority_basic_interpretation": aristotelian_fallacies["vague_authority"]["interpretation"],

        "false_dilemma_score": aristotelian_fallacies["false_dilemma"]["score"],
        "false_dilemma_markers": aristotelian_fallacies["false_dilemma"]["matches"],
        "false_dilemma_interpretation": aristotelian_fallacies["false_dilemma"]["interpretation"],

        "normative_qualification_score": aristotelian_fallacies["normative_qualification"]["score"],
        "normative_qualification_markers": aristotelian_fallacies["normative_qualification"]["matches"],
        "normative_qualification_interpretation": aristotelian_fallacies["normative_qualification"]["interpretation"],

        "ideological_premise_sophism_score": aristotelian_fallacies["ideological_premise"]["score"],
        "ideological_premise_sophism_markers": aristotelian_fallacies["ideological_premise"]["matches"],
        "ideological_premise_sophism_interpretation": aristotelian_fallacies["ideological_premise"]["interpretation"],

        "false_consensus_strong_score": false_consensus_strong_analysis["score"],
        "false_consensus_strong_markers": false_consensus_strong_analysis["markers"],
        "false_consensus_strong_interpretation": false_consensus_strong_analysis["interpretation"],

        "argument_from_nature_score": aristotelian_fallacies["argument_from_nature"]["score"],
        "argument_from_nature_markers": aristotelian_fallacies["argument_from_nature"]["matches"],
        "argument_from_nature_interpretation": aristotelian_fallacies["argument_from_nature"]["interpretation"],

        "descriptive_normative_confusion_score": descriptive_normative_confusion["score"],
        "descriptive_normative_confusion_markers": descriptive_normative_confusion["markers"],
        "descriptive_normative_confusion_interpretation": descriptive_normative_confusion["interpretation"],
        "descriptive_normative_confusion_nuance_count": descriptive_normative_confusion_analysis.get("nuance_count", 0),
        "descriptive_normative_confusion_nuance_markers": descriptive_normative_confusion_analysis.get("nuance_markers", []),

        "complex_enthymeme_score": complex_enthymeme_analysis["score"],
        "complex_enthymeme_markers": complex_enthymeme_analysis["markers"],
        "complex_enthymeme_interpretation": complex_enthymeme_analysis["interpretation"],
        
        "petition_score": petition_analysis["score"],
        "petition_markers": petition_analysis["markers"],
        "petition_interpretation": petition_analysis["interpretation"],

        "scientific_simulation_score": scientific_simulation_analysis["score"],
        "scientific_simulation_markers": scientific_simulation_analysis["markers"],
        "scientific_simulation_interpretation": scientific_simulation_analysis["interpretation"],
        "scientific_simulation_details": scientific_simulation_analysis["details"],

        "causal_overreach_score": causal_overreach_analysis["score"],
        "causal_overreach_markers": causal_overreach_analysis["markers"],
        "causal_overreach_interpretation": causal_overreach_analysis["interpretation"],

        "vague_authority_score": vague_authority_analysis["score"],
        "vague_authority_markers": vague_authority_analysis["markers"],
        "vague_authority_interpretation": vague_authority_analysis["interpretation"],

        "emotional_intensity_score": emotional_intensity_analysis["score"],
        "emotional_intensity_markers": emotional_intensity_analysis["markers"],
        "emotional_intensity_interpretation": emotional_intensity_analysis["interpretation"],

        "statistical_manipulation_score": statistical_manipulation_analysis["score"],
        "statistical_manipulation_markers": statistical_manipulation_analysis["markers"],
        "statistical_manipulation_interpretation": statistical_manipulation_analysis["interpretation"],

        "misleading_comparison_score": misleading_comparison_analysis["score"],
        "misleading_comparison_markers": misleading_comparison_analysis["markers"],
        "misleading_comparison_interpretation": misleading_comparison_analysis["interpretation"],

        "self_validating_score": self_validating_analysis["score"],
        "self_validating_markers": self_validating_analysis["markers"],
        "self_validating_interpretation": self_validating_analysis["interpretation"],

        "generalization_score": generalization_analysis[0],
        "generalization_interpretation": generalization_analysis[1],
        "generalization_markers": generalization_analysis[2],

        "abstract_enemy_score": abstract_enemy_analysis[0],
        "abstract_enemy_interpretation": abstract_enemy_analysis[1],
        "abstract_enemy_markers": abstract_enemy_analysis[2],

        "certainty_score": certainty_analysis[0],
        "certainty_interpretation": certainty_analysis[1],
        "certainty_markers": certainty_analysis[2],

        "false_consensus_score": false_consensus_analysis[0],
        "false_consensus_interpretation": false_consensus_analysis[1],
        "false_consensus_markers": false_consensus_analysis[2],

        "binary_opposition_score": binary_opposition_analysis[0],
        "binary_opposition_interpretation": binary_opposition_analysis[1],
        "binary_opposition_markers": binary_opposition_analysis[2],

        "threat_amplification_score": threat_amplification_analysis[0],
        "threat_amplification_interpretation": threat_amplification_analysis[1],
        "threat_amplification_markers": threat_amplification_analysis[2],

        "false_analogy_score": false_analogy_analysis["score"],
        "false_analogy_markers": false_analogy_analysis["markers"],
        "false_analogy_interpretation": false_analogy_analysis["interpretation"],

        "factual_overinterpretation_score": factual_overinterpretation_analysis["score"],
        "factual_overinterpretation_markers": factual_overinterpretation_analysis["markers"],
        "factual_overinterpretation_interpretation": factual_overinterpretation_analysis["interpretation"],

        "internal_dissonance_score": internal_dissonance_analysis["score"],
        "internal_dissonance_markers": internal_dissonance_analysis["markers"],
        "internal_dissonance_interpretation": internal_dissonance_analysis["interpretation"],

        "normative_saturation_score": normative_saturation_analysis["score"],
        "normative_saturation_markers": normative_saturation_analysis["markers"],
        "normative_saturation_interpretation": normative_saturation_analysis["interpretation"],

        "doxic_rigidity_score": doxic_rigidity_analysis["score"],
        "doxic_rigidity_markers": doxic_rigidity_analysis["markers"],
        "doxic_rigidity_interpretation": doxic_rigidity_analysis["interpretation"],

        "narrative_overdetermination_score": narrative_overdetermination_analysis["score"],
        "narrative_overdetermination_markers": narrative_overdetermination_analysis["markers"],
        "narrative_overdetermination_interpretation": narrative_overdetermination_analysis["interpretation"],

        "short_form_mode": short_form_analysis["is_short_form"],
        "short_form_label": short_form_analysis["label"],
        "short_form_interpretation": short_form_analysis["interpretation"],
        "word_count_precise": short_form_analysis["word_count"],

        "historical_mode": historical_analysis["is_historical"],
        "historical_score": historical_analysis["score"],
        "historical_markers": historical_analysis["markers"],
        "historical_interpretation": historical_analysis["interpretation"],

        "index_page_mode": index_page_analysis["is_index_page"],
        "index_page_score": index_page_analysis["score"],
        "index_page_markers": index_page_analysis["markers"],
        "index_page_interpretation": index_page_analysis["interpretation"],

        "propaganda_score": propaganda_analysis["score"],
        "propaganda_enemy_terms": propaganda_analysis["enemy_terms"],
        "propaganda_urgency_terms": propaganda_analysis["urgency_terms"],
        "propaganda_certainty_terms": propaganda_analysis["certainty_terms"],
        "propaganda_emotional_terms": propaganda_analysis["emotional_terms"],
        "propaganda_interpretation": propaganda_analysis["interpretation"],

        "victimization_score": victimization_analysis["score"],
        "victimization_markers": victimization_analysis["markers"],
        "victimization_interpretation": victimization_analysis["interpretation"],

        "moral_polarization_score": moral_polarization_analysis["score"],
        "moral_polarization_markers": moral_polarization_analysis["markers"],
        "moral_polarization_interpretation": moral_polarization_analysis["interpretation"],

        "strategic_simplification_score": strategic_simplification_analysis["score"],
        "strategic_simplification_markers": strategic_simplification_analysis["markers"],
        "strategic_simplification_interpretation": strategic_simplification_analysis["interpretation"],

        "frame_shift_score": frame_shift_analysis["score"],
        "frame_shift_markers": frame_shift_analysis["markers"],
        "frame_shift_interpretation": frame_shift_analysis["interpretation"],

        "argument_asymmetry_score": argument_asymmetry_analysis["score"],
        "argument_attack_count": argument_asymmetry_analysis.get("attack_count", 0), 
        "argument_support_count": argument_asymmetry_analysis.get("argument_count", 0),
        "argument_asymmetry_interpretation": argument_asymmetry_analysis["interpretation"],
       
        "argument_asymmetry_label": argument_asymmetry_analysis["label"],
        "argument_assertions_count": argument_asymmetry_analysis["assertions"],
        "argument_nuances_count": argument_asymmetry_analysis["nuances"],
        "argument_counterweight_count": argument_asymmetry_analysis.get("counterweight_count", 0),

        "narrative_pressure_score": narrative_pressure_analysis["score"],
        "narrative_pressure_label": narrative_pressure_analysis["label"],
        "narrative_pressure_interpretation": narrative_pressure_analysis["interpretation"],

        "logical_jump_score": logical_jump_analysis["score"],
        "logical_jump_label": logical_jump_analysis["label"],
        "logical_jump_interpretation": logical_jump_analysis["interpretation"],

        "argument_density_score": argument_density_analysis["score"],
        "argument_density_label": argument_density_analysis["label"],
        "argument_density_interpretation": argument_density_analysis["interpretation"],

        "absolute_prediction_score": absolute_prediction_analysis["score"],
        "absolute_prediction_label": absolute_prediction_analysis["label"],
        "absolute_prediction_interpretation": absolute_prediction_analysis["interpretation"],

        "threat_amplification_advanced_score": threat_amplification_advanced_analysis["score"],
        "threat_amplification_advanced_label": threat_amplification_advanced_analysis["label"],
        "threat_amplification_advanced_interpretation": threat_amplification_advanced_analysis["interpretation"],

        "strong_certainty_score": strong_certainty_analysis["score"],
        "strong_certainty_label": strong_certainty_analysis["label"],
        "strong_certainty_interpretation": strong_certainty_analysis["interpretation"],
        "strong_certainty_markers": strong_certainty_analysis["markers"],
        
        "missing_reference_score": missing_reference_analysis["score"],
        "missing_reference_markers": missing_reference_analysis["markers"],
        "missing_reference_interpretation": missing_reference_analysis["interpretation"],

        "advanced_deceptive_coherence_score": advanced_deceptive_coherence_analysis["score"],
        "advanced_deceptive_coherence_markers": advanced_deceptive_coherence_analysis["markers"],
        "advanced_deceptive_coherence_interpretation": advanced_deceptive_coherence_analysis["interpretation"],
        "advanced_deceptive_coherence_nuance_count": advanced_deceptive_coherence_analysis.get("nuance_count", 0),
        "advanced_deceptive_coherence_nuance_markers": advanced_deceptive_coherence_analysis.get("nuance_markers", []),

        "emotional_intensity_score": emotional_intensity_analysis["score"],
        "emotional_intensity_markers": emotional_intensity_analysis["markers"],
        "emotional_intensity_interpretation": emotional_intensity_analysis["interpretation"],

        "false_dilemma_nuance_count": aristotelian_fallacies["false_dilemma"].get("nuance_count", 0),
        "false_dilemma_nuance_markers": aristotelian_fallacies["false_dilemma"].get("nuance_markers", []),

        "reported_speech_score": reported_speech["score"],
        "reported_speech_ratio": reported_speech["ratio"],
        "reported_speech_markers": reported_speech["markers"],
        "reported_speech_interpretation": reported_speech["interpretation"],

        "rhetorical_scores": rhetorical_scores,
        "discourse_type_rhetoric": disc_type_rhetoric,
        "discourse_explanation_rhetoric": disc_explanation_rhetoric,
        "discourse_scores": discourse_scores,
        "emotional_registers": emotional_registers,
        
        "linguistic_trigger_count": ling["trigger_count"],
        "linguistic_pressure_hits": ling["rhetorical_pressure"],
        "absolute_claims": ling["absolute_claims"],
        "vague_authority": ling["vague_authority"],
        "dramatic_framing": ling["dramatic_framing"],
        "lack_of_nuance": ling["lack_of_nuance"],
        "political_pattern_score": political_pattern_score,
        "political_results": political_results,
        "matched_terms": matched_terms,
        "rhetorical_pressure": 0,
        "V": V,
        "R": R,
        "improved": improved,
        "source_quality": source_quality,
        "avg_claim_risk": avg_claim_risk,
        "avg_claim_verifiability": avg_claim_verifiability,
        "HFS": HFS,
        "OC": OC,
        "ID": ID,
        "discursive_pressure": discursive_pressure,
        "deceptive_coherence": deceptive_coherence,
        "deceptive_coherence_label": deceptive_label,
        "final_credibility_score": final_credibility_score,
        "final_verdict": verdict,
        "hard_fact_score": hard_fact_score,
        "analogical_reasoning_score": analogical_reasoning_score,
        "verdict": verdict,
        "profil_solidite": verdict,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "claims": claims,
        "inference_patterns": inference_patterns,
        "syllogisms": syllogisms,
        "enthymemes": enthymemes,
        "fallacies": fallacies,

        "syllogism_signal": syllogism_signal,
        "syllogism_label": syllogism_label,
        "enthymeme_signal": enthymeme_signal,
        "enthymeme_label": enthymeme_label,
        "fallacy_signal": fallacy_signal,
        "fallacy_label": fallacy_label,
        "cherry_picking_score": cherry_picking_analysis["score"],
        "cherry_picking_markers": cherry_picking_analysis["matches"],
        "cherry_picking_omission_markers": cherry_picking_analysis["omission_markers"],
        "cherry_picking_interpretation": cherry_picking_analysis["interpretation"],

        "red_flags": [flag["name"] for flag in penalties["flags"]]
        + [flag["name"] for flag in mecroyance_penalties["flags"]],

        "weighted_red_flags": penalties["flags"] + mecroyance_penalties["flags"],

        "credibility_penalty_total": total_credibility_penalty,
        "lie_boost_total": total_lie_boost,

        "mecroyance_penalty_details": mecroyance_penalties,

        "deceptive_coherence": deceptive_coherence,
        "deceptive_coherence_label": deceptive_label,      

        "drift_mecroyance": drifts["drift_mecroyance"],
        "drift_pseudo_savoir": drifts["drift_pseudo_savoir"],
        "drift_intuition_dogmatique": drifts["drift_intuition_dogmatique"],

        "G_drift": round(G_drift, 3),
        "N_drift": round(N_drift, 3),
        "D_drift": round(D_drift, 3),
        
        "global_cognitive_drift": drifts["global_cognitive_drift"],
        "cognitive_drift_interpretation": drifts["cognitive_drift_interpretation"],

        "conceptual_domains": conceptual_domains,
        "conceptual_terms": conceptual_terms,
    }
    
    result["rhetorical_pressure"] = compute_rhetorical_pressure(result)
    
    modern_propaganda = compute_modern_propaganda_score(result)
    
    result["propaganda_score"] = modern_propaganda["score"]
    result["propaganda_interpretation"] = modern_propaganda["interpretation"]
    
    emotional_intensity_analysis = compute_emotional_intensity(result)
    
    result["emotional_intensity_score"] = emotional_intensity_analysis["score"]
    result["emotional_intensity_markers"] = emotional_intensity_analysis["markers"]
    result["emotional_intensity_interpretation"] = emotional_intensity_analysis["interpretation"]

    normative_analysis = detect_normative_charges(text)
    
    result["normative_charge_score"] = normative_analysis["score"]
    result["normative_score"] = normative_analysis["score"]
    
    result["normative_terms"] = normative_analysis["normative_terms"]
    result["normative_judgment_markers"] = normative_analysis["judgment_markers"]
    result["normative_interpretation"] = normative_analysis["interpretation"]

    result["strong_certainty_hedge_count"] = strong_certainty_analysis.get("hedge_count", 0)
    result["strong_certainty_hedge_markers"] = strong_certainty_analysis.get("hedge_markers", [])

    # Sécurité asymétrie argumentative
    if result.get("argument_attack_count", 0) == 0:
        result["argument_asymmetry_score"] = 0.0
        result["argument_asymmetry_interpretation"] = "Aucune rhétorique d’attaque dominante détectée."

    # -----------------------------
    # Cherry Picking
    # -----------------------------
    cherry_picking = detect_cherry_picking(article)
    
    result["cherry_picking_score"] = cherry_picking["score"]
    result["cherry_picking_markers"] = cherry_picking["markers"]
    result["cherry_picking_matches"] = cherry_picking["matches"]
    result["cherry_picking_omission_markers"] = cherry_picking["omission_markers"]
    result["cherry_picking_structural_markers"] = cherry_picking["structural_markers"]
    result["cherry_picking_interpretation"] = cherry_picking["interpretation"]
    
    # Modulation contextuelle selon le type de discours
    result = apply_discourse_modifiers(result)
    
    result = classify_cognitive_regime(result)
    
    bonus = compute_cognitive_bonus(result)
    result.update(bonus)

    # -----------------------------
    # Indice de baratinage
    # -----------------------------
    baratinage = compute_baratinage_score(result)
    result.update(baratinage)
    
    # -----------------------------
    # Indice d’omission stratégique
    # -----------------------------
    omission = compute_omission_score(result)
    result.update(omission)
    
    # -----------------------------
    # Effet placebo étendu
    # -----------------------------
    placebo = compute_extended_placebo_effect(result)
    result.update(placebo)

    # -----------------------------
    # Cerveau DOXA
    # -----------------------------
    # brain_indices = compute_brain_indices(result)
    # result.update(brain_indices)
    
    result["doxa_brain"] = compute_doxa_brain(result)
    result.update(result["doxa_brain"])

    # -----------------------------
    # Modérateur discours rapporté / citations
    # -----------------------------
    reported_speech_score = result.get("reported_speech_score", 0)

    reported_speech_reduction = 1 - min(reported_speech_score * 0.35, 0.35)

    for key in [
        "propaganda_score",
        "normative_score",
        "certainty_score",
        "binary_opposition_score",
        "threat_amplification_score",
        "doxic_rigidity_score",
    ]:
        result[key] = round(result.get(key, 0) * reported_speech_reduction, 3)
        
    result["reported_speech_reduction"] = round(reported_speech_reduction, 3)

    # -----------------------------
    # Pénalité des jauges affichées
    # -----------------------------
    display_gauge_penalty = compute_display_gauge_penalty(result)
    result["display_gauge_penalty"] = display_gauge_penalty
    
    # On ajoute les jauges affichées au total général
    total_credibility_penalty = round(
        total_credibility_penalty + display_gauge_penalty,
        2
    )
    
    # -----------------------------
    # Pénalités finales
    # -----------------------------
    result["credibility_penalty"] = total_credibility_penalty
    
    result["penalty_details"] = {
        "red_flag_penalties": penalties,
        "mecroyance_penalties": mecroyance_penalties,
        "display_gauge_penalty": display_gauge_penalty,
    }
    
    result["penalty_index"] = total_credibility_penalty
    
    result["final_credibility_score"] = round(
        max(0, result["hard_fact_score"] - total_credibility_penalty),
        1
    )
    
    result["hard_fact_score_penalized"] = result["final_credibility_score"]
    
    result["improved_penalized"] = round(
        max(0, result["improved"] - total_credibility_penalty),
        1
    )

    # -----------------------------
    # Ancrage au réel
    # -----------------------------
    
    real_anchor = detect_real_anchor(text, result)
    result.update(real_anchor)
    
    # -----------------------------
    # Bonus cognitif
    # -----------------------------
    
    bonus = compute_cognitive_bonus(result)
    result.update(bonus)
    
    # -----------------------------
    # Cerveau DOXA FINAL
    # -----------------------------
    
    brain = compute_brain_indices(result)
    result.update(brain)
    
    result["doxa_brain"] = compute_doxa_brain(result)
    result.update(result["doxa_brain"])
    
    return result

# -----------------------------
# Corroboration
# -----------------------------
def extract_key_sentences_for_corroboration(text: str, max_sentences: int = 5) -> List[str]:
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 40]
    scored = []
    for s in sentences:
        score = 0
        if re.search(r"\d+", s):
            score += 2
        if re.search(r"\d{4}|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre", s, re.I):
            score += 2
        if re.search(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|[A-Z]{2,}", s):
            score += 2
        if any(word in s.lower() for word in [
            "selon", "affirme", "déclare", "rapport", "étude",
            "expert", "source", "publié", "annonce", "confirme", "révèle"
        ]):
            score += 1
        if any(word in s.lower() for word in [
            "absolument", "certain", "jamais", "toujours",
            "incontestable", "choc", "scandale", "révolution", "urgent"
        ]):
            score += 1
        scored.append((score, s))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [s for _, s in scored[:max_sentences]]


def build_search_query_from_claim(claim: str) -> str:
    claim = re.sub(r"[^\w\s%\-]", " ", claim)
    claim = re.sub(r"\s+", " ", claim).strip()
    words = claim.split()
    important_words = [w for w in words if len(w) > 3][:12]
    return " ".join(important_words)


def extract_claim_features(claim: str) -> Dict:
    numbers = re.findall(r"\d+(?:[.,]\d+)?%?", claim)
    years = re.findall(r"\b(?:19|20)\d{2}\b", claim)
    proper_names = re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+|[A-Z]{2,}", claim)
    words = re.findall(r"\b\w+\b", claim.lower())
    stopwords = {
        "les", "des", "une", "dans", "avec", "pour", "être", "sont", "mais",
        "plus", "comme", "nous", "vous", "sur", "par", "est", "ont", "aux",
        "du", "de", "la", "le", "un", "et", "ou", "en", "à", "au", "ce",
        "ces", "ses", "son", "sa", "qui", "que", "quoi", "dont", "ainsi", "alors",
    }
    keywords = [w for w in words if len(w) > 4 and w not in stopwords]
    return {
        "numbers": list(set(numbers)),
        "years": list(set(years)),
        "proper_names": list(set(proper_names)),
        "keywords": list(dict.fromkeys(keywords))[:12],
    }


def score_match_between_claim_and_result(claim: str, result_text: str) -> Dict:
    features = extract_claim_features(claim)
    rt = result_text.lower()
    number_hits = sum(1 for n in features["numbers"] if n.lower() in rt)
    year_hits = sum(1 for y in features["years"] if y.lower() in rt)
    proper_name_hits = sum(1 for p in features["proper_names"] if p.lower() in rt)
    keyword_hits = sum(1 for k in features["keywords"] if k.lower() in rt)

    score = 0.0
    score += number_hits * 3
    score += year_hits * 2
    score += proper_name_hits * 3
    score += min(keyword_hits, 5) * 1.2

    contradiction_markers = [
        "faux", "trompeur", "incorrect", "inexact",
        "démenti", "réfuté", "aucune preuve",
    ]
    contradiction_signal = any(marker in rt for marker in contradiction_markers)

    return {
        "score": round(score, 1),
        "number_hits": number_hits,
        "year_hits": year_hits,
        "proper_name_hits": proper_name_hits,
        "keyword_hits": keyword_hits,
        "contradiction_signal": contradiction_signal,
    }


def classify_corroboration(matches: List[Dict]) -> str:
    if not matches:
        return "insufficient"

    best_score = max(m["match_score"]["score"] for m in matches)
    contradiction_count = sum(1 for m in matches if m["match_score"]["contradiction_signal"])
    strong_matches = sum(1 for m in matches if m["match_score"]["score"] >= 8)
    medium_matches = sum(1 for m in matches if 4 <= m["match_score"]["score"] < 8)

    if strong_matches >= 2 and contradiction_count == 0:
        return "corroborated"
    if best_score >= 8 and contradiction_count >= 1:
        return "mixed"
    if medium_matches >= 1 or best_score >= 4:
        return "mixed"
    return "not_corroborated"


def display_corroboration_verdict(code: str) -> str:
    if code == "corroborated":
        return f"🟢 {T['corroborated']}"
    if code == "mixed":
        return f"🟠 {T['mixed']}"
    if code == "not_corroborated":
        return f"🔴 {T['not_corroborated']}"
    return f"⚪ {T['insufficiently_documented']}"


def corroborate_claims(text: str, max_claims: int = 5, max_results_per_claim: int = 3) -> List[Dict]:
    claims = extract_key_sentences_for_corroboration(text, max_sentences=max_claims)
    corroboration_results = []

    trusted_domains = [
        "reuters.com", "apnews.com", "bbc.com", "nytimes.com", "theguardian.com",
        "lemonde.fr", "lefigaro.fr", "liberation.fr", "francetvinfo.fr", "lesechos.fr",
        "who.int", "un.org", "worldbank.org", "nature.com", "science.org",
        "elpais.com", "elmundo.es", "dw.com", "spiegel.de",
    ]

    try:
        with DDGS() as ddgs:
            for claim in claims:
                query = build_search_query_from_claim(claim)
    
                search_results = list(ddgs.text(query, max_results=max_results_per_claim * 5))
    
                filtered = []
                for r in search_results:
                    url = r.get("href", "")
                    title = r.get("title", "")
                    body = r.get("body", "")
                    combined_text = f"{title} {body}"
    
                    if any(domain in url for domain in trusted_domains):
                        match_score = score_match_between_claim_and_result(claim, combined_text)
    
                        filtered.append(
                            {
                                "title": title,
                                "url": url,
                                "snippet": body,
                                "match_score": match_score,
                            }
                        )
    
                filtered = sorted(
                    filtered,
                    key=lambda x: x["match_score"]["score"],
                    reverse=True
                )[:max_results_per_claim]
    
                verdict = classify_corroboration(filtered)
    
                corroboration_results.append(
                    {
                        "claim": claim,
                        "query": query,
                        "matches": filtered,
                        "verdict": verdict,
                    }
                )
    
    except Exception as e:
        st.warning(f"Erreur de corroboration : {e}")
    
    return corroboration_results


# -----------------------------
# IA helpers
# -----------------------------
@st.cache_data(show_spinner=False)
def generate_ai_summary(article_text: str, result: Dict, max_chars: int = 7000) -> str:
    if client is None:
        return ""

    short_text = article_text[:max_chars]
    claims_preview = []
    for c in result.get("claims", [])[:8]:
        claims_preview.append(
            {
                "affirmation": c.text,
                "statut": c.status,
                "verifiabilite": c.verifiability,
                "risque": c.risk,
                "has_number": c.has_number,
                "has_date": c.has_date,
                "has_named_entity": c.has_named_entity,
                "has_source_cue": c.has_source_cue,
            }
        )

    prompt = f"""
Tu es un assistant de lecture critique rigoureux.

Ta tâche :
1. Résumer le profil global de crédibilité du texte.
2. Expliquer la différence entre plausibilité structurelle et robustesse factuelle.
3. Identifier les 3 principales forces.
4. Identifier les 3 principales fragilités.
5. Terminer par un verdict prudent.

Contraintes :
- Sois clair, concis et concret.
- N’invente aucun fait.
- N’affirme pas avec certitude qu’un texte est vrai ou faux sans justification solide.
- Appuie-toi sur les métriques heuristiques ci-dessous.

Analyse heuristique :
{json.dumps({
    'G': result.get('G'),
    'N': result.get('N'),
    'D': result.get('D'),
    'M': result.get('M'),
    'V': result.get('V'),
    'R': result.get('R'),
    'hard_fact_score': result.get('hard_fact_score'),
    'verdict': result.get('verdict'),
    'strengths': result.get('strengths', []),
    'weaknesses': result.get('weaknesses', []),
    'claims': claims_preview,
    'red_flags': result.get('red_flags', []),
}, ensure_ascii=False, indent=2)}

Texte à analyser :
{short_text}
"""

    try:
        response = client.responses.create(model="gpt-4o", input=prompt)
        return response.output_text.strip()
    except Exception as e:
        return f"Erreur IA : {e}"
        
@st.cache_data(show_spinner=False, ttl=1800)
def analyze_multiple_articles(keyword: str, max_results: int = 10) -> List[Dict]:
    articles = search_articles_by_keyword(keyword, max_results)
    results = []

    for art in articles:
        try:
            full_text = extract_article_from_url(art["url"])

            if not full_text or len(full_text.strip()) <= 120:
                continue

            analysis = analyze_article(full_text)

            results.append(
                {
                    "Source": art["source"],
                    "Titre": art["title"],
                    "Score classique": analysis["M"],
                    "Hard Fact Score": analysis["hard_fact_score"],
                    "Verdict": analysis["verdict"],
                    "URL": art["url"],
                }
            )

        except Exception as e:
            import traceback
            st.warning(f"Article ignoré : {type(e).__name__} — {e}")
            st.code(traceback.format_exc())
            continue

    return results 
    
@st.cache_data(show_spinner=False, ttl=1800)
def fetch_text_for_textarea(url: str) -> str:
    try:
        text = extract_article_from_url(url)
        text = (text or "").strip()

        if not text:
            return ""

        # filtre page parasite
        noise = detect_web_noise(text)

        if noise["is_noise"]:
            return ""

        return text

    except Exception:
        return ""

# =============================
# Détection rhétorique interne
# =============================

def contains_term(text: str, term: str) -> bool:
    """
    Détecte un mot ou une expression sans faux positif grossier.
    Exemple : détecte 'corrompu' dans 'corrompus' ou 'corrompues'.
    """
    t = text.lower()
    term = term.lower().strip()

    pattern = r"\b" + re.escape(term) + r"\w*\b"
    return re.search(pattern, t) is not None


def count_markers(text: str, markers: list) -> int:
    return sum(1 for m in markers if contains_term(text, m))


def compute_performative_coherence(text: str) -> float:
    sentences = [
        s.strip()
        for s in re.split(r"[.!?;:]+", text)
        if len(s.strip()) > 8
    ]

    if len(sentences) < 3:
        return 0.0

    # Répétitions de débuts de phrases
    starts = []
    for s in sentences:
        words = s.lower().split()
        if len(words) >= 2:
            starts.append(" ".join(words[:2]))

    repeated_starts = len(starts) - len(set(starts))

    # Connecteurs d’équilibre / opposition
    balance_markers = [
        "mais", "pourtant", "cependant", "alors que",
        "tandis que", "d'un côté", "de l'autre",
        "non seulement", "mais encore"
    ]

    balance_count = count_markers(text, balance_markers)

    # Structures binaires / symétriques simples
    symmetry_count = len(re.findall(
        r"\b(de|du|des|la|le|les)\s+\w+\s+(et|ou)\s+\b(de|du|des|la|le|les)\s+\w+",
        text.lower()
    ))

    raw = repeated_starts + balance_count + symmetry_count
    
    score = min(raw / 6, 1.0)
    
    encyclopedic_markers = [
        "is defined as",
        "refers to",
        "this article is about",
        "see also",
        "references",
        "citations",
        "background",
        "analysis",
        "according to",
        "scholars",
        "concept",
        "theory",
    ]
    
    encyclopedic_hits = sum(
        1 for m in encyclopedic_markers
        if m in text.lower()
    )
    
    if encyclopedic_hits >= 4:
        score *= 0.55
    
    return round(score, 3)

def compute_cognitive_compression(text: str) -> float:
    words = re.findall(r"\b[\wà-ÿ'-]+\b", text.lower())
    sentences = [
        s.strip()
        for s in re.split(r"[.!?;:]+", text)
        if len(s.strip()) > 5
    ]

    if not words or not sentences:
        return 0.0

    connectors = [
        "car", "parce que", "puisque", "donc", "ainsi", "cependant",
        "pourtant", "mais", "or", "en effet", "toutefois", "néanmoins",
        "par conséquent", "dès lors", "alors"
    ]

    connector_count = count_markers(text, connectors)

    avg_sentence_len = len(words) / max(len(sentences), 1)

    short_sentence_ratio = sum(
        1 for s in sentences
        if len(s.split()) <= 8
    ) / len(sentences)

    lexical_density = len([
        w for w in words
        if w not in STOPWORDS
    ]) / len(words)

    low_connector_ratio = 1 - min(connector_count / max(len(sentences), 1), 1)

    score = (
        lexical_density * 0.45
        + short_sentence_ratio * 0.25
        + low_connector_ratio * 0.30
    )

    return round(min(score, 1.0), 3)

def compute_rhetorical_saturation(text: str) -> float:
    t = text.lower()

    emotional_markers = [
        "catastrophe", "chaos", "effondrement", "urgence",
        "historique", "terrible", "massif", "dramatique",
        "grave", "dangereux", "inacceptable", "scandale"
    ]

    repetition_markers = [
        "toujours", "jamais", "encore", "sans cesse",
        "tout", "rien", "absolument", "totalement"
    ]

    encyclopedic_markers = [
        "is defined as",
        "refers to",
        "this article is about",
        "see also",
        "references",
        "citations",
        "background",
        "analysis",
        "according to",
        "scholars",
        "concept",
        "theory",
    ]

    exclamation_count = text.count("!")

    emotional_score = count_markers(t, emotional_markers)
    repetition_score = count_markers(t, repetition_markers)

    accumulation_score = sum(
        1 for s in re.split(r"[.!?]", text)
        if s.count(",") >= 4
    )

    raw = (
        emotional_score * 1.2
        + repetition_score
        + accumulation_score
        + exclamation_count * 0.5
    )

    score = min(raw / 14, 1.0)

    encyclopedic_hits = sum(
        1 for m in encyclopedic_markers
        if m in t
    )

    if encyclopedic_hits >= 4:
        score *= 0.45

    return round(score, 3)

def compute_dissimulation_attenuation(text: str) -> float:
    t = text.lower()

    attenuation_markers = [
        "incident",
        "ajustement",
        "réorganisation",
        "dommages collatéraux",
        "mesure exceptionnelle",
        "situation complexe",
        "contexte difficile",
        "malheureusement",
        "certains effets",
        "quelques problèmes",
        "cas isolés",
        "nécessaire adaptation",
        "mesure temporaire",
        "simple opération",
        "simple procédure",
        "sans impact majeur",
        "limité",
        "partiel",
        "modéré",
        "encadré"
    ]

    euphemism_markers = [
        "plan social",
        "optimisation",
        "rationalisation",
        "flexibilisation",
        "réduction d'effectifs",
        "intervention",
        "neutralisation",
        "pacification"
    ]

    raw = (
        count_markers(t, attenuation_markers)
        + count_markers(t, euphemism_markers) * 1.4
    )

    return round(min(raw / 10, 1.0), 3)

def detect_emotional_registers(text: str) -> dict:
    registers = {
        "peur": [
            "peur", "crainte", "menace", "danger", "risque", "panique",
            "angoisse", "inquiétude", "insécurité", "catastrophe"
        ],
        "colere": [
            "colère", "scandale", "inacceptable", "honte", "trahison",
            "corrompu", "mensonge", "abus", "révolte", "indignation"
            "domination", "confiscation", "contrôle", "censure",
            "verrouillé", "défiance", "injustice", "oppression",
            "mépris", "trahison", "privilégiée", "corruption"
        ],
        "urgence": [
            "immédiatement", "urgent", "urgence", "avant qu'il ne soit trop tard",
            "il faut agir", "maintenant", "sans délai", "crise majeure"
        ],
        "fatalisme": [
            "inévitable", "tout est perdu", "plus rien", "aucune solution",
            "condamné", "effondrement", "fin d'un cycle", "basculement"
        ],
        "victimisation": [
            "victimes", "abandonnés", "méprisés", "humiliés", "opprimés",
            "sacrifiés", "oubliés", "sans défense"
        ],
        "exaltation": [
            "réveil", "libération", "espoir", "victoire", "renaissance",
            "sursaut", "courage", "grandeur", "héroïque"
        ],
    }

    scores = {}

    for register, words in registers.items():
        raw = count_markers(text, words)
        scores[register] = round(min(raw / 5, 1.0), 3)

    return scores

def detect_rhetorical_structures(text: str):
    t = text.lower()

    markers = {
        "amplification": [
            "jamais", "toujours", "absolument", "totalement", "inévitable",
            "catastrophe", "effondrement", "historique", "massivement",
            "extrême", "radical", "terrible", "dramatique"
        ],

        "implicite": [
            "on nous cache", "comme par hasard", "tout le monde sait",
            "inutile de rappeler", "je ne dis pas que", "ce n'est pas un hasard",
            "il suffit de voir", "chacun sait",
        
            "derrière", "cache", "les mêmes intérêts", "rien d'accidentel",
            "comme si", "semble", "paraît", "ce qu'ils niaient",
            "on nous explique", "faire confiance", "ouvrir les yeux",
        
            *CAUSALITE_IMPLICITE,
            *IDEOLOGICAL_PREMISE_MARKERS,
            *IDEOLOGICAL_FRAMING_PATTERNS,
        ],
        
            "soupcon_systemique": [
            "on nous cache",
            "comme par hasard",
            "les mêmes intérêts",
            "ce n'est pas un hasard",
            "ouvrir les yeux",
            "vérité cachée",
            "les médias mentent",
            "les élites corrompues",
            "système",
            "manipulation",
            "contrôle",
            "propagande",
            "mensonge",
            "ils savaient",
            "ce qu'ils niaient",
            "rien d'accidentel",
            "derrière",
            "mécanique cachée",
            "agenda",
            "censure"
        ],

        "persuasion": [
            "il faut", "nous devons", "réveillez-vous", "ouvrez les yeux",
            "la vérité", "évidemment", "clairement", "sans aucun doute"
        ],

        "attaque": [
            "traîtres", "corrompus", "vendus", "menteurs", "hypocrites",
            "parasites", "criminels", "complices", "collabos",
            "corrompu", "manipulation", "contrôle", "détruisent",
            "imposent", "culpabilisation", "mensonge", "propagande"
        ],

        "abstraction": [
            "vérité", "être", "néant", "conscience", "raison", "liberté",
            "justice", "essence", "existence", "morale", "âme", "sens"
        ],

        "narrativité": [
            "depuis", "alors", "ensuite", "désormais", "aujourd'hui",
            "hier", "demain", "histoire", "destin", "peuple", "nation"
        ],

        "poeticite": [
            "ombre", "lumière", "silence", "flamme", "ciel", "âme",
            "souffle", "écho", "chant", "nuit", "soleil", "sang"
        ],

        "technicite": [
            "étude", "rapport", "source", "données", "statistique",
            "méthode", "analyse", "pourcentage", "%", "selon", "chiffres"
        ],
        
        "economie_politique": [
            "dette", "dette publique", "déficit", "budget", "budgétaire",
            "croissance", "inflation", "emprunt", "taux", "intérêts",
            "refinancement", "recettes publiques", "dépenses",
            "prélèvements", "fiscalité", "investissement public",
            "politique industrielle", "protection sociale",
            "ressources disponibles", "marges de manœuvre",
            "macroéconomique", "économie", "investisseurs",
            "charge des intérêts", "modèle de société"
        ],
    }
    scores = {}

    for family, words in markers.items():
        raw = count_markers(t, words)
        scores[family] = min(raw / 6, 1.0)

    scores["coherence_performative"] = compute_performative_coherence(text)
    scores["compression_cognitive"] = compute_cognitive_compression(text)
    scores["saturation_rhetorique"] = compute_rhetorical_saturation(text)
    scores["dissimulation_attenuation"] = compute_dissimulation_attenuation(text)

    # =============================
    # Amplification structurelle
    # =============================
    
    compression = scores.get("compression_cognitive", 0)
    
    if compression > 0.45:
    
        # -----------------------------
        # Abstraction
        # -----------------------------
        scores["abstraction"] = min(
            1.0,
            scores.get("abstraction", 0) + compression * 0.35
        )
    
        # -----------------------------
        # Technicité
        # -----------------------------
        scores["technicite"] = min(
            1.0,
            scores.get("technicite", 0) + compression * 0.45
        )
    
        # -----------------------------
        # Cohérence performative
        # -----------------------------
        scores["coherence_performative"] = min(
            1.0,
            scores.get("coherence_performative", 0) + compression * 0.30
        )
    
        # -----------------------------
        # Scientificité rhétorique
        # -----------------------------
        scores["scientificite_rhetorique"] = min(
            1.0,
            scores.get("scientificite_rhetorique", 0) + compression * 0.40
        )
    
        # -----------------------------
        # Saturation rhétorique légère
        # -----------------------------
        scores["saturation_rhetorique"] = min(
            1.0,
            scores.get("saturation_rhetorique", 0) + compression * 0.12
        )
    
    # =========================================================
    # Comptage des nouveaux régimes discursifs
    # =========================================================
    
    encyclopedic_count = sum(
        1 for m in ENCYCLOPEDIC_MARKERS if contains_term(t, m)
    )
    
    definition_count = sum(
        1 for m in DEFINITION_MARKERS if contains_term(t, m)
    )
    
    geopolitical_count = sum(
        1 for m in GEOPOLITICAL_MARKERS if contains_term(t, m)
    )
    
    ecological_count = sum(
        1 for m in ECOLOGICAL_MARKERS if contains_term(t, m)
    )
    
    social_count = sum(
        1 for m in SOCIAL_MARKERS if contains_term(t, m)
    )
    
    biographical_count = sum(
        1 for m in BIOGRAPHICAL_MARKERS if contains_term(t, m)
    )
    
    fiction_count = sum(
        1 for m in FICTION_MARKERS if contains_term(t, m)
    )
    
    mythic_count = sum(
        1 for m in MYTHIC_MARKERS if contains_term(t, m)
    )
    scores["encyclopedique"] = min(encyclopedic_count * 0.12, 1.0)
    scores["definitionnel"] = min(definition_count * 0.12, 1.0)
    scores["geopolitique"] = min(geopolitical_count * 0.12, 1.0)
    scores["ecologique"] = min(ecological_count * 0.12, 1.0)
    scores["social"] = min(social_count * 0.12, 1.0)
    scores["biographique"] = min(biographical_count * 0.12, 1.0)
    scores["fictionnel"] = min(fiction_count * 0.12, 1.0)
    scores["mythique"] = min(mythic_count * 0.12, 1.0)

    # =====================================================
    # Facteur de discours rapporté / documentaire
    # =====================================================
    
    reported_discourse_factor = (
        scores.get("reported_speech_score", 0)
        + scores.get("encyclopedique", 0)
        + scores.get("definitionnel", 0)
        + scores.get("journalistique", 0) * 0.5
    )
    
    reported_discourse_factor = min(
        reported_discourse_factor / 3,
        1.0
    )
    
    scores["reported_discourse_factor"] = round(
        reported_discourse_factor,
        3
    )
    # =====================================================
    # Contrepoids : encyclopédique mais fortement orienté
    # =====================================================
    
    orientation_pressure = (
        scores.get("attaque", 0)
        + scores.get("soupcon_systemique", 0)
        + scores.get("amplification", 0)
        + scores.get("implicite", 0)
    )
    
    if orientation_pressure > 0.55:
        reported_discourse_factor *= 0.45
    elif orientation_pressure > 0.35:
        reported_discourse_factor *= 0.65
    
    reported_discourse_factor = round(reported_discourse_factor, 3)
    scores["reported_discourse_factor"] = reported_discourse_factor

    # =====================================================
    # Réduction des faux positifs idéologiques
    # =====================================================
    
    reduction = reported_discourse_factor
    
    for key, factor in {
        "propaganda_score": 0.45,
        "rhetorical_pressure": 0.35,
        "conspirationniste": 0.55,
        "pamphlétaire": 0.50,
        "saturation_rhetorique": 0.30,
    }.items():
    
        if key in scores:
            scores[key] *= (1 - reduction * factor)
            scores[key] = round(scores[key], 3)

    # =====================================================
    # Réduction structurelle documentaire
    # =====================================================
    
    for key, factor in {
        "coherence_performative": 0.35,
        "compression_cognitive": 0.25,
        "soupcon_systemique": 0.45,
        "implicite": 0.30,
        "attaque": 0.25,
        "amplification": 0.25,
    }.items():
    
        if key in scores:
            scores[key] *= (1 - reduction * factor)
            scores[key] = round(scores[key], 3)

    return scores

# =============================
# Type de discours enrichi
# =============================

def detect_discourse_type_from_rhetoric(text: str, rhetorical_scores: dict):
    scores = {
        "politique": 0,
        "pamphlétaire": 0,
        "philosophique": 0,
        "religieux": 0,
        "poétique": 0,
        "argumentatif": 0,
        "scientifique": 0,
        "conspirationniste": 0,
        "journalistique": 0,
        "technocratique": 0,
        "economie_politique": 0,
    
        # Nouveaux régimes
        "encyclopedique": 0,
        "definitionnel": 0,
        "geopolitique": 0,
        "ecologique": 0,
        "social": 0,
        "biographique": 0,
        "fictionnel": 0,
        "mythique": 0,
    }

    scores["pamphlétaire"] += rhetorical_scores.get("attaque", 0) * 1.6
    scores["pamphlétaire"] += rhetorical_scores.get("amplification", 0) * 0.7
    scores["pamphlétaire"] += rhetorical_scores.get("coherence_performative", 0) * 0.4
    scores["pamphlétaire"] += rhetorical_scores.get("saturation_rhetorique", 0) * 0.45

    scores["politique"] += rhetorical_scores.get("narrativité", 0) * 0.8
    scores["politique"] += rhetorical_scores.get("attaque", 0) * 0.7
    scores["politique"] += rhetorical_scores.get("saturation_rhetorique", 0) * 0.3
    scores["politique"] += rhetorical_scores.get("dissimulation_attenuation", 0) * 0.5

    scores["economie_politique"] += rhetorical_scores.get("economie_politique", 0) * 1.8
    scores["economie_politique"] += rhetorical_scores.get("technicite", 0) * 0.5
    scores["economie_politique"] += rhetorical_scores.get("coherence_performative", 0) * 0.3
    scores["economie_politique"] += rhetorical_scores.get("abstraction", 0) * 0.2

    # =====================================================
    # Philosophique
    # =====================================================
    
    if (
        rhetorical_scores.get("implicite", 0) > 0.15
        or rhetorical_scores.get("abstraction", 0) > 0.45
    ):
    
        scores["philosophique"] += rhetorical_scores.get("abstraction", 0) * 0.9
        scores["philosophique"] += rhetorical_scores.get("implicite", 0) * 1.1
        scores["philosophique"] += rhetorical_scores.get("compression_cognitive", 0) * 0.02

    scores["poétique"] += rhetorical_scores.get("poeticite", 0) * 1.4
    scores["poétique"] += rhetorical_scores.get("abstraction", 0) * 0.4
    scores["poétique"] += rhetorical_scores.get("coherence_performative", 0) * 0.10

    scores["scientifique"] += rhetorical_scores.get("technicite", 0) * 1.1
    scores["scientifique"] += rhetorical_scores.get("dissimulation_attenuation", 0) * 0.3

    scores["journalistique"] += rhetorical_scores.get("technicite", 0) * 0.9
    scores["journalistique"] += rhetorical_scores.get("narrativité", 0) * 0.5
    scores["journalistique"] += rhetorical_scores.get("coherence_performative", 0) * 0.3
    scores["journalistique"] += rhetorical_scores.get("saturation_rhetorique", 0) * 0.4

    scores["technocratique"] += rhetorical_scores.get("dissimulation_attenuation", 0) * 1.8
    scores["technocratique"] += rhetorical_scores.get("technicite", 0) * 0.5
    scores["technocratique"] += rhetorical_scores.get("coherence_performative", 0) * 0.2
    scores["technocratique"] += rhetorical_scores.get("compression_cognitive", 0) * 0.2

    scores["conspirationniste"] += rhetorical_scores.get("soupcon_systemique", 0) * 0.6
    scores["conspirationniste"] += rhetorical_scores.get("implicite", 0) * 0.2
    scores["conspirationniste"] += rhetorical_scores.get("amplification", 0) * 0.4
    scores["conspirationniste"] += rhetorical_scores.get("narrativité", 0) * 0.15

    
    if (
        rhetorical_scores.get("soupcon_systemique", 0) > 0.4
        and rhetorical_scores.get("implicite", 0) > 0.4
        and (
            rhetorical_scores.get("attaque", 0) > 0.3
            or rhetorical_scores.get("saturation_rhetorique", 0) > 0.5
        )
    ):
        scores["conspirationniste"] += 0.25

    scores["argumentatif"] += rhetorical_scores.get("technicite", 0) * 0.6
    scores["argumentatif"] += rhetorical_scores.get("persuasion", 0) * 0.6
    scores["argumentatif"] += rhetorical_scores.get("dissimulation_attenuation", 0) * 0.4

    # =====================================================
    # Encyclopédique
    # =====================================================
    
    scores["encyclopedique"] += rhetorical_scores.get("definitionnel", 0) * 0.8
    scores["encyclopedique"] += rhetorical_scores.get("encyclopedique", 0) * 1.8
    scores["encyclopedique"] += rhetorical_scores.get("technicite", 0) * 0.3
    scores["encyclopedique"] += rhetorical_scores.get("coherence_performative", 0) * 0.1
    
    # =====================================================
    # Définitionnel
    # =====================================================
    
    scores["definitionnel"] += rhetorical_scores.get("definitionnel", 0) * 1.1
    
    # =====================================================
    # Géopolitique
    # =====================================================
    
    scores["geopolitique"] += rhetorical_scores.get("geopolitique", 0) * 1.3
    scores["geopolitique"] += rhetorical_scores.get("technicite", 0) * 0.2
    
    # =====================================================
    # Écologique
    # =====================================================
    
    scores["ecologique"] += rhetorical_scores.get("ecologique", 0) * 1.3
    scores["ecologique"] += rhetorical_scores.get("amplification", 0) * 0.15
    
    # =====================================================
    # Social
    # =====================================================
    
    scores["social"] += rhetorical_scores.get("social", 0) * 1.2
    scores["social"] += rhetorical_scores.get("narrativité", 0) * 0.1
    
    # =====================================================
    # Biographique
    # =====================================================
    
    scores["biographique"] += rhetorical_scores.get("biographique", 0) * 1.4
    
    # =====================================================
    # Fictionnel
    # =====================================================
    
    if (
        rhetorical_scores.get("poeticite", 0) > 0.15
        or rhetorical_scores.get("narrativité", 0) > 0.30
    ):
    
        scores["fictionnel"] += rhetorical_scores.get("fictionnel", 0) * 0.7
        scores["fictionnel"] += rhetorical_scores.get("poeticite", 0) * 0.15
    
    # =====================================================
    # Mythique
    # =====================================================
    
    scores["mythique"] += rhetorical_scores.get("mythique", 0) * 1.3
    scores["mythique"] += rhetorical_scores.get("abstraction", 0) * 0.15

    scores["philosophique"] += rhetorical_scores.get("compression_cognitive", 0) * 0.03
    scores["pamphlétaire"] += rhetorical_scores.get("compression_cognitive", 0) * 0.3
    scores["poétique"] += rhetorical_scores.get("compression_cognitive", 0) * 0.05
    
    # Sécurité : pas de pamphlétaire fort sans agressivité réelle
    attack = rhetorical_scores.get("attaque", 0)
    anger = rhetorical_scores.get("colere", 0)
    suspicion = rhetorical_scores.get("soupcon_systemique", 0)
    
    if attack < 0.15 and anger < 0.15 and suspicion < 0.15:
        scores["pamphlétaire"] = round(scores["pamphlétaire"] * 0.45, 3)

    # =====================================================
    # Priorité structurelle : encyclopédique / définitionnel
    # =====================================================
    
    encyclopedic_strength = (
        scores.get("encyclopedique", 0)
        + scores.get("definitionnel", 0)
    )
    
    direct_aggression = (
        rhetorical_scores.get("attaque", 0)
        + rhetorical_scores.get("persuasion", 0)
        + rhetorical_scores.get("amplification", 0)
    )
    
    if encyclopedic_strength >= 0.45 and direct_aggression < 0.25:
    
        scores["pamphlétaire"] = round(scores.get("pamphlétaire", 0) * 0.30, 3)
        scores["conspirationniste"] = round(scores.get("conspirationniste", 0) * 0.40, 3)
        scores["politique"] = round(scores.get("politique", 0) * 0.65, 3)
    
        scores["encyclopedique"] = round(scores.get("encyclopedique", 0) * 1.45, 3)
        scores["definitionnel"] = round(scores.get("definitionnel", 0) * 1.25, 3)
        
        scores["encyclopedique"] += rhetorical_scores.get("encyclopedique", 0) * 1.8
        scores["definitionnel"] += rhetorical_scores.get("definitionnel", 0) * 1.6
        scores["geopolitique"] += rhetorical_scores.get("geopolitique", 0) * 1.5
        scores["ecologique"] += rhetorical_scores.get("ecologique", 0) * 1.4
        scores["social"] += rhetorical_scores.get("social", 0) * 1.4
        scores["biographique"] += rhetorical_scores.get("biographique", 0) * 1.5
        scores["fictionnel"] += rhetorical_scores.get("fictionnel", 0) * 1.7
        scores["mythique"] += rhetorical_scores.get("mythique", 0) * 1.6
    

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    dominant, dominant_value = sorted_scores[0]
    secondary, secondary_value = sorted_scores[1]
    
    if dominant_value < 0.15:
        return (
            "Discours indéterminé",
            "Aucune dominante rhétorique claire détectée.",
            scores
        )
    
    # Construction hybride
    if secondary_value >= dominant_value * 0.6:
    
        if dominant == "journalistique" and secondary == "pamphlétaire":
            discourse_label = "Journalistique à coloration polémique"
    
        elif dominant == "journalistique" and secondary == "politique":
            discourse_label = "Journalistique à coloration politique"
    
        elif dominant == "scientifique" and secondary == "technocratique":
            discourse_label = "Scientifique à coloration technocratique"
    
        else:
            discourse_label = f"{dominant.capitalize()} à dominante {secondary}"
    
    else:
        discourse_label = dominant.capitalize()
    
    explanation = (
        f"Dominante détectée par les marqueurs rhétoriques : "
        f"{dominant}."
    )
    
    return discourse_label, explanation, scores

def explain_discourse_profile(result):
    rhetorical = result.get("rhetorical_scores", {})
    discourse = result.get("discourse_scores", {})

    if not rhetorical or not discourse:
        return "Aucun profil discursif détaillé disponible."

    top_rhetorical = sorted(
        rhetorical.items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    top_discourse = sorted(
        discourse.items(),
        key=lambda x: x[1],
        reverse=True
    )[:3]

    rhet_text = ", ".join(
        f"{name.replace('_', ' ').replace('soupcon', 'soupçon').replace('systemique', 'systémique').replace('rhetorique', 'rhétorique')} ({round(score, 2)})"
        for name, score in top_rhetorical
        if score > 0
    )

    disc_text = ", ".join(
        f"{name} ({round(score, 2)})"
        for name, score in top_discourse
        if score > 0
    )

    return (
        f"Le profil dominant repose principalement sur : {rhet_text}. "
        f"Les types discursifs les plus proches sont : {disc_text}."
    )

# =====================================================
# TYPE DE DISCOURS DÉTECTÉ
# =====================================================
def detect_discourse_type(result):

    G = result.get("G", 0)
    N = result.get("N", 0)
    D = result.get("D", 0)
    V = result.get("V", 0)

    rhetorical_pressure = result.get("rhetorical_pressure", 0)
    propaganda = result.get("propaganda_score", 0)
    closure = result.get("cognitive_closure", 0)

    final_score = result.get(
        "final_credibility_score",
        result.get("hard_fact_score", 0)
    )

    domains = result.get("conceptual_domains", {})

    journalistic = domains.get("journalistique", 0)
    philosophical = domains.get("philosophique", 0)
    religious = domains.get("religieux", 0)

    narrative_score = result.get("narrative_score", 0)
    scientific_score = result.get("scientific_simulation_score", 0)
    propaganda_score = result.get("propaganda_score", 0)

    historical_score = domains.get("historique", 0)
    literary_score = domains.get("litteraire", 0)
    scientific_domain = domains.get("scientifique", 0)
    political_score = domains.get("politique", 0)
    geostrategic_score = domains.get("geostrategique", 0)

    # =====================================================
    # A) ROMANESQUE / NARRATIF
    # =====================================================
    if (
        narrative_score >= 0.5
        and G < 4
        and V < 4
    ):
        return (
            "Discours romanesque / narratif",
            "Le texte repose principalement sur une structure narrative ou fictionnelle."
        )

    # =====================================================
    # B) LITTÉRAIRE / POÉTIQUE
    # =====================================================
    if (
        literary_score >= 2
        and rhetorical_pressure < 0.5
    ):
        return (
            "Discours littéraire / poétique",
            "Le texte mobilise principalement une recherche stylistique ou expressive."
        )

    # =====================================================
    # C) HISTORIQUE
    # =====================================================
    if (
        historical_score >= 2
        and G >= 4
    ):
        return (
            "Discours historique",
            "Le texte mobilise principalement des références historiques ou civilisationnelles."
        )

    # =====================================================
    # D) SCIENTIFIQUE
    # =====================================================
    if (
        scientific_domain >= 2
        and G >= 5
        and V >= 5
    ):
        return (
            "Discours scientifique",
            "Le texte mobilise principalement des références scientifiques ou analytiques."
        )

    # =====================================================
    # E) VULGARISATION SCIENTIFIQUE
    # =====================================================
    if (
        scientific_domain >= 1
        and scientific_score >= 0.2
    ):
        return (
            "Discours de vulgarisation scientifique",
            "Le texte adopte une présentation scientifique simplifiée destinée à expliquer ou convaincre."
        )

    # =====================================================
    # F) POLITIQUE / IDÉOLOGIQUE
    # =====================================================
    if (
        political_score >= 2
        or propaganda_score >= 0.35
    ):
        return (
            "Discours politique / idéologique",
            "Le texte cherche à orienter une lecture sociale, culturelle ou politique du réel."
        )

    # =====================================================
    # 1) PROPAGANDE (cas extrême)
    # =====================================================
    if (
        propaganda >= 0.65
        and rhetorical_pressure >= 0.45
        and closure >= 0.45
    ):
        return (
            "Discours propagandiste",
            "Le texte combine pression rhétorique, simplification narrative et fermeture cognitive."
        )

    # =====================================================
    # 2) RELIGIEUX
    # =====================================================
    if religious >= 2:
        return (
            "Discours religieux",
            "Le texte mobilise un registre religieux, spirituel ou doctrinal."
        )
    # =====================================================
    # 3) Geostrategic
    # =====================================================
    if geostrategic_score >= 4 or (
        political_score >= 3 and geostrategic_score >= 2
    ):
        return (
            "Discours politico-stratégique",
            "Le texte développe principalement une vision géopolitique, institutionnelle ou stratégique."
        )

    # =====================================================
    # 4) PHILOSOPHIQUE
    # =====================================================
    if (
        philosophical >= 3
        and rhetorical_pressure < 0.45
        and propaganda < 0.45
    ):
        return (
            "Discours philosophique",
            "Le texte développe principalement une réflexion conceptuelle ou abstraite."
        )

    # =====================================================
    # 5) JOURNALISTIQUE INTERPRÉTATIF
    # =====================================================
    if (
        journalistic >= 2
        and philosophical >= 1
        and V >= 4
    ):
        return (
            "Discours journalistique interprétatif",
            "Le texte combine information, interprétation et lecture analytique."
        )

    # =====================================================
    # 6) JOURNALISTIQUE FACTUEL
    # =====================================================
    if (
        journalistic >= 2
        and G >= 5
        and V >= 5
    ):
        return (
            "Discours journalistique",
            "Le texte présente une structure informative fondée sur des éléments vérifiables."
        )

    # =====================================================
    # 7) FACTUEL
    # =====================================================
    if (
        G >= 6
        and V >= 6
        and final_score >= 13
    ):
        return (
            "Discours factuel",
            "Le raisonnement repose principalement sur des éléments vérifiables."
        )

    # =====================================================
    # PSEUDO-ANALYTIQUE / CIVILISATIONNEL
    # =====================================================
    if (
        result.get("scientific_simulation_score", 0) >= 0.25
        or result.get("causal_overreach_score", 0) >= 0.25
        or result.get("argument_from_nature_score", 0) >= 0.25
        or result.get("false_analogy_score", 0) >= 0.25
        or result.get("generalization_score", 0) >= 0.4
    ):
        return (
            "Discours pseudo-analytique / civilisationnel",
            "Le texte adopte une apparence analytique tout en mobilisant des analogies historiques, des arguments de nature, des généralisations ou des causalités fragiles."
        )

    # =====================================================
    # 8) DISCOURS ORIENTÉ / ALARMISTE
    # =====================================================
    if (
        result.get("threat_amplification_score", 0) >= 0.6
        or result.get("semantic_shift_score", 0) >= 0.6
        or result.get("binary_opposition_score", 0) >= 0.6
        or result.get("false_consensus_score", 0) >= 0.4
    ):
        return (
            "Discours orienté / alarmiste",
            "Le texte mobilise menace, recadrage sémantique, opposition binaire ou consensus supposé pour orienter la lecture."
        )

    # =====================================================
    # 9) PSEUDO-ANALYTIQUE / CIVILISATIONNEL
    # =====================================================
    if (
        result.get("scientific_simulation_score", 0) >= 0.25
        or result.get("causal_overreach_score", 0) >= 0.25
        or result.get("argument_from_nature_score", 0) >= 0.25
        or result.get("false_analogy_score", 0) >= 0.25
    ):
        return (
            "Discours pseudo-analytique / civilisationnel",
            "Le texte adopte une apparence analytique tout en mobilisant des analogies historiques, des arguments de nature ou des causalités fragiles."
        )

    # =====================================================
    # 10) POLÉMIQUE
    # =====================================================
    if (
        rhetorical_pressure >= 0.45
        or D >= 7
    ):
        return (
            "Discours polémique",
            "Le texte présente une forte orientation argumentative ou émotionnelle."
        )

    # =====================================================
    # 11) ANALYTIQUE
    # =====================================================
    if (
        N >= 6
        and rhetorical_pressure < 0.45
    ):
        return (
            "Discours analytique",
            "Le texte développe un raisonnement structuré ou explicatif."
        )

    # =====================================================
    # 12) SPÉCULATIF
    # =====================================================
    if (
        N >= 6
        and G < 4
        and V < 5
    ):
        return (
            "Discours spéculatif",
            "Le texte repose principalement sur des hypothèses ou des généralisations conceptuelles."
        )

    # =====================================================
    # 13) INDÉTERMINÉ
    # =====================================================
    return (
        "Discours indéterminé",
        "Le texte ne présente pas assez d’indices dominants pour être classé clairement."
    )

# =====================================================
# DÉTECTION PAGE WEB PARASITE
# =====================================================

def detect_web_noise(text):
    t = text.lower()

    noise_markers = [
        "accueil", "blogs", "vidéos", "contact", "à propos",
        "se connecter", "s'inscrire", "mot de passe oublié",
        "publier une réponse", "annuler votre réponse",
        "catégories", "recherche", "faire un don",
        "cookies", "politique de confidentialité",
        "google analytics", "centre de confidentialité",
        "dernières petites annonces", "articles liés",
        "partager cet article", "imprimer ou envoyer",
        "voir toutes les annonces", "proposer une annonce",
        "liste des événements", "proposer un événement"
    ]

    hits = sum(1 for marker in noise_markers if marker in t)

    words = re.findall(r"\b[\wà-ÿ'-]+\b", t)
    total_words = len(words)

    sentences = re.split(r"[.!?]+", text)

    real_sentences = [
        s.strip() for s in sentences
        if len(s.strip().split()) >= 8
    ]

    return {
        "hits": hits,
        "total_words": total_words,
        "real_sentences": len(real_sentences),

        # condition améliorée
        "is_noise": hits >= 6 and (
            len(real_sentences) < 8
            or hits / max(total_words,1) > 0.02
        )
    }
# -----------------------------
# Réglages et méthode de recherche
# -----------------------------
with st.expander("⚙️ Réglages et méthode de recherche", expanded=False):
    use_sample = st.button(
        T["load_example"],
        key="settings_load_example"
    )

    show_method = st.toggle(
        T["show_method"],
        value=True,
        key="settings_show_method"
    )

    st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True)

    st.markdown("""
### Principe de sélection des articles — basé sur la formule :
M = (G + N) − D

⚠️ Le système ne classe pas les articles uniquement par popularité ou par mots-clés.
Il privilégie les textes dont la structure argumentative active l’analyse cognitive.

**Textes fortement affirmatifs**  
Les discours très affirmatifs ou rhétoriquement chargés déclenchent davantage de signaux analytiques.

**⚙️ Filtrage automatique**  
**Si 10 textes fortement affirmatifs sont déjà détectés, les articles plus neutres peuvent ne pas apparaître dans l’analyse.

**⬇️ Important**
**Lorsque vous effectuez le chargement d’un article, descendez jusqu’au bloc “Texte chargé” afin de lancer l’analyse.
""")

if "article" not in st.session_state:
    st.session_state.article = SAMPLE_ARTICLE
if "article_source" not in st.session_state:
    st.session_state.article_source = "paste"
if "loaded_url" not in st.session_state:
    st.session_state.loaded_url = ""
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_article" not in st.session_state:
    st.session_state.last_article = ""
if "multi_results" not in st.session_state:
    st.session_state.multi_results = []
if "last_keyword" not in st.session_state:
    st.session_state.last_keyword = ""

if use_sample:
    st.session_state.article = SAMPLE_ARTICLE
    st.session_state.article_source = "paste"
    st.session_state.loaded_url = ""

# -----------------------------
# Analyse multi-articles
# -----------------------------
if not st.session_state.get("direct_search_result_mode"):

    st.subheader(T["topic_section"])
    keyword = st.text_input(T["topic"], placeholder=T["topic_placeholder"])

    if st.button(T["analyze_topic"], key="analyze_topic"):

        if keyword.strip():

            st.warning(
                "⏳ Analyse multi-sources en cours : extraction, parsing et vérification des articles. "
                "Le traitement peut durer entre 10 et 15 secondes pour les textes longs ou "
                "mobilisant de nombreuses jauges heuristiques."
            )

            st.info(T["searching"])

            st.session_state.multi_results = analyze_multiple_articles(
                keyword.strip(),
                max_results=10
            )

            st.session_state.last_keyword = keyword.strip()

        else:
            st.session_state.multi_results = []
            st.warning(T["enter_keyword_first"])

    if st.button("🔄 Réinitialiser la recherche", use_container_width=True):
        st.session_state.multi_results = []
        st.session_state.last_keyword = ""
        st.cache_data.clear()
        st.rerun()

    if st.session_state.get("multi_results"):
        df_multi = pd.DataFrame(st.session_state.multi_results).sort_values("Hard Fact Score", ascending=False)

        st.success(f"{len(df_multi)} {T['articles_analyzed']}")

        st.caption(
            "🔎 Recherche automatique de sources basée sur la formule cognitive M = (G + N) − D."
        )

        if False:
            st.dataframe(df_multi, use_container_width=True, hide_index=True)

        st.markdown("### Examiner les articles trouvés")

        for i, row in df_multi.reset_index(drop=True).iterrows():
            with st.container(border=True):

                st.markdown(f"### {row['Titre']}")
                st.caption(f"{row['Source']}")

                col1, col2 = st.columns(2)

                with col1:
                    st.link_button("🌐 Ouvrir l'article", row["URL"], use_container_width=True)

                with col2:
                    if st.button("📥 Charger pour analyse", key=f"load_article_{i}", use_container_width=True):
                
                        loaded_text = fetch_text_for_textarea(row["URL"])
                
                        if loaded_text and not detect_web_noise(loaded_text)["is_noise"]:
                
                            st.session_state.article = loaded_text
                            st.session_state.article_source = "search"
                            st.session_state.loaded_url = row["URL"]
                            st.session_state.loaded_article_title = row["Titre"]
                            st.session_state.loaded_article_index = i
                
                            st.success("Article chargé.")
                            st.rerun()
                
                        else:
                            st.warning("Impossible d'extraire un vrai corps d’article exploitable.")

    elif st.session_state.get("last_keyword"):
        st.warning(T["no_exploitable_articles_found"])

# =============================
# Chargement d’une page publique par URL
# =============================
st.markdown("### Analyser une page publique par URL")
st.caption(
    "Collez le lien d’un article, d’un post X, LinkedIn, Medium ou toute autre page publique."
)

page_url = st.text_input(
    "Lien de la page publique à analyser",
    key="page_url_input"
)

if st.button("📥 Charger la page", use_container_width=True):

    if page_url.strip():

        texte_page = extract_article_from_url(page_url.strip())

        if texte_page:
            st.session_state.article = texte_page
            st.session_state.article_source = "page_url"
            st.session_state.loaded_url = page_url.strip()
            st.session_state.loaded_article_title = "Page publique"
            st.session_state.article_loaded_from_search = True

            st.success("Page chargée. Vous pouvez l’analyser juste ici.")
            st.rerun()

        else:
            st.warning(
                "Impossible de récupérer automatiquement le texte. "
                "La page bloque peut-être l’accès ou ne contient pas de texte exploitable. "
                "Copiez-collez alors le texte directement dans la zone d’analyse."
            )

    else:
        st.warning("Collez d’abord un lien.")

if (
    st.session_state.get("article_loaded_from_search")
    and st.session_state.get("article_source") == "page_url"
):

    st.markdown("### 📰 Texte chargé")
    st.success("Le texte est prêt à être analysé.")


# =============================
# Mode résultat direct depuis recherche
# =============================
if st.session_state.get("direct_search_result_mode"):

    st.info("Article analysé depuis la recherche. Affichage direct du résultat.")

    if st.button("↩️ Revenir au mode normal", key="back_to_normal_mode", use_container_width=True):
        st.session_state.direct_search_result_mode = False
        st.session_state.selected_article_index = None
        st.rerun()

    result = st.session_state.last_result
    article_for_analysis = st.session_state.last_article

    mode = "Analyse simple"
    analyze_submitted = False

else:

    st.markdown("## Mode d’analyse")

    mode = st.radio(
        "Choisissez le mode",
        ["Analyse simple", "Débat dynamique"],
        horizontal=True,
        key="mode"
    )
# =====================================================
# INITIALISATION ROBUSTE
# =====================================================

if "debate_turns" not in st.session_state:
    st.session_state["debate_turns"] = []

if "pending_debate_transcription" not in st.session_state:
    st.session_state["pending_debate_transcription"] = ""

if "pending_speaker" not in st.session_state:
    st.session_state["pending_speaker"] = "Participant A"

if "clear_debate_text_next_run" not in st.session_state:
    st.session_state["clear_debate_text_next_run"] = False

if "pending_editor_version" not in st.session_state:
    st.session_state["pending_editor_version"] = 0


# =====================================================
# SÉLECTEUR PARTICIPANT AVANT MICRO
# =====================================================
if not st.session_state.get("direct_search_result_mode") and mode == "Débat dynamique":

    participant_count = st.selectbox(
        "Nombre de participants",
        [2, 3, 4, 5, 6],
        index=0,
        key="debate_participant_count"
    )

    debate_participants = [
        f"Participant {chr(65 + i)}"
        for i in range(participant_count)
    ]

    st.session_state["debate_participants"] = debate_participants

    st.session_state["debate_speaker_choice"] = st.radio(
        "Participant pour la prochaine intervention",
        debate_participants,
        horizontal=True,
        key="debate_speaker_radio"
    )

if st.session_state.get("direct_search_result_mode"):
    st.markdown("### Analyse sémantique")
    st.caption("Active une lecture du sens des affirmations via un dictionnaire sémantique assisté par IA.")

    if st.button(
        "Activer l’analyse sémantique",
        key="semantic_direct",
        use_container_width=True
    ):
        st.session_state.semantic_mode = True
        st.rerun()

    if st.session_state.get("semantic_mode", False):
        st.success("Analyse sémantique activée.")
    else:
        st.info("Analyse sémantique inactive. La crédibilité globale reste partielle.")

if not st.session_state.get("direct_search_result_mode"):

    # -----------------------------
    # Zone d’analyse
    # -----------------------------
    previous_article = st.session_state.article

    st.markdown("### Zone d’analyse")

    with st.container(border=True):

        st.caption("Collez un texte, chargez une URL, ou dictez directement.")

        # =============================
        # Dictée vocale classique
        # =============================
        if MICRO_AVAILABLE:
            spoken_text = speech_to_text(
                language="fr",
                start_prompt="🎙️ Dicter",
                stop_prompt="⏹️ Stop",
                just_once=True,
                use_container_width=True,
                key="speech_to_text_article"
            )

            if spoken_text:

                if mode == "Analyse simple":
                    st.session_state.article = spoken_text
                    st.session_state.article_source = "voice"
                    st.success("Texte dicté reçu.")
                    st.rerun()

                else:
                    st.session_state["pending_debate_transcription"] = spoken_text
                    st.session_state["pending_speaker"] = st.session_state.get(
                        "debate_speaker_choice",
                        "Participant A"
                    )
                    st.session_state["pending_editor_version"] += 1

                    st.success("Transcription prête.")
                    st.info("Validez la transcription ci-dessous pour l’ajouter au débat.")
                    st.rerun()

        else:
            st.caption("🎙️ Dictée vocale classique indisponible dans cette version.")

        # =============================
        # Dictée vocale mobile
        # =============================
        st.markdown("#### 🎙️ Entrée vocale mobile")
        st.caption("📱 Compatible smartphone / iPhone")

        audio = st.audio_input("Dicter un texte à analyser", key="audio_mobile")

        if audio:
            st.audio(audio)

            if st.button("Transcrire l’audio", use_container_width=True):
                if client is None:
                    st.warning(
                        "Transcription vocale indisponible : clé OpenAI absente ou module OpenAI non installé."
                    )
                else:
                    try:
                        with st.spinner("Transcription en cours..."):
                            audio_bytes = audio.getvalue()

                            transcript = client.audio.transcriptions.create(
                                model="gpt-4o-mini-transcribe",
                                file=("audio.wav", audio_bytes, "audio/wav")
                            )

                        text_transcribed = transcript.text
                        st.session_state["speech_to_text_result"] = text_transcribed

                        if mode == "Analyse simple":
                            st.session_state.article = text_transcribed
                            st.session_state.article_source = "voice"
                            st.success("Texte transcrit et chargé dans la zone d’analyse.")
                            st.info("Texte prêt. Cliquez sur Analyser pour lancer l’analyse.")
                        else:
                            st.session_state["pending_debate_transcription"] = text_transcribed
                            st.session_state["pending_speaker"] = st.session_state.get(
                                "debate_speaker_choice",
                                "Participant A"
                            )
                            st.session_state["pending_editor_version"] += 1

                            st.success("Transcription prête.")
                            st.info("Validez la transcription ci-dessous pour l’ajouter au débat.")
                            st.rerun()

                    except Exception as e:
                        st.error(f"Erreur de transcription : {e}")


# =====================================================
# NETTOYAGE DU CHAMP DÉBAT SI DEMANDÉ
# =====================================================
if not st.session_state.get("direct_search_result_mode"):
    if st.session_state.get("clear_debate_text_next_run"):
        st.session_state["debate_text_input"] = ""
        st.session_state["clear_debate_text_next_run"] = False

    if st.session_state.get("clear_article_next_run"):
        st.session_state["article"] = ""
        st.session_state["clear_article_next_run"] = False


# =====================================================
# FORMULAIRE PRINCIPAL
# =====================================================
if not st.session_state.get("direct_search_result_mode"):

    with st.form("article_form"):

        if mode == "Analyse simple":

            article = st.text_area(
                T["paste"],
                key="article",
                height=220,
                label_visibility="collapsed",
                placeholder=T["paste"]
            )

        else:

            speaker = st.session_state.get("debate_speaker_choice", "Participant A")

            st.info(f"Participant sélectionné : {speaker}")

            debate_text = st.text_area(
                "Intervention du tour",
                key="debate_text_input",
                height=180,
                placeholder="Ajoutez l’intervention du participant..."
            )

        analyze_submitted = st.form_submit_button(
            T["analyze"],
            use_container_width=True
        )

if not st.session_state.get("direct_search_result_mode") and mode == "Analyse simple":

    if st.button("🔄 Rafraîchir le texte", use_container_width=True):

        st.session_state["clear_article_next_run"] = True
        st.session_state["last_result"] = None
        st.session_state["last_article"] = ""
        st.session_state["analysis_done"] = False
        st.session_state["article_source"] = "paste"

        for key in ["loaded_url", "loaded_article_title"]:
            if key in st.session_state:
                del st.session_state[key]

        st.rerun()


# =====================================================
# MODE DÉBAT — TEXTE ÉCRIT MIS EN ATTENTE
# =====================================================
if analyze_submitted and mode == "Débat dynamique":

    if debate_text.strip():

        st.session_state["pending_debate_transcription"] = debate_text.strip()
        st.session_state["pending_speaker"] = speaker
        st.session_state["pending_editor_version"] += 1

        st.info("Intervention prête à vérifier.")
        st.rerun()

    else:
        st.warning("Ajoutez une intervention avant de valider.")


# =====================================================
# VALIDATION TRANSCRIPTION DÉBAT
# =====================================================
if mode == "Débat dynamique" and st.session_state.get("pending_debate_transcription"):

    st.markdown("### Transcription à valider")

    edited_transcription = st.text_area(
        "Corrigez si nécessaire avant validation",
        value=st.session_state["pending_debate_transcription"],
        key=f"pending_debate_transcription_editor_{st.session_state['pending_editor_version']}",
        height=160
    )

    col_val, col_cancel = st.columns(2)

    with col_val:
        if st.button("✅ Valider cette intervention", use_container_width=True):

            if edited_transcription.strip():

                st.session_state["debate_turns"].append({
                    "speaker": st.session_state.get("pending_speaker", "Participant A"),
                    "text": edited_transcription.strip()
                })

                st.session_state["pending_debate_transcription"] = ""
                st.session_state["pending_speaker"] = "Participant A"
                st.session_state["clear_debate_text_next_run"] = True

                st.success("Intervention ajoutée au débat.")
                st.rerun()

            else:
                st.warning("La transcription est vide.")

    with col_cancel:
        if st.button("❌ Annuler", use_container_width=True):

            st.session_state["pending_debate_transcription"] = ""
            st.session_state["pending_speaker"] = "Participant A"
            st.session_state["clear_debate_text_next_run"] = True

            st.rerun()


# =====================================================
# HISTORIQUE COMPLET DU DÉBAT
# =====================================================
if mode == "Débat dynamique" and st.session_state.get("debate_turns"):

    st.markdown("### Historique du débat")

    for i, turn in enumerate(st.session_state["debate_turns"], start=1):

        with st.container(border=True):
            st.markdown(f"**Tour {i} — {turn['speaker']}**")
            st.write(turn["text"])


# =====================================================
# BOUTON RÉINITIALISER LE DÉBAT
# =====================================================
if mode == "Débat dynamique" and st.session_state.get("debate_turns"):

    if st.button("🧹 Réinitialiser le débat", use_container_width=True):

        st.session_state["debate_turns"] = []
        st.session_state["pending_debate_transcription"] = ""
        st.session_state["pending_speaker"] = "Participant A"
        st.session_state["clear_debate_text_next_run"] = True

        st.rerun()

# -----------------------------
# Mode débat — analyse complète
# -----------------------------
if mode == "Débat dynamique":

    if st.session_state.get("debate_turns"):

        if st.button("Analyser tout le débat", use_container_width=True):

            debate_results = []

            for i, turn in enumerate(st.session_state["debate_turns"], start=1):

                analysis = analyze_article(turn["text"])

                debate_results.append({
                    "Tour": i,
                    "Participant": turn["speaker"],
                    "Score final": analysis.get(
                        "final_credibility_score",
                        analysis["hard_fact_score"]
                    ),
                    "M": analysis["M"],
                    "ME": analysis["ME"],
                    "Pression rhétorique": round(
                        analysis.get("rhetorical_pressure", 0) * 100, 1
                    ),
                    "Cohérence trompeuse": round(
                        analysis.get("deceptive_coherence", 0) * 100, 1
                    ),
                    "Verdict": analysis["verdict"],
                })

            df_debate = pd.DataFrame(debate_results)

            st.subheader("Résultats du débat")

            st.dataframe(
                df_debate,
                use_container_width=True,
                hide_index=True
            )

            winner = df_debate.groupby("Participant")["Score final"].mean().idxmax()

            st.success(
                f"Participant le plus crédible selon l'analyse : {winner}"
            )

    st.stop()
# -----------------------------
# Analyse principale
# -----------------------------
if analyze_submitted:

    words = re.findall(r"\b[\wà-ÿ'-]+\b", article.lower())
    semantic_words = [w for w in words if w not in STOPWORDS]

    if len(semantic_words) < 3:
        st.session_state.last_result = None
        st.session_state.last_article = article

        st.warning("⚠️ Analyse impossible")
        st.caption("Le texte est trop court pour permettre une analyse fiable.")
        st.info(
            "DOXA Detector n’utilise pas de dictionnaire encyclopédique : "
            "il analyse la structure des raisonnements "
            "(logique, sources, contradictions, causalités, degré de certitude).\n\n"
            "Pour lancer l’analyse, le texte doit contenir au moins trois mots "
            "porteurs de sens formant une relation minimale.\n\n"
            "Veuillez saisir une affirmation plus développée."
        )
        st.stop()
        
    # =====================================================
    # Vérification : page web parasite
    # =====================================================

    web_noise = detect_web_noise(article)

    if web_noise["is_noise"]:
        st.session_state.last_result = None
        st.session_state.last_article = article

        st.warning("⚠️ Analyse bloquée")
        st.caption("Le contenu chargé ressemble à une page de navigation ou un menu de site.")
        st.caption(
            f"Détection technique : {web_noise['hits']} marqueurs web, "
            f"{web_noise['real_sentences']} phrases réelles détectées."
        )

        st.info(
            "DOXA Detector a détecté trop d’éléments techniques : "
            "menus, catégories, cookies, annonces ou blocs de navigation.\n\n"
            "Pour éviter une fausse bonne note, l’analyse est interrompue.\n\n"
            "Veuillez coller uniquement le corps de l’article."
        )

        st.stop()

    st.session_state.last_result = analyze_article(article)
    st.session_state.last_article = article

result = st.session_state.get("last_result")
article_for_analysis = st.session_state.get("last_article", "")

if not result:
    st.stop()

# =====================================================
# AIDE DE LECTURE DES JAUGES
# =====================================================

    def show_gauge_help():
        with st.expander("📘 Comment lire les jauges", expanded=False):
            st.markdown("""
Chaque jauge mesure un mécanisme du discours : raisonnement, pression rhétorique, biais argumentatifs ou degré de certitude.

Les jauges n’indiquent pas si un texte est vrai ou faux, mais **la solidité de sa structure cognitive**.

- 🟢 **Vert** → structure saine ou raisonnement solide
- 🟡 **Jaune** → vigilance modérée ou raisonnement partiellement fragile
- 🟠 **Orange** → fragilité importante, raisonnement incomplet ou insuffisamment démontré
- 🔴 **Rouge** → dérive cognitive importante ou manipulation possible
- 🟤 **Marron clair** → mécanisme d’analyse cognitive

**Les textes les plus solides sont ceux qui allument le moins de jauges, ou qui restent majoritairement dans le vert.**

---

### Poids des jauges

Toutes les jauges n’ont pas la même influence sur le résultat final.

Certaines jauges structurelles ont un **coefficient plus élevé**, car elles signalent des problèmes fondamentaux dans le raisonnement.

**Une jauge secondaire à fort coefficient peut peser autant qu’une jauge plus visible.**

Le score final dépend donc **à la fois de l’intensité des jauges et de leur poids dans l’analyse.**

---

### Important

Un texte peut être **cohérent sans être démonstratif**.

Les discours philosophiques, moraux ou spéculatifs obtiennent souvent des scores intermédiaires.
""")


    def show_word_lists_help():
        with st.popover("ℹ️ Rôle de la heuristique et des coefficients"):
            st.markdown("""
### Comment certaines jauges lisent le texte

Certaines jauges ne cherchent pas à “comprendre” le texte comme un humain. Elles n'ont pas besoin de sémantique. Aucune définition n'est nécessaire.

Elles repèrent des mots ou expressions associés à une charge émotionnelle, rhétorique ou cognitive, et analysent leur contexte d’utilisation.

Chaque mot agit comme un signal :

plus il y a de mots marqués, plus les jauges s’allument.

Cependant, ces signaux sont modulés par leur environnement (négation, atténuation, intensification), ce qui permet une lecture plus nuancée.

---

Rôle des coefficients

Tous les signaux détectés ne sont pas équivalents.

Chaque type de marqueur est pondéré par un coefficient, qui ajuste son impact dans le calcul final.

Ces coefficients permettent :

de donner plus de poids à certains signaux (ex : propagande, certitude forte, asymétrie) de limiter l’impact de signaux faibles ou ambigus d’équilibrer les différentes dimensions du langage (émotion, logique, structure, idéologie)

👉 Un mot ou une structure n’a donc pas un effet brut : il est intégré dans un système pondéré qui reflète son importance relative.

Les coefficients ne sont pas aléatoires : ils sont calibrés pour produire une lecture cohérente du discours, en tenant compte :

de la fréquence des signaux de leur intensité de leur rôle dans la construction du raisonnement

👉 Autrement dit : ce ne sont pas les mots seuls qui comptent, mais leur poids dans l’ensemble du système.

Ce que ces jauges détectent réellement

Elles ne disent pas si le texte est vrai ou faux.

Elles mesurent :

- l’intensité du langage utilisé  
- la pression exercée sur le lecteur  
- la manière dont les formulations orientent la perception (crise, urgence, jamais, catastrophe…)

👉 Autrement dit : comment le texte cherche à faire réagir, pas ce qu’il prouve.

---

Exemple

“Une crise majeure menace le pays” → langage chargé → les jauges montent  
“Il n’y a pas de crise actuellement” → présence de négation → signal atténué  
“Il semble possible qu’une crise survienne” → signal modéré par l’incertitude  

---

Pourquoi ce système ?

Parce qu’un discours peut être :

- très convaincant sans être solide  
- très chargé sans être démontré  

Ces jauges captent cette dimension.

---

Limite importante

Elles analysent des structures linguistiques, pas une intention consciente.

Elles peuvent donc :

- surestimer certains textes neutres  
- ou manquer des nuances complexes  

---

Comment interpréter

👉 Ces jauges ne sont jamais à lire seules.

Elles indiquent un niveau de pression linguistique, à croiser avec :

- la solidité argumentative  
- la vérifiabilité  
- l’équilibre G / N / D  

---

Résumé

➡️ Elles mesurent l’impact du langage  
➡️ Elles intègrent partiellement le contexte  
➡️ Elles n’évaluent pas directement la vérité du contenu
➡️ Elles n’interprètent pas l’intention réelle de l’auteur
""")

# =====================================================
# AFFICHAGE
# =====================================================
    
result = st.session_state.get("last_result")

if not result:
    st.info("Aucune analyse disponible.")
    st.stop()

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True)

# =============================
# Barre de raisonnement
# =============================

score = result.get("hard_fact_score", 0)

if score < 6:
    couleur_r = "🔴"
    color_r = "#dc2626"
    etiquette_r = "Très fragile"
    message_r = "Le texte présente peu d’éléments de raisonnement structurés."
elif score < 9:
    couleur_r = "🟠"
    color_r = "#f97316"
    etiquette_r = "Fragile"
    message_r = "Le raisonnement existe, mais reste incomplet ou insuffisamment construit."
elif score < 13:
    couleur_r = "🟡"
    color_r = "#facc15"
    etiquette_r = "Modérée"
    message_r = "Le texte présente une structure de raisonnement cohérente, mais plusieurs affirmations restent conceptuelles ou insuffisamment démontrées."
elif score < 16:
    couleur_r = "🟢"
    color_r = "#16a34a"
    etiquette_r = "Solide"
    message_r = "Le discours est bien organisé en surface, mais cette cohérence ne garantit pas sa validité épistémique."
else:
    couleur_r = "🟢"
    color_r = "#15803d"
    etiquette_r = "Très solide"
    message_r = "Le texte présente un raisonnement robuste, structuré et bien soutenu."

st.subheader(f"{couleur_r} Solidité argumentative : {etiquette_r}")
# Barre épaisse colorée
st.caption(
    "Cette jauge mesure la solidité argumentative globale du texte : "
    "structure du raisonnement, cohérence logique, vérifiabilité, qualité des sources "
    "et pénalités discursives détectées."
)
st.markdown(f"""
<div style="width:100%; margin-top:10px; margin-bottom:10px;">
    <div style="
        width:100%;
        height:26px;
        background:#e5e7eb;
        border-radius:12px;
        overflow:hidden;
        border:1px solid #cbd5e1;
    ">
        <div style="
            width:{min(score / 20, 1) * 100}%;
            height:100%;
            background:{color_r};
            transition:width 0.4s ease;
        "></div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    f"<b style='color:{color_r}'>{etiquette_r}</b> — Score : {round(score, 1)}/20",
    unsafe_allow_html=True
)
st.caption(message_r)
with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown(f"""
### Solidité argumentative

Cette jauge estime la solidité argumentative globale du texte.

Elle ne mesure pas :

- la vérité absolue du texte ;
- l’intention réelle du locuteur ;
- la seule cohérence stylistique.

Elle mesure plutôt la capacité du discours à soutenir ses affirmations par une structure logique, des éléments vérifiables et une base documentaire suffisante.

---

### Principe

Le moteur combine :

- la structure du raisonnement ;
- la cohérence discursive ;
- la vérifiabilité des affirmations ;
- la qualité des sources ;
- la présence de pénalités discursives.

Cette jauge peut être fragilisée indirectement par :

- le **baratinage**, lorsqu’une impression de maîtrise dépasse la démonstration visible ;
- l’**omission stratégique**, lorsque le contexte utile semble insuffisamment présenté.

L’**effet placebo étendu** n’est pas intégré ici sauf cas particulier.

---

### Formule utilisée

```python
HFS_brut = (
    0.18 * G
    + 0.12 * N
    + 0.20 * V
    + 0.22 * QS
    + 0.18 * VC
) - (
    0.16 * D
    + 0.12 * R
    + 0.18 * RC
    + P
)

HFS = HFS_brut + 8 + bonus_epistemique

score = max(0, min(HFS, 20))
```

---

### Où :

- **G** = gnōsis / savoir articulé  
- **N** = nous / compréhension intégrée  
- **V** = vérifiabilité globale  
- **QS** = qualité des sources  
- **VC** = vérifiabilité moyenne des affirmations  
- **D** = doxa / certitude  
- **R** = risque rhétorique  
- **RC** = risque moyen des affirmations  
- **P** = pénalités de crédibilité  

---

### Fragilités complémentaires

Baratinage :
**{round(result.get("baratinage_score", 0) * 100, 1)}%**

Omission stratégique :
**{round(result.get("omission_score", 0) * 100, 1)}%**

---

### Valeur actuelle

Score argumentatif :
**{round(score, 1)}/20**

Cohérence discursive brute :
**{round(result.get("discursive_coherence_score", 0), 1)}/20**

Crédibilité finale après pénalités :
**{round(result.get("final_credibility_score", 0), 1)}/20**

Couleurs

🔴 Rouge — Très fragile
Le texte présente peu d’éléments de raisonnement structurés.

🟠 Orange — Fragile
Le raisonnement existe mais reste incomplet ou insuffisamment construit.

🟡 Jaune — Modérée
Le texte présente une structure cohérente mais plusieurs affirmations restent conceptuelles ou insuffisamment démontrées.

🟢 Vert — Solide
Le discours est bien organisé et relativement soutenu.

🟢 Vert foncé — Très solide
Le texte présente un raisonnement robuste, structuré et bien soutenu.

Lecture

🔴 0–5.9 : raisonnement très fragile

🟠 6–8.9 : raisonnement fragile

🟡 9–12.9 : raisonnement modéré

🟢 13–15.9 : raisonnement solide

🟢 16–20 : raisonnement très solide

Attention

Un score élevé ne garantit pas que le texte est vrai.

Il indique seulement que sa structure argumentative, ses appuis vérifiables et sa cohérence globale paraissent relativement solides.
""")


# =============================
# Analyse analogique du raisonnement
# =============================

st.subheader("Analyse analogique du raisonnement")

st.caption(
    "Analyse analogique du raisonnement à partir des structures du langage afin d’estimer la solidité épistémique du discours."
)

real_score = result.get("final_credibility_score", result.get("hard_fact_score", 0))

# Plancher VISUEL uniquement
display_score = max(real_score, 2.0)
display_score = min(display_score, 20.0)

# Couleurs et verdict — basés sur le score affiché
if display_score < 6:
    score_icon = "🔴"
    score_color = "#dc2626"
    score_label = "Faible"
elif display_score < 9:
    score_icon = "🟠"
    score_color = "#f97316"
    score_label = "Fragile"
elif display_score < 13:
    score_icon = "🟡"
    score_color = "#facc15"
    score_label = "Modérée"
elif display_score < 16:
    score_icon = "🟢"
    score_color = "#22c55e"
    score_label = "Solide"
else:
    score_icon = "🟢"
    score_color = "#15803d"
    score_label = "Très solide"

# Barre épaisse colorée
st.markdown(f"""
<div style="width:100%; margin-top:10px; margin-bottom:10px;">
    <div style="
        width:100%;
        height:26px;
        background:#e5e7eb;
        border-radius:12px;
        overflow:hidden;
        border:1px solid #cbd5e1;
    ">
        <div style="
            width:{min(display_score / 20, 1) * 100}%;
            height:100%;
            background:{score_color};
            transition:width 0.4s ease;
        "></div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    f"<b style='color:{score_color}'>Score analogique : {score_icon} {round(display_score,1)}/20 — {score_label}</b>",
    unsafe_allow_html=True
)

if display_score < 6:
    analogique_message = "Le raisonnement paraît faible : les enchaînements logiques sont insuffisants ou trop fragmentaires."
elif display_score < 9:
    analogique_message = "Le raisonnement est fragile : une structure existe, mais elle reste incomplète ou peu démonstrative."
elif display_score < 13:
    analogique_message = "Le raisonnement est modéré : la structure logique est présente, mais plusieurs liens restent partiels ou insuffisamment soutenus."
elif display_score < 16:
    analogique_message = "Le raisonnement est solide : les idées s’enchaînent de manière globalement cohérente."
else:
    analogique_message = "Le raisonnement est très solide : le discours présente une progression claire, cohérente et bien structurée."

st.caption(analogique_message)

# Popover explicatif
with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown(f"""
### Analyse analogique du raisonnement

Cette jauge estime la **solidité argumentative après pénalités**.

Elle ne mesure pas :

- la vérité absolue du texte ;
- l’intention réelle du locuteur ;
- la seule cohérence stylistique.

Elle mesure plutôt la solidité restante du raisonnement après prise en compte des fragilités détectées.

---

### Principe

Cette jauge part de la solidité argumentative globale, puis tient compte des pénalités de crédibilité.

Elle peut être diminuée par :

- pression rhétorique ;
- certitude excessive ;
- contradiction interne ;
- données sans référentiel ;
- baratinage ;
- omission stratégique.

L’effet placebo étendu n’est pas intégré ici sauf cas particulier de discours expérientiel.

---

### Résultats de cette analyse

Score affiché :
**{round(display_score, 1)}/20**

Score réel utilisé :
**{round(real_score, 1)}/20**

Verdict :
**{score_label}**

---

### Formule utilisée

```python
score = final_credibility_score

if final_credibility_score is None:
    score = hard_fact_score

display_score = max(score, 2.0)
```

---

### Valeurs complémentaires

Solidité argumentative brute :

**{round(result.get("hard_fact_score", 0), 1)}/20**

Crédibilité finale pénalisée :

**{round(result.get("final_credibility_score", 0), 1)}/20**

Pénalité de crédibilité :

**{round(result.get("credibility_penalty", 0), 2)}**

Baratinage :

**{round(result.get("baratinage_score", 0) * 100, 1)}%**

Omission stratégique :

**{round(result.get("omission_score", 0) * 100, 1)}%**

---

### Couleurs

🔴 **Rouge — Faible**  
Le raisonnement paraît très fragilisé.

🟠 **Orange — Fragile**  
Une structure existe mais reste peu démonstrative.

🟡 **Jaune — Modérée**  
La structure logique est présente mais plusieurs liens restent partiels ou insuffisamment soutenus.

🟢 **Vert — Solide**  
Les idées s’enchaînent de manière globalement cohérente.

🟢 **Vert foncé — Très solide**  
Le discours présente une progression claire, cohérente et bien structurée.

---

### Lecture

🔴 **0–5.9** : raisonnement très fragile  

🟠 **6–8.9** : raisonnement fragile  

🟡 **9–12.9** : raisonnement modéré  

🟢 **13–15.9** : raisonnement solide  

🟢 **16–20** : raisonnement très solide  

---

### Attention

Un score élevé ne garantit pas que le texte est vrai.

Il indique seulement que le raisonnement conserve une solidité apparente après application des pénalités détectées.
""")

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True)


st.markdown("### Type de discours détecté")

st.info(
    f"**{result.get('discourse_type_rhetoric', 'Indéterminé')}** — "
    f"{result.get('discourse_explanation_rhetoric', '')}"
)
st.caption(explain_discourse_profile(result))

with st.expander("Voir les scores rhétoriques détaillés", expanded=False):
    st.markdown("#### Scores rhétoriques")
    st.json(result.get("rhetorical_scores", {}))

    st.markdown("#### Scores des types de discours")
    st.json(result.get("discourse_scores", {}))

    st.markdown("#### Registres émotionnels")
    st.json(result.get("emotional_registers", {}))

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True)


# =============================
# 🧠 1. DÉRIVES COGNITIVES FONDAMENTALES
# =============================

st.markdown(
    """
<div style="text-align:center;">
    <h3>🧠 Dérives cognitives fondamentales</h3>
    <p style="color:#888; margin-top:-10px;">
        Dérives internes du raisonnement liées à l’équilibre entre connaissance (G), compréhension (N) et certitude (D).
    </p>
</div>
""",
    unsafe_allow_html=True
)

# -----------------------------
# Pseudo-savoir
# -----------------------------
st.markdown("### Pseudo-savoir")
st.caption("Accumulation de savoirs mal intégrés ou mal compris.")

value = min(result["drift_pseudo_savoir"] / 10, 1.0)

if result["drift_pseudo_savoir"] < 1:
    label, color = "Faible", "#16a34a"
elif result["drift_pseudo_savoir"] < 3:
    label, color = "Modérée", "#ca8a04"
elif result["drift_pseudo_savoir"] < 6:
    label, color = "Élevée", "#f97316"
else:
    label, color = "Très élevée", "#dc2626"

render_custom_gauge(value, color)

st.markdown(
    f"<b style='color:{color}'>{label}</b> — {result['drift_pseudo_savoir']}",
    unsafe_allow_html=True
)

with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown(f"""
### Pseudo-savoir

Cette jauge mesure un déséquilibre où le texte accumule du savoir apparent ou des éléments de connaissance, mais sans compréhension suffisamment intégrée.

Elle ne mesure pas :

- le mensonge ;
- la vérité du texte ;
- l’intention réelle du locuteur.

Elle mesure plutôt un risque d’accumulation cognitive mal intégrée.

---

### Formule utilisée

Pseudo-savoir = max(0, (G_drift + D) - N)

Avec :

- **G_drift** = savoir recalibré  
- **D** = certitude  
- **N** = compréhension intégrée  

---

### Avec les valeurs actuelles

G_drift = **{result['G_drift']:.2f}**  
D = **{result['D']:.2f}**  
N = **{result['N']:.2f}**

Calcul :

max(0, ({result['G_drift']:.2f} + {result['D']:.2f}) - {result['N']:.2f}) = **{result['drift_pseudo_savoir']:.2f}**

---

### Couleurs

🟢 **Vert — Faible**  
Le savoir paraît suffisamment intégré.

🟡 **Jaune — Modérée**  
Le texte accumule certains éléments de savoir, mais leur intégration reste partielle.

🟠 **Orange — Élevée**  
Le discours donne une impression notable de savoir mal digéré ou insuffisamment relié.

🔴 **Rouge — Très élevée**  
Le texte semble fortement accumuler du savoir apparent sans compréhension intégrée suffisante.

---

### Lecture

🟢 **Faible** : savoir intégré  
🟡 **Modérée** : accumulation partiellement intégrée  
🟠 **Élevée** : pseudo-savoir notable  
🔴 **Très élevée** : accumulation cognitive dominante  

---

### Attention

Un score élevé ne signifie pas que le texte est faux.

Il indique seulement que le savoir affiché semble dépasser son intégration réelle dans le raisonnement.

---

### Normalisation graphique

value = min(drift_pseudo_savoir / 10, 1.0)
""")

st.divider()

# -----------------------------
# Intuition dogmatique
# -----------------------------
st.markdown("### Intuition dogmatique")
st.caption("Conviction forte sans base de savoir suffisante.")

value = min(result["drift_intuition_dogmatique"] / 10, 1.0)

if result["drift_intuition_dogmatique"] < 1:
    label, color = "Faible", "#16a34a"
elif result["drift_intuition_dogmatique"] < 3:
    label, color = "Modérée", "#ca8a04"
elif result["drift_intuition_dogmatique"] < 6:
    label, color = "Élevée", "#f97316"
else:
    label, color = "Très élevée", "#dc2626"

render_custom_gauge(value, color)

st.markdown(
    f"<b style='color:{color}'>{label}</b> — {result['drift_intuition_dogmatique']}",
    unsafe_allow_html=True
)

with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown(f"""
### Intuition dogmatique

Cette jauge mesure un déséquilibre où l’intuition ou la compréhension apparente s’allie à une certitude forte, mais sans base de savoir suffisamment articulée.

Elle ne mesure pas :

- le mensonge ;
- la vérité du texte ;
- l’intention réelle du locuteur.

Elle mesure plutôt une conviction portée par la compréhension apparente plus que par le savoir articulé.

---

### Formule utilisée

Intuition dogmatique = max(0, (N + D) - G_drift)

Avec :

- **N** = compréhension intégrée  
- **D** = certitude  
- **G_drift** = savoir recalibré  

---

### Avec les valeurs actuelles

N = **{result['N']:.2f}**  
D = **{result['D']:.2f}**  
G_drift = **{result['G_drift']:.2f}**

Calcul :

max(0, ({result['N']:.2f} + {result['D']:.2f}) - {result['G_drift']:.2f}) = **{result['drift_intuition_dogmatique']:.2f}**

---

### Couleurs

🟢 **Vert — Faible**  
La conviction reste soutenue par une base de savoir suffisante.

🟡 **Jaune — Modérée**  
Une intuition ou compréhension apparente commence à dépasser le savoir articulé.

🟠 **Orange — Élevée**  
Le discours semble s’appuyer fortement sur une intuition affirmée.

🔴 **Rouge — Très élevée**  
La conviction semble nettement dépasser le savoir disponible.

---

### Lecture

🟢 **Faible** : intuition contenue par le savoir  
🟡 **Modérée** : intuition partiellement dominante  
🟠 **Élevée** : intuition fortement structurante  
🔴 **Très élevée** : conviction dogmatique dominante  

---

### Attention

Un score élevé ne signifie pas que l’intuition est fausse.

Il indique seulement que la conviction semble dépasser le savoir articulé disponible.

---

### Normalisation graphique

value = min(drift_intuition_dogmatique / 10, 1.0)
""")


st.divider()

# -----------------------------
# Fermeture cognitive
# -----------------------------
st.markdown("### Fermeture cognitive")
st.caption("Excès de certitude par rapport au savoir et à la compréhension.")

value = min(result["drift_mecroyance"] / 10, 1.0)

if result["drift_mecroyance"] < 1:
    label, color = "Faible", "#16a34a"
elif result["drift_mecroyance"] < 3:
    label, color = "Modérée", "#ca8a04"
elif result["drift_mecroyance"] < 6:
    label, color = "Élevée", "#f97316"
else:
    label, color = "Très élevée", "#dc2626"

render_custom_gauge(value, color)

st.markdown(
    f"<b style='color:{color}'>{label}</b> — {result['drift_mecroyance']}",
    unsafe_allow_html=True
)

with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown("""
### Fermeture cognitive

Cette jauge mesure un déséquilibre où la certitude affirmée dépasse le savoir articulé et la compréhension intégrée.

Elle ne mesure pas :

- le mensonge ;
- la vérité du texte ;
- l’intention réelle du locuteur.

Elle mesure plutôt un risque de fermeture interprétative.
""")

    st.markdown("### Principe")

    st.write(
        "Le moteur compare le niveau de certitude au savoir disponible "
        "et à la compréhension intégrée."
    )

    st.markdown("### Formule utilisée")

    st.code("""
Forme théorique :

Fermeture cognitive = max(0, D - (G + N))

Forme utilisée ici :

Fermeture cognitive = max(
    0,
    D - (G_drift + N)
)

G_drift = G × 0.5
""")

    st.markdown("### Avec les valeurs actuelles")

    st.write(
        f"D = {result['D_drift']:.2f} | "
        f"G_drift = {result['G_drift']:.2f} | "
        f"N = {result['N_drift']:.2f}"
    )

    st.code(
        f"max(0, {result['D_drift']:.2f} - "
        f"({result['G_drift']:.2f} + {result['N_drift']:.2f})) "
        f"= {result['drift_mecroyance']:.2f}"
    )

    st.markdown("### Couleurs")

    st.write(
        "🟢 Faible — équilibre préservé\n\n"
        "🟡 Modérée — certitude légèrement dominante\n\n"
        "🟠 Élevée — fermeture interprétative notable\n\n"
        "🔴 Très élevée — certitude nettement supérieure au savoir disponible"
    )

    st.markdown("### Lecture")

    st.write(
        "Plus ce score est élevé, plus le discours affirme avec certitude "
        "alors que les bases de savoir et de compréhension restent limitées."
    )

    st.markdown("### Normalisation graphique")

    st.code("value = min(drift_mecroyance / 10, 1.0)")

    st.markdown("### Attention")

    st.write(
        "Un score élevé ne signifie pas que le texte est faux.\n\n"
        "Il indique seulement qu’une certitude semble dépasser "
        "le savoir disponible et son intégration."
    )

st.divider()

# -----------------------------
# Indice global de dérive cognitive
# -----------------------------
st.markdown("### Indice global de dérive cognitive")
st.caption("Synthèse des trois dérives cognitives.")

global_score = result["global_cognitive_drift"]
global_value = min(global_score / 10, 1.0)

if global_score < 1:
    global_label, global_color = "Faible", "#16a34a"
elif global_score < 3:
    global_label, global_color = "Modérée", "#ca8a04"
elif global_score < 6:
    global_label, global_color = "Élevée", "#f97316"
else:
    global_label, global_color = "Très élevée", "#dc2626"

render_custom_gauge(global_value, global_color)

st.markdown(
    f"<b style='color:{global_color}'>{global_label}</b> — {global_score}",
    unsafe_allow_html=True
)

st.caption(result["cognitive_drift_interpretation"])


with st.popover("ℹ️ Comprendre cette jauge", use_container_width=True):

    st.markdown(f"""
### Indice global de dérive cognitive

Cette jauge synthétise les trois dérives cognitives fondamentales.

Elle ne dit pas si le texte est vrai ou faux :
elle mesure le degré de déséquilibre entre savoir,
compréhension et certitude.

---

### Principe

Le moteur combine trois dérives :

- fermeture cognitive ;
- pseudo-savoir ;
- intuition dogmatique.

L’indice final donne davantage de poids à la dérive dominante afin d’éviter qu’un signal fort soit noyé dans la moyenne.

---

### Formule fondatrice

Forme théorique :

M = (G + N) − D

Forme utilisée ici :

M = (G_drift + N) − D

avec :

G_drift = G × 0.5

afin d’éviter qu’un savoir fortement présent domine mécaniquement les autres dimensions.

---

### Dérives utilisées

Fermeture cognitive = max(0, -M)

Pseudo-savoir = max(0, (G_drift + D) - N)

Intuition dogmatique = max(0, (N + D) - G_drift)

---

### Formule utilisée

dominant_value = max(
    fermeture,
    pseudo_savoir,
    intuition
)

average_value = (
    fermeture
    + pseudo_savoir
    + intuition
) / 3

global_drift = (
    dominant_value * 0.60
) + (
    average_value * 0.40)

---

### Valeurs actuelles

Fermeture cognitive :
{result['drift_mecroyance']:.2f}

Pseudo-savoir :
{result['drift_pseudo_savoir']:.2f}

Intuition dogmatique :
{result['drift_intuition_dogmatique']:.2f}

---

### Résultat actuel

Score :
{global_score:.2f}

Niveau :
{global_label}

{result["cognitive_drift_interpretation"]}

---

### Couleurs

🟢 Vert — Faible  
Les dimensions restent relativement équilibrées.

🟡 Jaune — Modérée  
Une dérive commence à structurer le raisonnement.

🟠 Orange — Élevée  
Une logique cognitive domine nettement l’équilibre général.

🔴 Rouge — Très élevée  
Une forme cognitive semble fortement surdéterminer le discours.

---

### Lecture

🟢 Faible : équilibre global conservé

🟡 Modérée : dérive émergente

🟠 Élevée : déséquilibre notable

🔴 Très élevée : dérive dominante

---

### Attention

Un score élevé ne signifie pas que le texte est faux.

Il indique seulement qu’une forme de déséquilibre entre savoir,
compréhension et certitude semble dominer la structure du discours.

---

### Échelle

🟢 Faible < 1.5

🟡 Modérée < 3.5

🟠 Élevée < 6

🔴 Très élevée ≥ 6
""")

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True) 

# =============================
# 🧠 LECTURE DES INTENTIONS COGNITIVES
# =============================

st.markdown(
    """
<div style="text-align:center; margin-top:10px; margin-bottom:20px;">

<h3 style="margin-bottom:8px;">
🧠 Lecture des intentions cognitives
</h3>

<div style="color:#888; font-size:0.95rem;">

Mécroyance ⟵⟶ Manipulation<br>
Démonstration explicite ⟵⟶ Impression de maîtrise

</div>

</div>
""",
    unsafe_allow_html=True
)
# =============================
# Calculs mécroyance / mensonge
# =============================

lie_result = compute_lie_gauge(result["M"], result["ME"])

gauge_value = lie_result["gauge"]
gauge_label = lie_result["label"]
gauge_color = lie_result["color"]
gauge_intensity = lie_result["intensity"]

M_val = result.get("M", 0)
ME_val = result.get("ME", 0)

m_norm = max(0.0, min(1.0, (M_val + 10) / 30))
me_norm = max(0.0, min(1.0, ME_val / 20))
delta_lie = me_norm - (1 - m_norm)
gauge_calc = max(0.0, min(1.0, 0.5 + (delta_lie * 0.8)))

if gauge_color == "#a16207":
    emoji = "🟤"
elif gauge_color == "#ca8a04":
    emoji = "🟡"
elif gauge_color == "#f59e0b":
    emoji = "🟠"
elif gauge_color == "#dc2626":
    emoji = "🔴"
else:
    emoji = "⚪"

st.subheader(f"{emoji} Tension cognitive : {gauge_label}")
st.caption(
    "Cette jauge indique si le discours relève plutôt d’une erreur sincère "
    "(mécroyance) ou d’une possible manipulation. "
    "Plus la jauge progresse, plus la structure du texte se rapproche du mensonge."
)
# Barre visuelle de la jauge
st.markdown(f"""
<div style="width:100%; margin-top:10px; margin-bottom:10px;">
    <div style="
        width:100%;
        height:26px;
        background:#e5e7eb;
        border-radius:12px;
        overflow:hidden;
        border:1px solid #cbd5e1;
    ">
        <div style="
            width:{gauge_value*100}%;
            height:100%;
            background:{gauge_color};
            transition:width 0.4s ease;
        "></div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    f"<b style='color:{gauge_color}'>{gauge_label}</b> — intensité : {round(gauge_intensity*100,1)}%",
    unsafe_allow_html=True
)

st.caption("Erreur sincère ⟵⟶ Manipulation probable")

with st.popover("ℹ️ Formule / résultats"):

    st.subheader(f"Verdict : {gauge_label}")
    st.caption(
        f"Position : {round(gauge_calc, 3)} / 1 — "
        f"Intensité : {round(gauge_intensity * 100, 1)}%"
    )

    st.subheader("Résumé de l’analyse")

    m1, m2 = st.columns(2)
    m1.metric("M — mécroyance", round(M_val, 2))
    m2.metric("ME — mendacité", round(ME_val, 2))

    m3, m4 = st.columns(2)
    m3.metric("M normalisé", round(m_norm, 3))
    m4.metric("ME normalisé", round(me_norm, 3))

    m5, m6 = st.columns(2)
    m5.metric("Delta cognitif", round(delta_lie, 3))
    m6.metric("Position jauge", round(gauge_calc, 3))

    m7, m8 = st.columns(2)
    m7.metric("Intensité", f"{round(gauge_intensity * 100, 1)}%")
    m8.metric("Verdict", gauge_label)

    st.markdown(f"""
Cette jauge situe le discours sur un axe allant de la **mécroyance** au **mensonge stratégique**.

Elle compare deux indices cognitifs :

- **M** : indice de mécroyance
- **ME** : indice de mendacité

---

### 1️⃣ Indice de mécroyance

`M = (G + N) − D`

avec :

G = gnōsis  
N = nous  
D = doxa

Dans cette analyse :

`M = {round(M_val, 2)}`

---

### 2️⃣ Indice de mensonge stratégique

`ME = 2D − (G + N)`

Dans cette analyse :

`ME = {round(ME_val, 2)}`

---

### 3️⃣ Normalisation des indices

`m_norm = (M + 10) / 30`

`me_norm = ME / 20`

Dans cette analyse :

`m_norm ≈ {round(m_norm, 3)}`

`me_norm ≈ {round(me_norm, 3)}`

---

### 4️⃣ Calcul de la tension cognitive

`delta = me_norm − (1 − m_norm)`

Dans cette analyse :

`delta ≈ {round(delta_lie, 3)}`

---

### 5️⃣ Formule heuristique principale

`gauge = 0.5 + (delta × 0.8)`

La valeur finale est bornée entre **0** et **1**.

Position observée :

`gauge = {round(gauge_calc, 3)} / 1`

---

### Interprétation de la jauge

0.00–0.20 : mécroyance forte  
0.20–0.40 : mécroyance modérée  
0.40–0.60 : zone ambiguë  
0.60–0.80 : mensonge probable  
0.80–1.00 : mensonge extrême

---

### Lecture du résultat

Plus **M domine ME**, plus le texte relève d’une erreur sincère ou d’un désalignement cognitif.

Plus **ME domine M**, plus le texte se rapproche d’une manipulation stratégique.

Dans cette analyse, la jauge indique :

**{gauge_label}**
""")

# =============================
# Diagnostic cognitif
# =============================

delta_mm = round(result["M"] - result["ME"], 2)
st.caption(f"Écart cognitif (M − ME) : {delta_mm}")

if result["M"] > result["ME"] + 1:
    dominant_pattern = "Structure dominante : mécroyance"
elif result["ME"] > result["M"] + 1:
    dominant_pattern = "Structure dominante : mensonge stratégique"
else:
    dominant_pattern = "Structure dominante : mixte ou ambiguë"

if result["ME"] > result["M"] and result["ME"] > 0:
    cognitive_type = (
        "Mensonge stratégique : la structuration du discours laisse apparaître "
        "un désalignement cognitif pouvant suggérer une intention manipulatoire."
    )

elif result["M"] < 0:
    cognitive_type = (
        "Clôture cognitive : la certitude dépasse fortement "
        "les éléments de savoir et de compréhension disponibles."
    )

elif result["M"] - result["ME"] > 3:
    cognitive_type = (
        "texte orienté avec absence d’intention manipulatoire détectée. "
    )

elif result["M"] > result["ME"]:
    cognitive_type = (
        "Le discours présente un désalignement cognitif notable, "
        "sans indication claire de manipulation."
    )

else:
    cognitive_type = (
        "Zone ambiguë : le discours présente une tension cognitive difficile à trancher "
        "entre erreur sincère et orientation stratégique."
    )

st.subheader("Interprétation cognitive")
st.write(cognitive_type)

if result["M"] - result["ME"] > 3:
    diagnosis = "Mécroyance avérée"
elif result["M"] > result["ME"]:
    diagnosis = "Mécroyance modérée"
elif abs(result["M"] - result["ME"]) <= 1:
    diagnosis = "Structure cognitive ambiguë"
else:
    diagnosis = "Tromperie stratégique possible ou mensonge"

st.subheader("Diagnostic cognitif")
st.write(diagnosis)

# =============================
# Explication automatique de la jauge mensonge
# =============================

if gauge_value >= 0.70:
    st.warning("### Pourquoi cette jauge indique une manipulation probable ?")

    st.markdown("""
La jauge monte fortement parce que le texte présente une combinaison de signaux :

- une certitude très élevée
- un niveau de preuves insuffisant face à cette certitude
- une pression rhétorique importante
- des affirmations difficiles à vérifier
- des formulations pouvant orienter le lecteur plutôt que d’éclairer le raisonnement
""")

    st.markdown("#### Facteurs détectés")

    st.write(f"- Mécroyance M : {result['M']}")
    st.write(f"- Mensonge stratégique ME : {result['ME']}")
    st.write(f"- Certitude D : {result['D']}")
    st.write(f"- Savoir G : {result['G']}")
    st.write(f"- Compréhension N : {result['N']}")
    st.write(f"- Pression rhétorique : {round(result.get('rhetorical_pressure', 0) * 100, 1)}%")
    st.write(f"- Red flags détectés : {len(result.get('red_flags', []))}")

elif gauge_value >= 0.45:
    st.info("### Pourquoi cette jauge s’allume ?")

    st.markdown("""
Le texte contient une tension entre mécroyance et manipulation.

La certitude paraît plus forte que les preuves disponibles, mais les signaux ne suffisent pas encore à conclure à une manipulation nette.
""")
    
else:
    pass

# =============================
# Indice de baratinage
# =============================

st.subheader("Indice de baratinage")

st.caption(
    "Cette jauge n’évalue pas si le texte est vrai ou faux. "
    "Elle estime l’écart entre l’impression de maîtrise produite "
    "par le discours et la démonstration réellement visible."
)

value = result.get("baratinage_score", 0)

render_custom_gauge(
    value,
    result.get("baratinage_color", "#22c55e")
)

st.markdown(
    f"""
<b style='color:{result.get("baratinage_color", "#22c55e")}'>
{result.get("baratinage_label", "Faible")}
</b>
— {round(value*100,1)}%
""",
    unsafe_allow_html=True
)

st.caption(
    result.get(
        "baratinage_interpretation",
        "Indice de baratinage non calculé."
    )
)

st.caption(
    "Démonstration explicite ⟵⟶ Impression de maîtrise"
)

with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown("""
### Indice de baratinage

Cette jauge estime dans quelle mesure un discours produit une **impression de maîtrise, de profondeur ou d’autorité** supérieure à ce que sa démonstration explicite semble soutenir.

Elle ne mesure pas :
- la vérité du texte ;
- le mensonge ;
- l’intention réelle du locuteur.

Elle mesure plutôt un **écart entre effet discursif et fondation démonstrative**.

---

### Principe

Le moteur compare les facteurs qui augmentent l’effet de maîtrise :

- certitude forte ;
- cohérence apparente ;
- densité argumentative ;
- intensité rhétorique ;
- abstraction ;
- clôture cognitive.

Avec les facteurs qui le réduisent :

- preuves ;
- ancrage au réel ;
- reconnaissance des limites ;
- révisabilité ;
- précision ;
- explicitation du raisonnement.

---

### Formule utilisée

```python
IB_heuristique = (
    CF + CE + ACE + RP + NP + PI + CS
) - (
    HF + AR + RV + BC + AS + AN
)

IB_doxa = (G + 2D) - N

IB = IB_heuristique + (IB_doxa * 0.15)

score = max(0.0, min(IB / 6, 1.0))

- **CE** = cohérence trompeuse  
- **ACE** = cohérence trompeuse avancée  
- **RP** = pression rhétorique  
- **NP** = pression narrative  
- **PI** = prémisses implicites  
- **CS** = certitude générale  

- **HF** = score factuel disponible  
- **BC** = bonus de cohérence  
- **AS** = arguments de soutien  
- **AN** = nuances argumentatives

### Lecture

🟢 **Faible** : démonstration dominante  
🟡 **Modéré** : rhétorique présente mais contenue  
🟠 **Élevé** : effet de maîtrise notable  
🔴 **Très élevé** : impression de maîtrise nettement supérieure à la démonstration

---

### Attention

Un score élevé ne signifie pas que le texte est faux ou que l’auteur ment.

Il indique seulement que la force perçue du discours semble davantage venir de sa forme que de sa démonstration explicite.
""")

# =============================
# Indice d’omission stratégique
# =============================

st.subheader("Indice d’omission stratégique")

st.caption(
    "Cette jauge n’affirme pas qu’un mensonge par omission existe. "
    "Elle estime si le discours semble sélectionner certains éléments "
    "au détriment du contexte utile."
)

value = result.get("omission_score", 0)

render_custom_gauge(
    value,
    result.get("omission_color", "#22c55e")
)

st.markdown(
    f"""
<b style='color:{result.get("omission_color", "#22c55e")}'>
{result.get("omission_label", "Faible")}
</b>
— {round(value*100,1)}%
""",
    unsafe_allow_html=True
)

st.caption(
    result.get(
        "omission_interpretation",
        "Indice d’omission stratégique non calculé."
    )
)

st.caption(
    "Contexte explicite ⟵⟶ Sélectivité discursive"
)

with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown("""
### Indice d’omission stratégique

Cette jauge estime dans quelle mesure un discours semble **sélectionner certains éléments** tout en laissant hors champ des informations susceptibles de modifier l’interprétation globale.

Elle ne mesure pas :

- le mensonge ;
- l’intention réelle du locuteur ;
- la quantité absolue d’informations disponibles.

Elle mesure plutôt un **risque de sélectivité discursive**.

---

### Principe

Le moteur compare les facteurs qui augmentent l’indice :

- cherry picking ;
- données sans référentiel ;
- manipulation statistique ;
- prémisses implicites ;
- asymétrie argumentative ;
- certitude forte ;
- clôture cognitive.

Avec les facteurs qui le réduisent :

- reconnaissance des limites ;
- révisabilité ;
- ancrage au réel ;
- précision ;
- présence de contre-arguments.

---

### Formule utilisée

```python
MO_heuristique = (
    CP
    + (DR * 1.5)
    + PI
    + AA
    + CF
    + CC
    + (MS * 0.35)
) - (
    LM + RV + AR + PX + CA
)

MO_doxa = (G + D) - (2 * N)

MO = MO_heuristique + (MO_doxa * 0.15)

score = max(0.0, min(MO / 12, 1.0))
```

Où :

- **CP** = cherry picking  
- **DR** = données sans référentiel  
- **PI** = prémisses implicites  
- **AA** = asymétrie argumentative  
- **CF** = certitude forte  
- **CC** = clôture cognitive
- **MS** = manipulation statistique

Et :

- **LM** = reconnaissance des limites  
- **RV** = révisabilité  
- **AR** = ancrage au réel  
- **PX** = précision  
- **CA** = contre-arguments  

Modulation DOXA :

- **G** = savoir articulé, approximé ici par le score factuel disponible  
- **D** = certitude  
- **N** = compréhension intégrée, approximée par l’ancrage et la révisabilité  

---

### Couleurs

🟢 **Vert — Faible**  
Le contexte paraît relativement complet.

🟡 **Jaune — Modéré**  
Quelques éléments semblent peu contextualisés.

🟠 **Orange — Élevé**  
Le discours paraît sélectionner certains éléments au détriment du contexte.

🔴 **Rouge — Très élevé**  
Le discours semble fortement orienté par sélection du contexte.

---

### Lecture

🟢 **Faible (0–14.9%)** : contexte relativement complet  
🟡 **Modéré (15–34.9%)** : éléments partiellement contextualisés  
🟠 **Élevé (35–64.9%)** : sélection discursive notable  
🔴 **Très élevé (65–100%)** : forte orientation par sélection du contexte

---

### Attention

Un score élevé ne prouve pas qu’une information a été volontairement cachée.

Il indique seulement que le discours semble laisser hors champ des éléments pouvant modifier son interprétation.
""")

# =============================
# Effet placebo étendu
# =============================

st.subheader("Effet placebo étendu")

st.caption(
    "Cette jauge n’affirme pas qu’un effet placebo existe réellement. "
    "Elle estime si le discours transforme une expérience vécue ou ressentie "
    "en preuve subjective auto-validante."
)

value = result.get("extended_placebo_score", 0)

render_custom_gauge(
    value,
    result.get("extended_placebo_color", "#22c55e")
)

st.markdown(
    f"""
<b style='color:{result.get("extended_placebo_color", "#22c55e")}'>
{result.get("extended_placebo_label", "Faible")}
</b>
— {round(value*100,1)}%
""",
    unsafe_allow_html=True
)

st.caption(
    result.get(
        "extended_placebo_interpretation",
        "Effet placebo étendu non calculé."
    )
)

st.caption(
    "Expérience prudente ⟵⟶ Conviction auto-validée"
)

with st.popover("ℹ️ Comprendre cette jauge"):

    st.markdown("""
### Effet placebo étendu

Cette jauge estime dans quelle mesure un discours semble **transformer une expérience vécue, ressentie ou perçue comme efficace** en preuve subjective.

Elle ne mesure pas :
- l’effet placebo médical au sens strict ;
- la vérité ou la fausseté de l’expérience ;
- l’intention réelle du locuteur.

Elle mesure plutôt un **risque d’auto-validation expérientielle**.

---

### Principe

Le moteur combine :

- une formule théorique de mécroyance expérientielle ;
- une formule heuristique ;
- un garde-fou d’expérience auto-validante (**EX**).

Les facteurs qui augmentent l’indice sont :

- certitude forte ;
- prémisses implicites ;
- cohérence trompeuse ;
- cohérence trompeuse avancée ;
- causalité abusive ;
- pression ou surdétermination narrative.

Les facteurs qui le réduisent sont :

- ancrage au réel ;
- révisabilité ;
- bonus de cohérence ;
- contre-arguments ;
- score factuel disponible.

---

### Formule utilisée

```python
EX = max(
    surinterpretation_factuelle,
    auto_validation_narrative,
    fausse_causalite,
    causalite_abusive
)

M_placebo = ((N + 2D) - G) * EX

EP_heuristique = (
    CF + PI + CT + ACT + SC + ND
) - (
    AR + RV + BC + CA + HF
)
score_theorique = max(0.0, min(M_placebo, 1.0))

score_heuristique = max(
    0.0,
    min((EP_heuristique / 4) * max(EX, 0.25), 1.0)
)

score = (
    score_theorique * 0.60
) + (
    score_heuristique * 0.40
)
```

Où :

- **EX** = expérience auto-validante / surinterprétation vécue  
- **N** = expérience intégrée, approximée par l’ancrage, la cohérence et la révisabilité  
- **D** = certitude  
- **G** = savoir articulé, approximé par le score factuel disponible  

Et :

- **CF** = certitude forte  
- **PI** = prémisses implicites  
- **CT** = cohérence trompeuse  
- **ACT** = cohérence trompeuse avancée  
- **SC** = causalité simplifiée / abusive  
- **ND** = pression ou surdétermination narrative  

Facteurs correcteurs :

- **AR** = ancrage au réel  
- **RV** = révisabilité  
- **BC** = bonus de cohérence  
- **CA** = contre-arguments  
- **HF** = score factuel disponible  

---

### Couleurs

🟢 **Vert — Faible**  
L’expérience reste prudente et ne devient pas une preuve suffisante.

🟡 **Jaune — Modéré**  
Le vécu commence à soutenir la conviction.

🟠 **Orange — Élevé**  
Le ressenti sert fortement de validation subjective.

🔴 **Rouge — Très élevé**  
L’expérience semble devenir une preuve auto-validée peu révisable.

---

### Lecture

🟢 **Faible** : expérience prudente  
🟡 **Modéré** : validation partielle par le ressenti  
🟠 **Élevé** : vécu fortement utilisé comme preuve  
🔴 **Très élevé** : certitude auto-validée par l’expérience  

---

### Attention

Un score élevé ne signifie pas que l’expérience est fausse.

Il indique seulement que le discours semble attribuer au vécu une valeur démonstrative supérieure au savoir disponible.
""")

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True)

st.markdown("""
<h3 style="text-align:center;">VERDICT FINAL</h3>
""", unsafe_allow_html=True)

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True)    


# =============================
# Barre de crédibilité finale
# =============================
final_score = result.get("final_credibility_score", score)
final_score = max(0, min(final_score, 20))

if final_score < 6:
    couleur_c = "🔴"
    color_c = "#dc2626"
    etiquette_c = "Très fragile"
    message_c = "Le texte présente de fortes fragilités structurelles ou vérifiables."
elif final_score < 9:
    couleur_c = "🟠"
    color_c = "#f97316"
    etiquette_c = "Fragile"
    message_c = "Le texte contient plusieurs fragilités importantes."
elif final_score < 13:
    couleur_c = "🟡"
    color_c = "#facc15"
    etiquette_c = "Prudente"
    message_c = "Le raisonnement est présent, mais certaines affirmations reposent davantage sur des idées générales que sur des éléments vérifiables."
elif final_score < 16:
    couleur_c = "🟢"
    color_c = "#22c55e"
    etiquette_c = "Solide"
    message_c = "Le texte présente une crédibilité globale correcte, avec peu de signaux problématiques."
else:
    couleur_c = "🟢"
    color_c = "#15803d"
    etiquette_c = "Très solide"
    message_c = "Le texte présente une structure cognitive robuste et peu de signaux de fragilité."

st.subheader(f"{couleur_c} Crédibilité finale : {etiquette_c}")

st.caption(
    "Cette jauge synthétise la crédibilité globale du texte en combinant "
    "la solidité factuelle, l’équilibre cognitif entre savoir et certitude, "
    "et la pression discursive détectée dans le langage."
)

st.markdown(f"""
<div style="width:100%; margin-top:10px; margin-bottom:10px;">
    <div style="
        width:100%;
        height:26px;
        background:#e5e7eb;
        border-radius:12px;
        overflow:hidden;
        border:1px solid #cbd5e1;
    ">
        <div style="
            width:{max(min(final_score / 20, 1) * 100, 3)}%;
            height:100%;
            background:{color_c};
            transition:width 0.4s ease;
        "></div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(
    f"<b style='color:{color_c}'>{etiquette_c}</b> — Score final : {round(final_score,1)}/20",
    unsafe_allow_html=True
)

st.caption(message_c)

with st.popover("ℹ️ Formule / explication"):

    st.subheader(f"{T['verdict']} : {couleur_c} Crédibilité finale — {etiquette_c}")
    st.caption(f"Score final : {round(final_score, 1)}/20 — {message_c}")
    st.subheader(T["summary"])

    m1, m2 = st.columns(2)
    m1.metric("HFS", round(result["hard_fact_score"], 1))
    m2.metric("G — gnōsis", round(result["G"], 2))
    
    m3, m4 = st.columns(2)
    m3.metric("N — nous", round(result["N"], 2))
    m4.metric("D — doxa", round(result["D"], 2))
    
    m5, m6 = st.columns(2)
    m5.metric("Pression discursive", round(result.get("discursive_pressure", 0), 2))
    m6.metric("ID", round(result.get("ID", 0), 2))
    
    m7, m8 = st.columns(2)
    m7.metric("Pénalité jauges", round(result.get("display_gauge_penalty", 0), 2))
    m8.metric("Score final", round(final_score, 1))
    
    st.markdown(f"""
    Cette jauge synthétise la **crédibilité globale du texte**.
    
    Elle combine trois dimensions :
    
    - la solidité factuelle du texte  
    - l’équilibre cognitif entre connaissance, compréhension et certitude  
    - la pression discursive détectée dans le langage  
    
    ---
    
    ### 1️⃣ Solidité factuelle
    
    `HFS = hard_fact_score / 20`
    
    Dans cette analyse :
    
    `HFS = {round(result["hard_fact_score"], 1)} / 20`
    
    ---
    
    ### 2️⃣ Calibration cognitive
    
    `OC = (G + N) / (G + N + D)`
    
    avec :
    
    G = gnōsis  
    N = nous  
    D = doxa  
    
    Dans cette analyse :
    
    `OC = ({round(result["G"],2)} + {round(result["N"],2)}) / ({round(result["G"],2)} + {round(result["N"],2)} + {round(result["D"],2)})`
    
    `OC ≈ {round((result["G"] + result["N"]) / max((result["G"] + result["N"] + result["D"]), 1), 2)}`
    
    ---
    
    ### 3️⃣ Indice de pression discursive
    
    `ID = 1 − pression_discursive`
    
    avec :
    
    `pression_discursive = propagande + pression_rhétorique`
    
    Plus la pression discursive est forte, plus le score final diminue.
    
    ---
    
    ### 4️⃣ Formule heuristique principale
    
    `score_initial = 20 × HFS × OC × ID`
    
    ---
    
    ### 5️⃣ Ajustement final
    
    `score_final = score_initial − pénalité_jauges`
    
    Score final observé :
    
    `score_final = {round(final_score, 1)} / 20`
    
    ---
    
    ### Interprétation du score final
    
    0–5 : crédibilité très fragile  
    6–9 : crédibilité fragile  
    10–14 : crédibilité prudente  
    15–20 : crédibilité robuste
    """)

    st.markdown("""
    <div style="text-align:center; margin:25px 0; color:#bbb;">
    ✦ ✦ ✦
    </div>
    """, unsafe_allow_html=True)
    
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
────────── ✦ ──────────
</div>
""", unsafe_allow_html=True)


st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

life_score = round((result.get("hard_fact_score", 0) / 20) * 100, 1)

# =============================
# Cerveau DOXA
# =============================

brain = result.get("doxa_brain", {})

st.markdown("### 🧠 Cerveau DOXA")

st.markdown(
    f"""
<div style='
border:1px solid #334155;
border-radius:16px;
padding:18px;
margin:12px 0 18px 0;
background:linear-gradient(135deg, rgba(15,23,42,0.06), rgba(30,41,59,0.03));
'>
    <div style='font-size:20px; font-weight:800; margin-bottom:6px;'>
        Diagnostic cognitif global
    </div>
    <div style='font-size:15px; color:#475569;'>
        {brain.get("brain_verdict", "Diagnostic indisponible.")}
    </div>
</div>
""",
    unsafe_allow_html=True
)

# Variables principales
stability = result.get("cognitive_stability", 0)
gravity = result.get("cognitive_gravity", 1 - stability)

dominant_regime = result.get(
    "dominant_regime",
    "Non déterminé"
)

brain_advice = result.get(
    "brain_advice",
    ""
)

# ✅ Correction dynamique avec jauges secondaires
secondary_pressure = compute_secondary_alert_pressure(result)

gravity = min(1.0, gravity + secondary_pressure * 0.65)
stability = max(0.0, stability - secondary_pressure * 0.55)

# Couleur stabilité
if stability >= 0.80:
    stability_label = "Stable"
    stability_color = "#16a34a"
elif stability >= 0.60:
    stability_label = "Assez stable"
    stability_color = "#facc15"
elif stability >= 0.40:
    stability_label = "Instable"
    stability_color = "#f97316"
else:
    stability_label = "Très instable"
    stability_color = "#dc2626"

# Ligne de métriques principales
c1, c2, c3, c4 = st.columns(4)

c1.metric("Stabilité cognitive", f"{stability:.2f}")
c2.metric("Gravité cognitive", f"{gravity:.2f}")
c3.metric("Régime dominant", dominant_regime)
c4.metric("Vitalité cognitive", f"{life_score}%")

# Grosse jauge de stabilité
st.markdown("#### Stabilité cognitive")

render_custom_gauge(stability, stability_color)

st.markdown(
    f"""
<div style='
border:1px solid {stability_color};
border-radius:12px;
padding:12px;
margin-top:8px;
background-color:rgba(255,255,255,0.03);
'>
<b style='color:{stability_color};'>
Stabilité {stability_label} — {stability:.2f}
</b><br>
"Le discours reste relativement cohérent, mais plusieurs signaux secondaires réduisent son équilibre cognitif."
</div>
""",
    unsafe_allow_html=True
)

with st.popover("ℹ️ Comprendre le cerveau DOXA"):
    st.markdown(f"""
### Cerveau DOXA

Le **Cerveau DOXA** est une synthèse générale de l’analyse.

Il regroupe les principaux indicateurs cognitifs du discours afin de produire un diagnostic global.

---

### Résultat de cette analyse

**État : {stability_label}**

**Stabilité cognitive : {stability:.2f}**

**Gravité cognitive : {gravity:.2f}**

**Régime dominant : {dominant_regime}**

---

### 1️⃣ Stabilité cognitive

La stabilité cognitive indique si le discours reste globalement équilibré ou s’il présente des signes de dérive.

Une stabilité élevée signifie que le texte présente peu de signaux de désalignement cognitif.

Dans cette analyse :

`stabilité = {stability:.2f}`

---

### 2️⃣ Gravité cognitive

La gravité cognitive représente le niveau global de dérive détecté dans le discours.

Elle est liée à la stabilité :

`gravité = 1 − stabilité`

Dans cette analyse :

`gravité = {gravity:.2f}`

---

### 3️⃣ Régime dominant

Le régime dominant indique la tendance cognitive principale du texte.

Il peut signaler par exemple :

- discours équilibré
- mécroyance probable
- pseudo-savoir
- manipulation rhétorique
- mensonge stratégique
- structure mixte ou ambiguë

Dans cette analyse :

**{dominant_regime}**

---

### 4️⃣ Indice classique

L’indice classique correspond au noyau cognitif :

`M = (G + N) − D`

Dans cette analyse :

`M = {round(result.get("M", 0), 2)}`

---

### 5️⃣ Indice ajusté

L’indice ajusté ajoute des corrections complémentaires au score classique.

Il permet d’obtenir une lecture plus large du niveau de robustesse cognitive du discours, en tenant compte non seulement du noyau **M = (G + N) − D**, mais aussi des pénalités, des fragilités discursives et des jauges secondaires détectées.

Dans cette analyse :

**Indice ajusté = {round(result.get("M_adjusted", result.get("ME", 0)), 2)}**

---

### 6️⃣ Score de raisonnement

Le score de raisonnement correspond au **Hard Fact Score**.

Il mesure la solidité factuelle et argumentative du texte.

Dans cette analyse :

`Score de raisonnement = {round(result.get("hard_fact_score", 0), 1)}/20`

---

### 7️⃣ Vitalité cognitive

La vitalité cognitive est le score de raisonnement converti en pourcentage.

Formule :

`vitalité = (hard_fact_score / 20) × 100`

Dans cette analyse :

`vitalité = {life_score}%`

---

brain_summary = (
    f"État : {result.get('brain_state', 'Non déterminé')} | "
    f"Stabilité : {result.get('cognitive_stability', 0):.2f} | "
    f"Gravité : {result.get('cognitive_gravity', 0):.2f} | "
    f"Régime dominant : {result.get('dominant_regime', 'Non déterminé')} | "
    f"M={result.get('M', 0):.2f}, "
    f"ME={result.get('ME', 0):.2f}, "
    f"Factuel={result.get('hard_fact_score', 0):.1f}/20"
)

### Lecture globale

{result.get("brain_summary", "")}

Même si la stabilité est élevée, le régime dominant peut signaler une fragilité particulière, comme du **pseudo-savoir**, une **mécroyance probable** ou une **orientation rhétorique**.
""")


# =============================
# Gravité cognitive globale
# =============================
# 👉 utiliser la gravité corrigée déjà calculée
# NE PAS relire result ici
# gravity est déjà modifiée plus haut
# Synchronisation finale cerveau DOXA
result["cognitive_gravity"] = gravity
result["cognitive_stability"] = stability
result["gravity"] = gravity
result["stability"] = stability
gravity_pct = round(gravity * 100, 1)

if gravity < 0.2:
    gravity_label = "Faible"
    gravity_color = "#16a34a"
    gravity_text = "Discours globalement sain."
elif gravity < 0.4:
    gravity_label = "Modérée"
    gravity_color = "#ca8a04"
    gravity_text = "Quelques tensions cognitives."
elif gravity < 0.6:
    gravity_label = "Élevée"
    gravity_color = "#f97316"
    gravity_text = "Dérive discursive notable."
elif gravity < 0.8:
    gravity_label = "Très élevée"
    gravity_color = "#dc2626"
    gravity_text = "Structure discursive problématique."
else:
    gravity_label = "Critique"
    gravity_color = "#7f1d1d"
    gravity_text = "Convergence de manipulation ou désalignement cognitif."

st.markdown("### Gravité cognitive globale")

render_custom_gauge(gravity, gravity_color)

st.markdown(
    f"""
<div style='
border:1px solid {gravity_color};
border-radius:12px;
padding:12px;
margin-top:8px;
background-color:rgba(255,255,255,0.03);
'>
<b style='color:{gravity_color};'>
Gravité {gravity_label} — {gravity_pct}%
</b><br>
{gravity_text}
</div>
""",
    unsafe_allow_html=True
)

with st.popover("ℹ️ Comprendre cette jauge"):
    st.markdown(f"""
### Gravité cognitive globale

Cette jauge estime le **niveau global de dérive cognitive** du discours.

Elle ne mesure pas directement si le texte est vrai ou faux.  
Elle mesure si sa structure présente des signes de **déséquilibre cognitif**, de fermeture argumentative, de pression discursive ou de fragilité logique.

#### Résultat de cette analyse

**Gravité cognitive : {gravity_pct}%**

**Verdict : {gravity_label}**


### Interprétation de la gravité cognitive

La **gravité cognitive** indique le **niveau global de dérive du raisonnement** dans le discours analysé.

Plus la gravité est faible, plus le discours est **cognitivement sain et équilibré**.  
Plus elle est élevée, plus le texte présente des **signaux de manipulation, de pression rhétorique ou de désalignement entre faits et certitudes**.

#### Échelle d’interprétation

| Gravité | Lecture |
|--------|--------|
| **0.00 – 0.20** | Gravité faible — discours globalement sain |
| **0.20 – 0.40** | Gravité modérée — quelques tensions cognitives |
| **0.40 – 0.60** | Gravité élevée — dérive discursive notable |
| **0.60 – 0.80** | Gravité très élevée — structure discursive problématique |
| **0.80 – 1.00** | Gravité critique — convergence de manipulation ou désalignement cognitif |

#### Signaux pris en compte

La jauge combine plusieurs indicateurs détectés dans le texte :

- indice de **mensonge potentiel**
- **pression rhétorique**
- **propagande discursive**
- **dissonance factuelle**
- **fermeture cognitive**
- **faiblesse factuelle**

Ces signaux sont agrégés pour produire un **diagnostic global de santé cognitive du discours**.

### Formule heuristique actuelle

La gravité cognitive est calculée par familles de pression :

- noyau cognitif : M, ME, Hard Fact, clôture
- pression discursive : rhétorique, propagande, émotion, certitude
- fragilité logique : dissonance, cohérence trompeuse, fausses causalités, analogies
- cadrage idéologique : prémisses, consensus, opposition binaire, glissements sémantiques
- ancrage réel fragile : faiblesse de l’ancrage au réel, statistiques, référentiels manquants

Formule simplifiée :

gravité =
    (noyau_cognitif × 0.28)
  + (pression_discursive × 0.22)
  + (fragilité_logique × 0.20)
  + (cadrage_idéologique × 0.18)
  + (ancrage_réel_fragile × 0.12)
  − (bonus_cognitif × 0.12)

Le score final est borné entre 0 et 1.

#### Valeurs de cette analyse

- Noyau cognitif : {round(result.get("core_pressure",0)*100,1)}%
- Pression discursive : {round(result.get("discursive_pressure_brain",0)*100,1)}%
- Fragilité logique : {round(result.get("reasoning_pressure_brain",0)*100,1)}%
- Cadrage idéologique : {round(result.get("ideological_pressure_brain",0)*100,1)}%
- Ancrage réel fragile : {round(result.get("reality_pressure_brain",0)*100,1)}%
- Bonus cognitif : {round(result.get("cognitive_bonus",0)*100,1)}%

#### Interprétation

0 → discours cognitivement stable  
1 → dérive cognitive maximale
""")

# =============================
# Vitalité cognitive
# =============================
life_score = round((result.get("hard_fact_score", 0) / 20) * 100, 1)
life_value = life_score / 100

if life_score < 30:
    life_label = "Faible"
    life_color = "#dc2626"
    life_text = "Vitalité cognitive faible — le discours manque d’appuis solides."
elif life_score < 50:
    life_label = "Fragile"
    life_color = "#f97316"
    life_text = "Vitalité cognitive fragile — plusieurs éléments restent insuffisamment fondés."
elif life_score < 70:
    life_label = "Modérée"
    life_color = "#facc15"
    life_text = "Vitalité cognitive modérée — le discours présente des appuis, mais reste perfectible."
elif life_score < 85:
    life_label = "Solide"
    life_color = "#16a34a"
    life_text = "Le discours contient une matière cognitive dense : les idées sont développées, reliées et appuyées."
else:
    life_label = "Très solide"
    life_color = "#15803d"
    life_text = "Vitalité cognitive très solide — le discours présente une forte robustesse cognitive."

st.markdown("### Vitalité cognitive")
render_custom_gauge(life_value, life_color)

st.markdown(
    f"""
<div style='
border:1px solid {life_color};
border-radius:12px;
padding:12px;
margin-top:8px;
background-color:rgba(255,255,255,0.03);
'>
<b style='color:{life_color};'>
Vitalité cognitive {life_label} — {life_score}%
</b><br>
{life_text}
</div>
""",
    unsafe_allow_html=True
)
with st.popover("ℹ️ Comprendre cette jauge"):
    st.markdown(f"""
### Vitalité cognitive

Cette jauge exprime la **vitalité cognitive du discours** sous forme de pourcentage.

Elle indique dans quelle mesure le texte présente une structure suffisamment fondée, vérifiable et équilibrée.

---

### Résultat de cette analyse

Vitalité cognitive : **{life_score}%**

Verdict : **{life_label}**

---

### Formule heuristique réelle

`vitalité_cognitive = (hard_fact_score / 20) × 100`

Dans cette analyse :

`vitalité_cognitive = ({round(result.get("hard_fact_score", 0), 1)} / 20) × 100`

Soit :

**{life_score}%**

---

### Ce que mesure cette jauge

Elle dépend directement du **HFS — Hard Fact Score**.

Elle tient donc compte de :

- la vérifiabilité des affirmations
- la qualité des sources
- l’équilibre entre **G**, **N** et **D**
- le risque rhétorique
- les pénalités de crédibilité
- le bonus épistémique éventuel

---

### Interprétation

- **0–30%** : vitalité faible
- **30–50%** : vitalité fragile
- **50–70%** : vitalité modérée
- **70–85%** : vitalité solide
- **85–100%** : vitalité très solide

---

### Lecture du résultat

Une vitalité cognitive de **{life_score}%** indique une vitalité **{life_label.lower()}**.

{life_text}
""")

# =============================
# Familles de pression DOXA
# =============================

st.markdown("### 🧠 Familles de pression DOXA")

c1, c2, c3 = st.columns(3)

c1.metric(
    "Noyau cognitif",
    f"{round(result.get('core_pressure',0)*100,1)}%"
)

c2.metric(
    "Pression discursive",
    f"{round(result.get('discursive_pressure_brain',0)*100,1)}%"
)

c3.metric(
    "Fragilité logique",
    f"{round(result.get('reasoning_pressure_brain',0)*100,1)}%"
)

c4, c5, c6 = st.columns(3)

c4.metric(
    "Cadrage idéologique",
    f"{round(result.get('ideological_pressure_brain',0)*100,1)}%"
)

c5.metric(
    "Ancrage réel fragile",
    f"{round(result.get('reality_pressure_brain',0)*100,1)}%"
)

c6.metric(
    "Famille dominante",
    result.get(
        "brain_dominant_family",
        "Non déterminée"
    )
)

st.caption(
    "Le cerveau DOXA agrège les grandes familles de pression qui influencent le diagnostic global."
)

st.divider()
    
with st.expander("📊 Résumé détaillé du cerveau DOXA"):
    st.write(
    f"État : {result.get('brain_state', 'Non déterminé')} | "
    f"Stabilité : {result.get('cognitive_stability', 0):.2f} | "
    f"Gravité : {result.get('cognitive_gravity', 0):.2f} | "
    f"Régime dominant : {result.get('dominant_regime', 'Non déterminé')} | "
    f"M={result.get('M', 0):.2f}, "
    f"ME={result.get('ME', 0):.2f}, "
    f"Factuel={result.get('hard_fact_score', 0):.1f}/20"
)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Indice classique", round(result.get("M", 0), 2), help=T["help_classic_score"])
    col2.metric("Indice ajusté", round(result.get("improved", 0), 2), help=T["help_improved_score"])
    col3.metric("Score de raisonnement", round(result.get("hard_fact_score", 0), 1), help=T["help_hard_fact_score"])
    col4.metric("Vitalité cognitive", f"{life_score}%")
    
# =============================
# Partage des résultats
# =============================

st.markdown("### Partager l’analyse")

summary, encoded = generate_share_block(result)

st.code(summary)

st.link_button(
    "📧 Envoyer par email",
    f"mailto:?subject=Analyse DOXA Detector&body={encoded}",
    use_container_width=True
)
# =============================
# Analyse sémantique du discours
# =============================

st.subheader("Analyse sémantique du discours")
st.caption(
    "Analyse la cohérence du sens et la stabilité conceptuelle du discours afin d’affiner l’évaluation épistémique."
)

semantic_score = result.get("semantic_score", None)

if st.session_state.get("semantic_mode", False):

    if semantic_score is not None:

        st.progress(semantic_score / 20)
        st.caption(f"Score sémantique : {semantic_score}/20")

        delta = round(semantic_score - base_score, 1)

        st.metric(
            "Influence sémantique sur l’évaluation épistémique",
            f"{delta:+}/20"
        )

    else:
        st.info("Analyse sémantique activée, mais aucun score n’est encore calculé.")

else:
    st.info("Activez l’analyse sémantique pour calculer cette jauge.")

# -----------------------------
# Mode sémantique
# -----------------------------
if "semantic_mode" not in st.session_state:
    st.session_state.semantic_mode = False

st.markdown("### Analyse sémantique")
st.caption(
    "Cette analyse sémantique sert à corroborer les jauges ayant déclenché des pénalités. "
    "Elle vérifie si le sens réel des affirmations confirme les signaux détectés "
    "par l’analyse analogique du langage."
)

if st.button(
    "Activer l’analyse sémantique",
    key="semantic_normal",
    use_container_width=True
):
    st.session_state.semantic_mode = True

if st.session_state.semantic_mode:
    st.success("Analyse sémantique activée.")
else:
    st.info(
    "Analyse sémantique inactive. Les pénalités reposent uniquement "
    "sur l’analyse analogique du discours."
)

sp1, col_center, sp2 = st.columns([2,3,2])

with col_center:

    st.markdown("### 🧠 Modules d’analyse DOXA")

    with st.expander("🧠 Voir le résumé complet des pénalités", expanded=False):

        # =============================
        # Pénalités appliquées
        # =============================

        st.markdown("### Pénalités appliquées")

        # =============================
        # Résumé chiffré
        # =============================
        

        colp1, colp2, colp3 = st.columns(3)

        with colp1:
            st.metric(
                "Pénalité crédibilité",
                round(result.get("credibility_penalty_total", 0), 2)
            )

        with colp2:
            st.metric(
                "Boost mensonge",
                round(result.get("lie_boost_total", 0), 2)
            )

        with colp3:
            st.metric(
                "Score final",
                f"{result.get('final_credibility_score', result['hard_fact_score'])}/20"
            )

        st.caption(
            "Les pénalités corrigent le score lorsque le texte accumule des signaux "
            "de fermeture cognitive, de manipulation ou de raisonnement fragile."
        )

        with st.expander("Voir le détail des pénalités"):
            st.write(result.get("weighted_red_flags", []))


    st.divider()

    st.subheader("Diagnostic cognitif")
    life_score = round((result["hard_fact_score"] / 20) * 100, 1)
    mecroyance_bar = max(0.0, min(1.0, (result["M"] + 10) / 30))


    st.divider()

    # =============================
    # Triangle cognitif
    # =============================
    st.subheader("Triangle cognitif G-N-D")
    st.caption("Le triangle G–N–D positionne un texte selon trois forces :"
    "savoir (G), compréhension (N) et certitude (D)."
    
    "L’équilibre entre ces dimensions révèle si le discours est ouvert, fragile ou cognitivement fermé."
    
    "👉 Si un texte sort du triangle, cela indique une structure incohérente ou instable :"
    "une des dimensions dépasse les autres de manière disproportionnée,"
    "rendant le discours difficilement interprétable ou épistémiquement non viable.")
    
    fig_triangle = plot_cognitive_triangle_3d(result["G"], result["N"], result["D"])
    st.pyplot(fig_triangle, use_container_width=True)


st.divider()

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

st.subheader("Cartographie discursive complémentaire")

st.caption(
    "Cette cartographie regroupe les principaux mécanismes discursifs détectables dans un texte : "
    "jugements de valeur, prémisses implicites, structures propagandistes, confusions logiques, "
    "simulations scientifiques, biais narratifs et mécanismes de fermeture cognitive."
)

st.caption(
    "Elle est complétée par une analyse logique des raisonnements "
    "(syllogismes, enthymèmes et sophismes) ainsi que par des indicateurs "
    "stratégiques permettant d’identifier certaines formes de manipulation argumentative."
)

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# =============================
# 🗣️ 2. PRESSIONS DISCURSIVES
# =============================
st.subheader("🗣️ Pressions discursives")
st.caption("Forces rhétoriques influençant la perception et l’interprétation du discours.")

pd1, pd2, pd3, pd4 = st.columns(4)

with pd1:
    st.markdown("### Pression rhétorique")
    st.caption(
        "Cette jauge ne mesure pas un mensonge certain, mais l’intensité des procédés discursifs "
        "susceptibles d’orienter, de verrouiller ou de dramatiser un discours."
    )

    rp = result["rhetorical_pressure"]
    rp_label, rp_color = interpret_rhetorical_pressure(rp)

    st.markdown(f"""
    <div style="width:100%; margin-top:10px; margin-bottom:10px;">
        <div style="
            width:100%;
            height:26px;
            background:#e5e7eb;
            border-radius:12px;
            overflow:hidden;
            border:1px solid #cbd5e1;
        ">
            <div style="
                width:{rp*100}%;
                height:100%;
                background:{rp_color};
                transition:width 0.4s ease;
            "></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(
        f"<b style='color:{rp_color}'>{rp_label}</b> — {round(rp*100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption("Pression rhétorique faible ⟵⟶ Pression rhétorique forte")

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Pression rhétorique")

        st.write(
            "Cette jauge mesure l’intensité des procédés discursifs qui orientent "
            "la perception du lecteur sans nécessairement reposer sur des preuves."
        )

        st.markdown("**Principe**")
        
        st.write(
            "Le calcul repose sur plusieurs dimensions rhétoriques capables "
            "d’orienter la perception du lecteur sans nécessairement démontrer "
            "les affirmations avancées."
        )
        
        st.write(
            "Le modèle combine notamment l’amplification, la saturation rhétorique, "
            "la persuasion, l’attaque, les sous-entendus implicites, le soupçon "
            "systémique et la cohérence performative."
        )
        
        st.markdown("**Formule utilisée**")
        
        st.code(
            "pression = (\n"
            " amplification × 0.16\n"
            "+ saturation_rhetorique × 0.20\n"
            "+ persuasion × 0.12\n"
            "+ attaque × 0.14\n"
            "+ implicite × 0.08\n"
            "+ soupcon_systemique × 0.10\n"
            "+ coherence_performative × 0.08\n"
            "+ colere × 0.08\n"
            "+ peur × 0.04\n"
            ")\n\n"
            "si discours_rapporté > 0.45 : pression × 0.75\n"
            "si discours_rapporté > 0.25 : pression × 0.88\n"
            "pression = min(max(pression, 0), 1.0)"
        )
        
        st.markdown("**Poids des mécanismes**")
        
        st.code(
            "amplification = 0.18\n"
            "saturation_rhetorique = 0.22\n"
            "persuasion = 0.14\n"
            "attaque = 0.16\n"
            "implicite = 0.10\n"
            "soupcon_systemique = 0.10\n"
            "coherence_performative = 0.10"
            "colere = 0.08\n"
            "peur = 0.04"
        )

        st.markdown("**Valeur actuelle**")
        st.write(f"Pression rhétorique = {round(rp * 100, 1)}%")
        st.code(f"pression = {rp:.3f}")

        st.markdown("**Interprétation**")
        st.write(
            "Plus la valeur est élevée, plus le discours utilise des leviers rhétoriques "
            "pour orienter la conclusion plutôt que de la démontrer."
        )

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours neutre\n"
            "🟡 Modérée : orientation légère\n"
            "🟠 Élevée : discours orienté\n"
            "🔴 Très élevée : forte pression narrative"
        )

with pd2:
    st.markdown("### Charge émotionnelle")
    st.caption("Intensité affective du lexique utilisé pour orienter la lecture.")

    emotional_value = result["emotional_intensity_score"]

    if emotional_value < 0.15:
        emotional_label, emotional_color = "Faible", "#ca8a04"
    elif emotional_value < 0.35:
        emotional_label, emotional_color = "Modérée", "#f97316"
    elif emotional_value < 0.60:
        emotional_label, emotional_color = "Élevée", "#ea580c"
    else:
        emotional_label, emotional_color = "Très élevée", "#dc2626"

    render_custom_gauge(emotional_value, emotional_color)

    st.markdown(
        f"<b style='color:{emotional_color}'>{emotional_label}</b> — {round(emotional_value * 100, 1)}%",
        unsafe_allow_html=True
    )
    st.caption(result["emotional_intensity_interpretation"])

    with st.expander("🔎 Marqueurs détectés", expanded=False):
        markers = result.get("emotional_intensity_markers", [])
        if not markers:
            st.info("Aucun marqueur émotionnel notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Charge émotionnelle")
    
        st.write(
            "Cette jauge mesure l’intensité affective du vocabulaire utilisé. "
            "Elle repère les mots qui peuvent orienter la lecture par l’émotion plutôt que par la démonstration."
        )
    
        st.markdown("**Principe**")
        
        st.write(
            "La charge émotionnelle mesure l’intensité affective du discours "
            "à partir de plusieurs registres émotionnels : peur, colère, urgence, "
            "fatalisme, victimisation et exaltation."
        )
        
        st.write(
            "Chaque registre possède un poids différent selon sa capacité "
            "à orienter émotionnellement la lecture."
        )
        
        st.markdown("**Formule utilisée**")
        
        st.code(
            "score = (\n"
            " peur × 0.22\n"
            "+ colere × 0.26\n"
            "+ urgence × 0.18\n"
            "+ fatalisme × 0.12\n"
            "+ victimisation × 0.12\n"
            "+ exaltation × 0.10\n"
            ")\n"
            "score = min(score, 1.0)"
        )
    
        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(emotional_value * 100, 1)}%**")
        st.write(f"Niveau : **{emotional_label}**")
    
        emotionals = result.get("emotional_registers", {})
        
        st.code(
            f"peur = {emotionals.get('peur', 0):.2f}\n"
            f"colère = {emotionals.get('colere', 0):.2f}\n"
            f"urgence = {emotionals.get('urgence', 0):.2f}\n"
            f"fatalisme = {emotionals.get('fatalisme', 0):.2f}\n"
            f"victimisation = {emotionals.get('victimisation', 0):.2f}\n"
            f"exaltation = {emotionals.get('exaltation', 0):.2f}\n\n"
            f"score = {emotional_value:.3f}"
        )
    
        st.markdown("**Interprétation actuelle**")
        st.write(result["emotional_intensity_interpretation"])
    
        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : vocabulaire peu chargé émotionnellement\n"
            "🟡 Modérée : quelques marqueurs affectifs\n"
            "🟠 Élevée : charge émotionnelle notable\n"
            "🔴 Très élevée : émotion fortement mobilisée pour orienter la lecture"
        )
    
        st.markdown("**Attention**")
        st.write(
            "Une charge émotionnelle élevée ne signifie pas que le texte est faux. "
            "Elle indique seulement que le discours agit fortement sur l’affect du lecteur."
        )
        
with pd3:
    st.markdown("### Discours rapporté / citations")
    st.caption("Détecte si le texte rapporte des propos extérieurs plutôt qu’une thèse directement assumée.")

    value = result.get("reported_speech_score", 0)

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Présent", "#84cc16"
    elif value < 0.60:
        label, color = "Élevé", "#16a34a"
    else:
        label, color = "Très élevé", "#15803d"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result.get("reported_speech_interpretation", ""))

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("reported_speech_markers", [])
        if not markers:
            st.info("Aucun marqueur de discours rapporté détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
    
        st.markdown("#### Discours rapporté / citations")
    
        st.write(
            "Cette jauge détecte si le texte rapporte des propos "
            "extérieurs plutôt que d’affirmer directement une thèse."
        )
    
        st.write(
            "Elle repère notamment :"
        )
    
        st.markdown("""
    - les citations entre guillemets ;
    - les verbes de parole : déclare, affirme, estime, explique ;
    - les marqueurs d’attribution : selon, d’après, pour.
    """)
    
        st.markdown("#### Formule utilisée")
    
        st.code(
            """quote_ratio = mots_dans_citations / mots_totaux
    marker_ratio = nombre_marqueurs / 10
    
    score = min(
        (quote_ratio * 1.8) +
        (marker_ratio * 0.5),
        1.0
    )""",
            language="python"
        )
    
        st.markdown("#### Valeur actuelle")
    
        st.write(f"Score : {round(score * 100, 1)}%")
        st.write(f"Niveau : {label}")
    
        markers = result.get("reported_speech_markers", [])
    
        st.write(f"Marqueurs détectés : {len(markers)}")
    
        st.markdown("#### Interprétation actuelle")
    
        st.write(
            result.get(
                "reported_speech_interpretation",
                "Aucune interprétation disponible."
            )
        )
    
        st.markdown("#### Lecture")
    
        st.markdown("""
    🟢 Faible : discours principalement assumé directement  
    🟡 Présent : citations ou attributions ponctuelles  
    🟠 Élevé : forte présence de discours rapporté  
    🔴 Très élevé : texte majoritairement composé de citations ou positions externes
    """)
    
        st.markdown("#### Attention")
    
        st.write(
            "Un score élevé ne signifie pas manipulation ou mensonge. "
            "Cette jauge sert aussi de modérateur afin d’éviter de "
            "surpénaliser les textes journalistiques ou analytiques "
            "rapportant des propos extérieurs."
        )
    
    
with pd4:
    st.markdown("### Asymétrie argumentative")
    st.caption("Le texte attaque davantage qu’il ne démontre.")

    value = result["argument_asymmetry_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["argument_asymmetry_interpretation"])

    with st.popover("🔎 Marqueurs détectés"):
        st.markdown("### Marqueurs détectés")

        st.write(
            "Cette jauge repose sur deux familles de marqueurs : "
            "les termes d’attaque ou de disqualification, "
            "et les termes d’appui logique ou explicatif."
        )

        st.write(f"**Attaques détectées :** {result['argument_attack_count']}")
        st.write(f"**Appuis logiques détectés :** {result['argument_support_count']}")

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Asymétrie argumentative")

        st.write(
            "Cette jauge mesure le déséquilibre entre l’attaque et la démonstration. "
            "Elle repère si le texte privilégie les formulations accusatoires, "
            "dépréciatives ou disqualifiantes, plutôt que les appuis logiques, "
            "explicatifs ou démonstratifs."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "if attack_count == 0:\n"
            "    score = 0.0\n"
            "elif argument_count == 0:\n"
            "    score = min(attack_count * 0.18, 0.65)\n"
            "else:\n"
            "    ratio = attack_count / argument_count\n"
            "    score = min(ratio * 0.22, 1.0)",
            language="python"
        )

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Attaques : **{result['argument_attack_count']}**")
        st.write(f"Appuis logiques : **{result['argument_support_count']}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["argument_asymmetry_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours globalement équilibré\n"
            "🟡 Modérée : légère asymétrie argumentative\n"
            "🟠 Élevée : l’attaque domine la démonstration\n"
            "🔴 Très élevée : rhétorique d’attaque dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une asymétrie argumentative élevée ne signifie pas que le texte est faux. "
            "Elle indique seulement que le discours attaque davantage qu’il ne démontre."
        )
            
pd5, pd6, pd7, pd8 = st.columns(4)

# -----------------------------
#  Certitude absolue
# -----------------------------
with pd5:
    st.markdown("### Certitude absolue")
    st.caption("Rigidité rhétorique et fermeture interprétative.")

    certainty_value = result["certainty_score"]

    if certainty_value < 0.20:
        certainty_label, certainty_color = "Faible", "#ca8a04"
    elif certainty_value < 0.40:
        certainty_label, certainty_color = "Modérée", "#f97316"
    elif certainty_value < 0.70:
        certainty_label, certainty_color = "Élevée", "#ea580c"
    else:
        certainty_label, certainty_color = "Très élevée", "#dc2626"

    render_custom_gauge(certainty_value, certainty_color)

    st.markdown(
        f"<b style='color:{certainty_color}'>{certainty_label}</b> — {round(certainty_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["certainty_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("certainty_markers", [])
        if not markers:
            st.info("Aucun marqueur fort de certitude absolue détecté.")
        else:
            for marker in markers:
                st.warning(marker)
    
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Certitude absolue")
    
        st.write(
            "Cette jauge détecte les formulations qui ferment l’interprétation : "
            "affirmations catégoriques, absence de nuance, impossibilité suggérée du doute."
        )
    
        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de certitude absolue. "
            "Chaque marqueur augmente le score de rigidité rhétorique."
        )
    
        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de certitude absolue détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )
    
        markers = result.get("certainty_markers", [])
    
        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(certainty_value * 100, 1)}%**")
        st.write(f"Niveau : **{certainty_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
    
        st.markdown("**Interprétation actuelle**")
        st.write(result["certainty_interpretation"])
    
        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours relativement nuancé\n"
            "🟡 Modérée : quelques affirmations catégoriques\n"
            "🟠 Élevée : forte rigidité assertive\n"
            "🔴 Très élevée : fermeture interprétative dominante"
        )
    
        st.markdown("**Attention**")
        st.write(
            "Une certitude absolue élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours laisse peu de place au doute, à la nuance ou à la révision."
        )
# -----------------------------
# Amplification de menace
# -----------------------------
with pd6:
    st.markdown("### Amplification de menace")
    st.caption("Exagération dramatique du danger ou de la gravité.")
    
    threat_value = result["threat_amplification_score"]
    
    if threat_value < 0.15:
        threat_label, threat_color = "Faible", "#ca8a04"
    elif threat_value < 0.35:
        threat_label, threat_color = "Modérée", "#f97316"
    elif threat_value < 0.60:
        threat_label, threat_color = "Élevée", "#ea580c"
    else:
        threat_label, threat_color = "Très élevée", "#dc2626"
    
    render_custom_gauge(threat_value, threat_color)
    
    st.markdown(
        f"<b style='color:{threat_color}'>{threat_label}</b> — {round(threat_value * 100, 1)}%",
        unsafe_allow_html=True
    )
    
    st.caption(result["threat_amplification_interpretation"])
    
    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("threat_amplification_markers", [])
        if not markers:
            st.info("Aucune amplification de menace notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Amplification de menace")
    
        st.write(
            "Cette jauge détecte les formulations qui dramatisent fortement un danger, "
            "une crise ou une menace."
        )
    
        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs d’amplification de menace : "
            "catastrophe, danger extrême, effondrement, menace existentielle, ou formulations équivalentes."
        )
    
        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs d’amplification de menace détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )
    
        markers = result.get("threat_amplification_markers", [])
    
        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(threat_value * 100, 1)}%**")
        st.write(f"Niveau : **{threat_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
    
        st.markdown("**Interprétation actuelle**")
        st.write(result["threat_amplification_interpretation"])
    
        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : menace peu dramatisée\n"
            "🟡 Modérée : quelques formulations alarmistes\n"
            "🟠 Élevée : danger fortement amplifié\n"
            "🔴 Très élevée : dramatisation centrale du discours"
        )
    
        st.markdown("**Attention**")
        st.write(
            "Une amplification de menace élevée ne signifie pas que le danger est imaginaire. "
            "Elle indique que le texte intensifie fortement la perception du risque."
        )

# -----------------------------
# Rigidité doxique
# -----------------------------
with pd7:
    st.markdown("### Rigidité doxique")
    st.caption("Degré de fermeture du texte par excès de certitude partagée.")

    value = result["doxic_rigidity_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["doxic_rigidity_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("doxic_rigidity_markers", [])
        if not markers:
            st.info("Aucune rigidité doxique notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Rigidité doxique")
    
        st.write(
            "Cette jauge mesure la tendance du discours à s’appuyer sur une certitude partagée "
            "ou supposée évidente, réduisant la possibilité de remise en question."
        )
    
        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de rigidité doxique : "
            "affirmations collectives, évidences supposées, ou consensus implicites renforçant la certitude."
        )
    
        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de rigidité doxique détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )
    
        markers = result.get("doxic_rigidity_markers", [])
    
        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
    
        st.markdown("**Interprétation actuelle**")
        st.write(result["doxic_rigidity_interpretation"])
    
        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours ouvert et révisable\n"
            "🟡 Modérée : quelques évidences implicites\n"
            "🟠 Élevée : forte adhésion à une certitude partagée\n"
            "🔴 Très élevée : fermeture collective du discours"
        )
    
        st.markdown("**Attention**")
        st.write(
            "Une rigidité doxique élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours s’appuie fortement sur des évidences supposées "
            "plutôt que sur une démonstration ouverte à la discussion."
        )
# -----------------------------
# Victimisation stratégique
# -----------------------------
with pd8:
    st.markdown("### Victimisation stratégique")
    st.caption("Mise en scène d’une persécution ou d’un empêchement de dire.")

    value = result["victimization_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["victimization_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("victimization_markers", [])
        if not markers:
            st.info("Aucune victimisation stratégique notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Victimisation stratégique")

        st.write(
            "Cette jauge détecte les situations où le discours met en scène une persécution, "
            "une censure ou un empêchement de s’exprimer, afin de renforcer son impact ou sa légitimité."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de victimisation : "
            "injustice subie, interdiction de dire, oppression, ou sentiment d’attaque ciblée."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de victimisation détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("victimization_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["victimization_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : pas de mise en scène victimaire\n"
            "🟡 Modérée : quelques éléments de victimisation\n"
            "🟠 Élevée : victimisation notable dans le discours\n"
            "🔴 Très élevée : posture victimaire dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une victimisation stratégique élevée ne signifie pas que la situation décrite est fausse. "
            "Elle indique que le discours mobilise une posture de victime pour renforcer son effet."
        )
        
    st.divider()
    
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# =============================
# 🧩 3. STRUCTURE DU RAISONNEMENT
# =============================
st.subheader("🧩 Structure du raisonnement")
st.caption("Analyse de la cohérence interne du discours, indépendamment de sa vérifiabilité.")

sr1, sr2, sr3, sr4 = st.columns(4)

# -----------------------------
#  Cohérence discursive
# -----------------------------
with sr1:
    st.markdown("### Cohérence discursive")
    st.caption("Solidité interne du texte, indépendamment de sa vérifiabilité.")

    coherence_score = result["discursive_coherence_score"]
    coherence_value = coherence_score / 20

    if coherence_value < 0.20:
        coherence_label, coherence_color = "Faible", "#dc2626"
    elif coherence_value < 0.40:
        coherence_label, coherence_color = "Limitée", "#f97316"
    elif coherence_value < 0.65:
        coherence_label, coherence_color = "Correcte", "#ca8a04"
    elif coherence_value < 0.85:
        coherence_label, coherence_color = "Solide", "#84cc16"
    else:
        coherence_label, coherence_color = "Très forte", "#16a34a"

    render_custom_gauge(coherence_value, coherence_color)

    st.markdown(
        f"<b style='color:{coherence_color}'>{coherence_label}</b> — {coherence_score}/20",
        unsafe_allow_html=True
    )

    st.caption(result["discursive_coherence_label"])

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Cohérence discursive")

        st.write(
            "Cette jauge mesure la solidité interne du texte. "
            "Elle ne vérifie pas si le texte est vrai ou faux : elle observe si le discours est construit, stable et cohérent."
        )

        st.markdown("**Principe**")
        st.write(
            "Le score combine plusieurs dimensions : logique discursive, stabilité thématique, longueur utile, "
            "cohérence entre paragraphes, puis applique des pénalités en cas de contradiction ou de rupture de sujet."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "score = logic_score + stability_score + length_score + paragraph_score\n"
            "score = score - contradiction_penalty - topic_shift_penalty\n"
            "score = max(0, min(score, 20))",
            language="python"
        )

        d = result["discursive_coherence_details"]

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{coherence_score}/20**")
        st.write(f"Niveau : **{coherence_label}**")

        st.write(f"Logique discursive : **{d['logic_score']}/5**")
        st.write(f"Stabilité thématique : **{d['stability_score']}/4**")
        st.write(f"Longueur utile : **{d['length_score']}/5**")
        st.write(f"Cohérence entre paragraphes : **{d['paragraph_score']}/4**")
        st.write(f"Pénalité de contradiction : **-{d['contradiction_penalty']}**")
        st.write(f"Pénalité de rupture thématique : **-{d['topic_shift_penalty']}**")

        if d["top_keywords"]:
            st.markdown("**Mots-clés dominants**")
            for word, count in d["top_keywords"]:
                st.write(f"- {word} ({count})")

        st.markdown("**Interprétation actuelle**")
        st.write(result["discursive_coherence_label"])

        st.markdown("**Lecture**")
        st.write(
            "🔴 Faible : texte peu structuré ou instable\n"
            "🟠 Limitée : cohérence fragile\n"
            "🟡 Correcte : structure compréhensible mais perfectible\n"
            "🟢 Solide : discours bien organisé\n"
            "🟢 Très forte : cohérence interne très robuste"
        )

        st.markdown("**Attention**")
        st.write(
            "Une forte cohérence discursive ne prouve pas qu’un texte est vrai. "
            "Un discours peut être très cohérent tout en restant faux, idéologique ou invérifiable."
        )

with sr2:
    st.subheader("Cohérence trompeuse")
    st.caption(
        "Cette jauge mesure si le texte paraît cohérent tout en restant fragile, orienté ou insuffisamment vérifiable."
    )
    
    value = result.get("deceptive_coherence", 0)
    label = result.get("deceptive_coherence_label", "—")
    
    if value < 0.25:
        color = "#ca8a04"
    elif value < 0.50:
        color = "#ca8a04"
    elif value < 0.75:
        color = "#f97316"
    else:
        color = "#dc2626"
    
    render_custom_gauge(value, color)
    
    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )
    
    st.caption("Cohérence apparente ⟵⟶ Cohérence trompeuse")
    
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Cohérence trompeuse")
    
        st.write(
            "Cette jauge détecte un phénomène particulier : un discours peut sembler cohérent, "
            "fluide et bien structuré, tout en étant fragile sur le fond, insuffisamment vérifié "
            "ou orienté."
        )
    
        st.markdown("**Principe**")
        st.write(
            "Elle compare la cohérence discursive (structure du texte) avec la solidité factuelle "
            "et l’équilibre cognitif. Plus la cohérence dépasse la vérifiabilité et le fondement, "
            "plus le risque de cohérence trompeuse augmente."
        )
    
        st.markdown("**Formule utilisée**")
        st.code(
            "deceptive_coherence = coherence_score - fact_score\n"
            "deceptive_coherence = max(0, deceptive_coherence)\n"
            "deceptive_coherence = min(deceptive_coherence / 20, 1.0)",
            language="python"
        )
    
        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
    
        st.markdown("**Interprétation actuelle**")
        st.write(label)
    
        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : cohérence alignée avec le fond\n"
            "🟡 Modérée : léger écart entre structure et fond\n"
            "🟠 Élevée : discours cohérent mais fragile\n"
            "🔴 Très élevée : forte illusion de solidité"
        )
    
        st.markdown("**Attention**")
        st.write(
            "Une cohérence trompeuse élevée ne signifie pas forcément manipulation. "
            "Elle indique qu’un discours peut être convaincant dans sa forme, "
            "tout en restant insuffisamment fondé dans son contenu."
        )

# -----------------------------
# Prémisses implicites
# -----------------------------
with sr3:
    st.markdown("### Prémisses implicites")
    st.caption("Idées présentées comme évidentes sans démonstration.")

    premise_value = result["premise_score"]

    if premise_value < 0.20:
        premise_label, premise_color = "Faible", "#ca8a04"
    elif premise_value < 0.40:
        premise_label, premise_color = "Modérée", "#f97316"
    elif premise_value < 0.70:
        premise_label, premise_color = "Élevée", "#ea580c"
    else:
        premise_label, premise_color = "Très élevée", "#dc2626"

    render_custom_gauge(premise_value, premise_color)

    st.markdown(
        f"<b style='color:{premise_color}'>{premise_label}</b> — {round(premise_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["premise_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        premise_markers = result.get("premise_markers", [])

        if not premise_markers:
            st.info("Aucune prémisse implicite saillante détectée.")
        else:
            for marker in premise_markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Prémisses implicites")

        st.write(
            "Cette jauge détecte les idées présentées comme évidentes, "
            "sans être explicitement démontrées dans le texte."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est analysé pour repérer les affirmations qui reposent sur des présupposés implicites : "
            "ce qui est tenu pour acquis sans justification."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = prémisses implicites détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        premise_markers = result.get("premise_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(premise_value * 100, 1)}%**")
        st.write(f"Niveau : **{premise_label}**")
        st.write(f"Marqueurs détectés : **{len(premise_markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["premise_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : peu de présupposés implicites\n"
            "🟡 Modérée : quelques évidences non démontrées\n"
            "🟠 Élevée : dépendance notable à des prémisses implicites\n"
            "🔴 Très élevée : raisonnement fortement fondé sur des évidences non explicitées"
        )

        st.markdown("**Attention**")
        st.write(
            "Une présence élevée de prémisses implicites ne signifie pas que le texte est faux. "
            "Elle indique que certaines bases du raisonnement ne sont pas explicitement justifiées."
        )

# -----------------------------
# Prémisses idéologiques implicites
# -----------------------------
with sr4:
    st.markdown("### Prémisses idéologiques")
    st.caption("Présupposés idéologiques présentés comme allant de soi.")

    ideological_value = result["ideological_premise_score"]

    if ideological_value < 0.20:
        ideological_label, ideological_color = "Faible", "#ca8a04"
    elif ideological_value < 0.40:
        ideological_label, ideological_color = "Modérée", "#f97316"
    elif ideological_value < 0.70:
        ideological_label, ideological_color = "Élevée", "#ea580c"
    else:
        ideological_label, ideological_color = "Très élevée", "#dc2626"

    render_custom_gauge(ideological_value, ideological_color)

    st.markdown(
        f"<b style='color:{ideological_color}'>{ideological_label}</b> — {round(ideological_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["ideological_premise_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("ideological_premise_markers", [])
        if not markers:
            st.info("Aucune prémisse idéologique saillante détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Prémisses idéologiques")

        st.write(
            "Cette jauge détecte les présupposés idéologiques présentés comme naturels, évidents ou allant de soi."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de prémisses idéologiques : "
            "idées de départ implicites, cadres politiques ou sociaux supposés vrais sans démonstration."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = prémisses idéologiques détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("ideological_premise_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(ideological_value * 100, 1)}%**")
        st.write(f"Niveau : **{ideological_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["ideological_premise_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : peu de présupposés idéologiques\n"
            "🟡 Modérée : quelques cadres idéologiques implicites\n"
            "🟠 Élevée : présupposés idéologiques notables\n"
            "🔴 Très élevée : raisonnement fortement fondé sur un cadre idéologique implicite"
        )

        st.markdown("**Attention**")
        st.write(
            "Une prémisse idéologique élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours repose sur un cadre d’évidence idéologique peu explicité."
        )

sr5, sr6, sr7, sr8 = st.columns(4)

# -----------------------------
# Surdétermination narrative
# -----------------------------
with sr5:
    st.markdown("### Surdétermination narrative")
    st.caption("Réduction du réel à un récit unique supposé tout expliquer.")

    value = result["narrative_overdetermination_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["narrative_overdetermination_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("narrative_overdetermination_markers", [])
        if not markers:
            st.info("Aucune surdétermination narrative notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Surdétermination narrative")

        st.write(
            "Cette jauge détecte les situations où le texte réduit la complexité du réel "
            "à un récit unique censé tout expliquer."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de surdétermination narrative : "
            "explication unique, cause globale, ou récit totalisant qui absorbe toutes les interprétations."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de récit totalisant détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("narrative_overdetermination_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["narrative_overdetermination_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : pluralité d’explications\n"
            "🟡 Modérée : tendance à simplifier le récit\n"
            "🟠 Élevée : récit dominant structurant\n"
            "🔴 Très élevée : récit unique totalisant"
        )

        st.markdown("**Attention**")
        st.write(
            "Une surdétermination narrative élevée ne signifie pas que l’explication est fausse. "
            "Elle indique que le discours tend à réduire la complexité du réel à une seule grille de lecture."
        )

# -----------------------------
#  Simplification stratégique
# -----------------------------
with sr6:
    st.markdown("### Simplification stratégique")
    st.caption("Réduction d’une réalité complexe à une cause unique ou simple.")

    value = result["strategic_simplification_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["strategic_simplification_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("strategic_simplification_markers", [])
        if not markers:
            st.info("Aucune simplification stratégique notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Simplification stratégique")

        st.write(
            "Cette jauge détecte les discours qui réduisent une réalité complexe "
            "à une cause unique, simple ou trop directement désignée."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de simplification stratégique : "
            "cause unique, explication trop directe, ou réduction d’un problème complexe "
            "à un responsable ou mécanisme simple."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de simplification stratégique détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("strategic_simplification_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["strategic_simplification_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : complexité relativement préservée\n"
            "🟡 Modérée : simplification ponctuelle\n"
            "🟠 Élevée : réduction forte d’un phénomène complexe\n"
            "🔴 Très élevée : explication unique dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une simplification stratégique élevée ne signifie pas que l’idée est fausse. "
            "Elle indique que le discours réduit fortement la complexité du réel."
        )

# -----------------------------
#  Frame shift
# -----------------------------
with sr7:
    st.markdown("### Frame shift")
    st.caption("Déplacement du cadre du débat pour orienter l’interprétation.")

    value = result["frame_shift_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["frame_shift_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("frame_shift_markers", [])
        if not markers:
            st.info("Aucun déplacement de cadre notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Frame shift")

        st.write(
            "Cette jauge détecte les déplacements du cadre du débat : "
            "le discours change implicitement les règles d’interprétation "
            "pour orienter la compréhension du lecteur."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est analysé pour repérer les glissements de cadre : "
            "changement de définition, déplacement du problème, "
            "ou reformulation orientée du sujet initial."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = déplacements de cadre détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("frame_shift_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["frame_shift_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : cadre stable\n"
            "🟡 Modérée : légers déplacements\n"
            "🟠 Élevée : recadrage notable du débat\n"
            "🔴 Très élevée : changement de cadre dominant"
        )

        st.markdown("**Attention**")
        st.write(
            "Un frame shift élevé ne signifie pas que le discours est faux. "
            "Il indique que le cadre d’interprétation est modifié pour orienter la lecture."
        )

st.divider()
    
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# =============================
# 🧭 4. ORIENTATION IDÉOLOGIQUE
# =============================
st.subheader("🧭 Orientation idéologique")
st.caption("Détection des structures narratives orientées ou propagandistes.")

oi1, oi2, oi3, oi4 = st.columns(4)

with oi1:
    
    st.subheader("Jauge propagandiste")
    st.caption(
            "Cette jauge estime si le texte dépasse le simple discours orienté "
            "pour entrer dans une structure plus fortement propagandiste."
    )
    
    closure_for_discourse = (
        (result["D"] * (1 + len(result["red_flags"]) / 5)) / (result["G"] + result["N"])
        if (result["G"] + result["N"]) > 0 else 10
    )
    
    propaganda_value = compute_propaganda_gauge(
        lie_gauge=gauge_value,
        rhetorical_pressure=result.get("rhetorical_pressure", 0),
        closure=closure_for_discourse,
    
        false_consensus=result.get("false_consensus_score", 0),
        moral_polarization=result.get("moral_polarization_score", 0),
        binary_opposition=result.get("binary_opposition_score", 0),
        victimization=result.get("victimization_score", 0),
        semantic_shift=result.get("semantic_shift_score", 0),
        false_dilemma=result.get("false_dilemma_score", 0),
    
        saturation_rhetorique=result.get("rhetorical_scores", {}).get("saturation_rhetorique", 0),
        soupcon_systemique=result.get("rhetorical_scores", {}).get("soupcon_systemique", 0),
        attaque=result.get("rhetorical_scores", {}).get("attaque", 0),
        amplification=result.get("rhetorical_scores", {}).get("amplification", 0),

        colere=result.get("emotional_registers", {}).get("colere", 0),
        peur=result.get("emotional_registers", {}).get("peur", 0),

        reported_speech=max(
            result.get("reported_speech_score", 0),
            result.get("reported_speech_ratio", 0),
            result.get("reported_speech", 0),
            result.get("reported_speech_gauge", 0),
        ),
    )

    propaganda_label, propaganda_color, propaganda_text = interpret_propaganda_gauge(
        propaganda_value
    )

    render_custom_gauge(
        propaganda_value,
        propaganda_color
    )

    st.markdown(
        f"<b style='color:{propaganda_color}'>{propaganda_label}</b> — {round(propaganda_value*100, 1)}%",
        unsafe_allow_html=True
    )
    if propaganda_value < 0.20:
        propaganda_interpretation = "Le texte ne présente pas de structure propagandiste marquée."
    elif propaganda_value < 0.40:
        propaganda_interpretation = "Le texte présente quelques mécanismes de cadrage idéologique."
    elif propaganda_value < 0.70:
        propaganda_interpretation = "Le discours combine plusieurs structures typiques des récits propagandistes."
    else:
        propaganda_interpretation = "Le discours semble fortement structuré par des mécanismes propagandistes."
    
    st.caption(propaganda_interpretation)
    
    st.caption("Discours peu orienté ⟵⟶ Structure propagandiste")
    st.caption(propaganda_text)
    
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Jauge propagandiste")
    
        st.write(
            "Cette jauge combine la tension cognitive, la pression rhétorique, "
            "les motifs idéologiques détectés et le degré de fermeture cognitive. "
            "Elle aide à estimer si le texte relève d’un simple discours orienté "
            "ou d’une structure plus franchement propagandiste. "

        )
    
        st.markdown("**Principe**")
        st.write(
            "Elle combine la tension stratégique, la pression rhétorique, "
            "la fermeture cognitive, les motifs idéologiques classiques, "
            "ainsi que les nouveaux signaux rhétoriques et émotionnels : "
            "saturation, soupçon systémique, attaque, amplification, colère et peur."
        )
    
        st.markdown("**Formule utilisée**")
        st.code(
            "propaganda_value = compute_propaganda_gauge(\n"
            "    lie_gauge=gauge_value,\n"
            "    rhetorical_pressure=rp,\n"
            "    closure=closure_for_discourse,\n"
            "    ideological_core=(false_consensus + moral_polarization + binary_opposition + victimization + semantic_shift + false_dilemma) / 6,\n"
            "    rhetorical_core=(saturation×0.30 + soupcon×0.25 + attaque×0.20 + amplification×0.15 + colere×0.07 + peur×0.03)\n"
            ")",
            language="python"
        )
            
        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(propaganda_value * 100, 1)}%**")
        st.write(f"Niveau : **{propaganda_label}**")
    
        st.write(f"Tension stratégique : **{round(gauge_value * 100, 1)}%**")
        st.write(f"Pression rhétorique : **{round(rp * 100, 1)}%**")
        st.write(f"Motifs idéologiques : **{result['political_pattern_score']}**")
        st.write(f"Fermeture cognitive : **{round(closure_for_discourse, 2)}**")

        rhetorical_scores = result.get("rhetorical_scores", {})
        emotional_registers = result.get("emotional_registers", {})
        
        st.write(f"Saturation rhétorique : **{round(rhetorical_scores.get('saturation_rhetorique', 0) * 100, 1)}%**")
        st.write(f"Soupçon systémique : **{round(rhetorical_scores.get('soupcon_systemique', 0) * 100, 1)}%**")
        st.write(f"Attaque : **{round(rhetorical_scores.get('attaque', 0) * 100, 1)}%**")
        st.write(f"Amplification : **{round(rhetorical_scores.get('amplification', 0) * 100, 1)}%**")
        st.write(f"Colère : **{round(emotional_registers.get('colere', 0) * 100, 1)}%**")
        st.write(f"Peur : **{round(emotional_registers.get('peur', 0) * 100, 1)}%**")
    
        st.markdown("**Interprétation actuelle**")
        st.write(propaganda_text)
    
        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours peu orienté\n"
            "🟡 Modérée : orientation discursive présente\n"
            "🟠 Élevée : structure fortement orientée\n"
            "🔴 Très élevée : structure propagandiste probable"
        )
        discursive_profile = interpret_discursive_profile(
            lie_gauge=gauge_value,
            rhetorical_pressure=rp,
            propaganda_gauge=propaganda_value,
            premise_score=result["premise_score"],
            logic_confusion_score=result["logic_confusion_score"],
            scientific_simulation_score=result["scientific_simulation_score"],
            discursive_coherence_score=result["discursive_coherence_score"],
        )
    
        st.subheader("Profil discursif global")
        st.write(discursive_profile)
    
        st.markdown("**Attention**")
        st.write(
            "Une jauge propagandiste élevée ne prouve pas une intention de propagande. "
            "Elle indique une convergence de signaux : pression, orientation, fermeture cognitive "
            "et motifs idéologiques."
        )
# -----------------------------
#  Propagande narrative
# -----------------------------
with oi2:
    st.markdown("### Narration propagandiste")
    st.caption("Urgence, ennemi abstrait, certitude et charge émotionnelle.")

    propaganda_value = result["propaganda_score"]

    if propaganda_value < 0.20:
        propaganda_label, propaganda_color = "Faible", "#ca8a04"
    elif propaganda_value < 0.40:
        propaganda_label, propaganda_color = "Modérée", "#f97316"
    elif propaganda_value < 0.70:
        propaganda_label, propaganda_color = "Élevée", "#ea580c"
    else:
        propaganda_label, propaganda_color = "Très élevée", "#dc2626"

    render_custom_gauge(propaganda_value, propaganda_color)

    st.markdown(
        f"<b style='color:{propaganda_color}'>{propaganda_label}</b> — {round(propaganda_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["propaganda_interpretation"])

    # 🔎 Marqueurs
    with st.expander("🔎 Voir les marqueurs", expanded=False):
        enemy_terms = result.get("propaganda_enemy_terms", [])
        urgency_terms = result.get("propaganda_urgency_terms", [])
        certainty_terms = result.get("propaganda_certainty_terms", [])
        emotional_terms = result.get("propaganda_emotional_terms", [])

        if not any([enemy_terms, urgency_terms, certainty_terms, emotional_terms]):
            st.info("Aucun marqueur narratif saillant détecté.")
        else:
            if enemy_terms:
                st.markdown("**Ennemi / bloc adverse**")
                for term in enemy_terms:
                    st.error(term)

            if urgency_terms:
                st.markdown("**Urgence / menace**")
                for term in urgency_terms:
                    st.warning(term)

            if certainty_terms:
                st.markdown("**Certitude absolue**")
                for term in certainty_terms:
                    st.warning(term)

            if emotional_terms:
                st.markdown("**Charge émotionnelle**")
                for term in emotional_terms:
                    st.error(term)

    # ℹ️ Popover explicatif
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Narration propagandiste")

        st.write(
            "Cette jauge détecte une structure narrative orientée, typique des discours cherchant à mobiliser, "
            "convaincre ou polariser."
        )

        st.markdown("**Principe**")
        st.write(
            "Elle combine les anciens marqueurs narratifs — ennemi, urgence, certitude et émotion — "
            "avec les nouveaux signaux rhétoriques : saturation, soupçon systémique, attaque, "
            "amplification, colère et peur."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "score = ancien_score_narratif × 0.35\n"
            "+ saturation_rhetorique × 0.15\n"
            "+ soupcon_systemique × 0.15\n"
            "+ attaque × 0.10\n"
            "+ amplification × 0.10\n"
            "+ colere × 0.10\n"
            "+ peur × 0.05\n"
            "score = min(score, 1.0)",
            language="python"
        )

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(propaganda_value * 100, 1)}%**")
        st.write(f"Niveau : **{propaganda_label}**")

        st.write(f"Ennemi : **{len(result.get('propaganda_enemy_terms', []))}**")
        st.write(f"Urgence : **{len(result.get('propaganda_urgency_terms', []))}**")
        st.write(f"Certitude : **{len(result.get('propaganda_certainty_terms', []))}**")
        st.write(f"Émotion : **{len(result.get('propaganda_emotional_terms', []))}**")
        rhetorical_scores = result.get("rhetorical_scores", {})
        emotional_registers = result.get("emotional_registers", {})
        
        st.write(f"Saturation rhétorique : **{round(rhetorical_scores.get('saturation_rhetorique', 0) * 100, 1)}%**")
        st.write(f"Soupçon systémique : **{round(rhetorical_scores.get('soupcon_systemique', 0) * 100, 1)}%**")
        st.write(f"Attaque : **{round(rhetorical_scores.get('attaque', 0) * 100, 1)}%**")
        st.write(f"Amplification : **{round(rhetorical_scores.get('amplification', 0) * 100, 1)}%**")
        st.write(f"Colère : **{round(emotional_registers.get('colere', 0) * 100, 1)}%**")
        st.write(f"Peur : **{round(emotional_registers.get('peur', 0) * 100, 1)}%**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["propaganda_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours peu narratif ou neutre\n"
            "🟡 Modérée : présence de cadrage narratif\n"
            "🟠 Élevée : narration orientée\n"
            "🔴 Très élevée : structure fortement propagandiste"
        )

        st.markdown("**Attention**")
        st.write(
            "Une narration propagandiste élevée ne signifie pas que le texte est faux. "
            "Elle indique une construction discursive orientée visant à influencer la perception."
        )
# -----------------------------
#  Ennemi abstrait
# -----------------------------
with oi3:
    st.markdown("### Polarisation / Ennemi abstrait")
    st.caption("Construction d’un adversaire flou ou globalisant.")

    abstract_enemy_value = result["abstract_enemy_score"]

    if abstract_enemy_value < 0.20:
        abstract_enemy_label, abstract_enemy_color = "Faible", "#ca8a04"
    elif abstract_enemy_value < 0.40:
        abstract_enemy_label, abstract_enemy_color = "Modérée", "#f97316"
    elif abstract_enemy_value < 0.70:
        abstract_enemy_label, abstract_enemy_color = "Élevée", "#ea580c"
    else:
        abstract_enemy_label, abstract_enemy_color = "Très élevée", "#dc2626"

    render_custom_gauge(abstract_enemy_value, abstract_enemy_color)

    st.markdown(
        f"<b style='color:{abstract_enemy_color}'>{abstract_enemy_label}</b> — {round(abstract_enemy_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["abstract_enemy_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("abstract_enemy_markers", [])
        if not markers:
            st.info("Aucun ennemi abstrait notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Ennemi abstrait")

        st.write(
            "Cette jauge détecte la construction d’un adversaire vague, global ou mal défini. "
            "Elle repère les formulations qui désignent un bloc hostile sans toujours préciser les acteurs, les faits ou les responsabilités."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à une liste de marqueurs d’ennemi abstrait. "
            "Chaque marqueur détecté augmente le score."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs d’ennemi abstrait détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("abstract_enemy_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(abstract_enemy_value * 100, 1)}%**")
        st.write(f"Niveau : **{abstract_enemy_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["abstract_enemy_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : adversaire peu ou pas construit\n"
            "🟡 Modérée : désignation adverse présente mais limitée\n"
            "🟠 Élevée : adversaire flou ou globalisant notable\n"
            "🔴 Très élevée : forte construction d’un bloc ennemi"
        )

        st.markdown("**Attention**")
        st.write(
            "Un score élevé ne signifie pas que le texte est faux. "
            "Il indique que le discours tend à construire un adversaire global, abstrait ou peu spécifié."
        )

# -----------------------------
# Dissonance interne
# -----------------------------
with oi4:
    st.markdown("### Dissonance interne")
    st.caption("Contradictions ou incompatibilités au sein du même discours.")

    value = result["internal_dissonance_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["internal_dissonance_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("internal_dissonance_markers", [])
        if not markers:
            st.info("Aucune dissonance interne notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Dissonance interne")

        st.write(
            "Cette jauge détecte les contradictions, tensions ou incompatibilités internes "
            "présentes dans un même discours."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est analysé pour repérer les marqueurs de contradiction : "
            "affirmations incompatibles, revirements, oppositions internes ou incohérences entre passages."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "contradictions = contradictions fortes détectées\n"
            "tensions = tensions internes faibles détectées\n"
            "score = min(len(contradictions)*0.28 + len(tensions)*0.12, 1.0)",
            language="python"
        )

        markers = result.get("internal_dissonance_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
        st.caption("Les tensions faibles pèsent moins que les contradictions formelles.")

        st.markdown("**Interprétation actuelle**")
        st.write(result["internal_dissonance_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours globalement cohérent\n"
            "🟡 Modérée : quelques tensions internes\n"
            "🟠 Élevée : contradictions notables\n"
            "🔴 Très élevée : incohérence interne dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une dissonance interne élevée ne signifie pas que tout le texte est faux. "
            "Elle indique que certaines parties du discours semblent entrer en tension ou se contredire."
        )
oi5, oi6, oi7, oi8 = st.columns(4)
# -----------------------------
# Polarisation morale
# -----------------------------
with oi5:
    st.markdown("### Polarisation morale")
    st.caption("Découpage moral du réel en camps du bien et du mal.")

    value = result["moral_polarization_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["moral_polarization_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("moral_polarization_markers", [])
        if not markers:
            st.info("Aucune polarisation morale notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Polarisation morale")

        st.write(
            "Cette jauge détecte les discours qui découpent le réel en camps moraux opposés : "
            "les bons contre les mauvais, les justes contre les coupables."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de polarisation morale : "
            "oppositions morales fortes, disqualification éthique de l’adversaire, "
            "ou séparation du monde en camps irréconciliables."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de polarisation morale détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("moral_polarization_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["moral_polarization_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours peu polarisant\n"
            "🟡 Modérée : quelques oppositions morales\n"
            "🟠 Élevée : polarisation morale notable\n"
            "🔴 Très élevée : découpage moral dominant du réel"
        )

        st.markdown("**Attention**")
        st.write(
            "Une polarisation morale élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours organise fortement le réel en camps moraux opposés."
        )
# =============================
# Faux consensus renforcé
# =============================
with oi6:
    st.markdown("### Faux consensus renforcé")
    st.caption("Simulation d’un accord collectif présenté comme preuve.")

    value = result["false_consensus_strong_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["false_consensus_strong_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("false_consensus_strong_markers", [])
        if not markers:
            st.info("Aucun faux consensus renforcé notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Faux consensus renforcé")

        st.write(
            "Cette jauge détecte les formulations qui présentent un accord collectif "
            "comme une preuve en soi."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de consensus renforcé : "
            "accord général supposé, évidence collective, majorité invoquée comme argument."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de faux consensus renforcé détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("false_consensus_strong_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["false_consensus_strong_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : pas de consensus utilisé comme preuve\n"
            "🟡 Modérée : accord collectif suggéré\n"
            "🟠 Élevée : consensus présenté comme appui argumentatif\n"
            "🔴 Très élevée : consensus collectif utilisé comme preuve centrale"
        )

        st.markdown("**Attention**")
        st.write(
            "Un faux consensus renforcé élevé ne signifie pas que l’idée est fausse. "
            "Il indique que le texte transforme un accord supposé en preuve argumentative."
        )

# =============================
# Argument de nature
# =============================
with oi7:
    st.markdown("### Argument de nature")
    st.caption("Le caractère naturel est utilisé comme argument de vérité ou de valeur.")

    value = result["argument_from_nature_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["argument_from_nature_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("argument_from_nature_markers", [])
        if not markers:
            st.info("Aucun argument de nature notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Argument de nature")

        st.write(
            "Cette jauge détecte les raisonnements qui utilisent le caractère "
            "« naturel » comme argument de vérité, de légitimité ou de valeur."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs d’argument de nature : "
            "référence à ce qui est « naturel » pour justifier une position, "
            "sans démonstration supplémentaire."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = arguments de nature détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("argument_from_nature_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["argument_from_nature_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : peu ou pas d’argument de nature\n"
            "🟡 Modérée : recours ponctuel au naturel\n"
            "🟠 Élevée : justification notable par le naturel\n"
            "🔴 Très élevée : le naturel est utilisé comme preuve centrale"
        )

        st.markdown("**Attention**")
        st.write(
            "Un argument de nature élevé ne signifie pas que le texte est faux. "
            "Il indique que le discours utilise le « naturel » comme fondement argumentatif."
        )
# -----------------------------
#  Opposition binaire
# -----------------------------
with oi8:
    st.markdown("### Opposition binaire")
    st.caption("Découpage du discours en camps antagonistes.")

    binary_value = result["binary_opposition_score"]

    if binary_value < 0.15:
        binary_label, binary_color = "Faible", "#ca8a04"
    elif binary_value < 0.35:
        binary_label, binary_color = "Modérée", "#f97316"
    elif binary_value < 0.60:
        binary_label, binary_color = "Élevée", "#ea580c"
    else:
        binary_label, binary_color = "Très élevée", "#dc2626"

    render_custom_gauge(binary_value, binary_color)

    st.markdown(
        f"<b style='color:{binary_color}'>{binary_label}</b> — {round(binary_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["binary_opposition_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("binary_opposition_markers", [])
        if not markers:
            st.info("Aucune opposition binaire notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Opposition binaire")

        st.write(
            "Cette jauge détecte les discours qui divisent le réel en deux camps opposés : "
            "nous contre eux, vérité contre mensonge, bien contre mal."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs d’opposition binaire : "
            "formulations antagonistes, camps irréconciliables, ou découpage simplifié du débat."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs d’opposition binaire détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("binary_opposition_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(binary_value * 100, 1)}%**")
        st.write(f"Niveau : **{binary_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["binary_opposition_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : peu d’opposition en camps\n"
            "🟡 Modérée : antagonisme ponctuel\n"
            "🟠 Élevée : opposition binaire notable\n"
            "🔴 Très élevée : découpage dominant en camps antagonistes"
        )

        st.markdown("**Attention**")
        st.write(
            "Une opposition binaire élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours réduit le réel à des camps opposés, "
            "ce qui peut renforcer la polarisation et la clôture cognitive."
        )
st.divider()
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# =============================
# ⚖️ 5. ANALYSE LOGIQUE
# =============================
st.subheader("⚖️ Analyse logique")
st.caption("Identification des erreurs de raisonnement et des structures logiques.")

al1, al2, al3, al4 = st.columns(4)

# -----------------------------
#  Confusion logique
# -----------------------------
with al1:
    st.markdown("### Confusion logique")
    st.caption("Causalité abusive, extrapolation, prédiction absolue.")

    logic_value = result["logic_confusion_score"]

    if logic_value < 0.20:
        logic_label, logic_color = "Faible", "#ca8a04"
    elif logic_value < 0.40:
        logic_label, logic_color = "Modérée", "#f97316"
    elif logic_value < 0.70:
        logic_label, logic_color = "Élevée", "#ea580c"
    else:
        logic_label, logic_color = "Très élevée", "#dc2626"

    render_custom_gauge(logic_value, logic_color)

    st.markdown(
        f"<b style='color:{logic_color}'>{logic_label}</b> — {round(logic_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["logic_confusion_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("logic_confusion_markers", [])
        if not markers:
            st.info("Aucune confusion logique saillante détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Confusion logique")

        st.write(
            "Cette jauge détecte les passages où le raisonnement paraît glisser : "
            "causalité trop rapide, extrapolation excessive, prédiction présentée comme certaine "
            "ou lien logique insuffisamment démontré."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à une liste de marqueurs de confusion logique. "
            "Chaque marqueur détecté augmente le score."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de confusion logique détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("logic_confusion_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(logic_value * 100, 1)}%**")
        st.write(f"Niveau : **{logic_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["logic_confusion_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : raisonnement peu confus\n"
            "🟡 Modérée : quelques glissements logiques\n"
            "🟠 Élevée : confusion logique notable\n"
            "🔴 Très élevée : raisonnement fortement instable ou abusif"
        )

        st.markdown("**Attention**")
        st.write(
            "Une confusion logique élevée ne signifie pas automatiquement que le texte est faux. "
            "Elle indique que certains liens de cause, de conséquence ou de projection méritent d’être vérifiés."
        )
# -----------------------------
#  Fausse causalité
# -----------------------------
with al2:
    st.markdown("### Fausse causalité")
    st.caption("Liens causaux affirmés plus vite qu'ils ne sont démontrés.")

    causal_value = result["causal_overreach_score"]

    if causal_value < 0.20:
        causal_label, causal_color = "Faible", "#ca8a04"
    elif causal_value < 0.40:
        causal_label, causal_color = "Modérée", "#f97316"
    elif causal_value < 0.70:
        causal_label, causal_color = "Élevée", "#ea580c"
    else:
        causal_label, causal_color = "Très élevée", "#dc2626"

    render_custom_gauge(causal_value, causal_color)

    st.markdown(
        f"<b style='color:{causal_color}'>{causal_label}</b> — {round(causal_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["causal_overreach_interpretation"])

    # 🔎 Marqueurs
    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("causal_overreach_markers", [])
        if not markers:
            st.info("Aucun marqueur de causalité abusive détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    # ℹ️ Explication
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Fausse causalité")

        st.write(
            "Cette jauge détecte les situations où un lien de cause à effet est affirmé trop rapidement, "
            "sans preuve suffisante ou sans démonstration rigoureuse."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de causalité abusive : liens implicites, "
            "enchaînements rapides, corrélations présentées comme des causes."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de causalité détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("causal_overreach_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(causal_value * 100, 1)}%**")
        st.write(f"Niveau : **{causal_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["causal_overreach_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : causalité prudente ou absente\n"
            "🟡 Modérée : quelques raccourcis causaux\n"
            "🟠 Élevée : causalité affirmée sans preuve solide\n"
            "🔴 Très élevée : enchaînements causaux abusifs"
        )

        st.markdown("**Attention**")
        st.write(
            "Une fausse causalité élevée ne signifie pas que le texte est entièrement faux. "
            "Elle indique que certains liens de cause à effet doivent être vérifiés ou approfondis."
        )
# -----------------------------
#  Faux dilemme
# -----------------------------
with al3:
    st.markdown("### Faux dilemme")
    st.caption("Réduction artificielle du réel à deux options.")

    value = result["false_dilemma_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["false_dilemma_interpretation"])

    # 🔎 Marqueurs
    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("false_dilemma_markers", [])
        if not markers:
            st.info("Aucun faux dilemme notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    # ℹ️ Explication
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Faux dilemme")
    
        st.write(
            "Cette jauge détecte les situations où un problème complexe est réduit "
            "à deux choix exclusifs, souvent opposés, alors que d’autres options existent."
        )
    
        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de dichotomisation, mais le score est réduit "
            "lorsque le texte contient aussi des marqueurs d’ouverture, de nuance ou de pluralité."
        )
    
        st.markdown("**Formule utilisée**")
        st.code(
            "raw_score = len(markers) × 0.25\n"
            "nuance_reduction = min(len(marqueurs_de_nuance) × 0.07, 0.35)\n"
            "score = max(0.0, raw_score - nuance_reduction)",
            language="python"
        )
    
        markers = result.get("false_dilemma_markers", [])
    
        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
        st.write(f"Marqueurs de nuance : **{result.get('false_dilemma_nuance_count', 0)}**")
    
        st.markdown("**Interprétation actuelle**")
        st.write(result["false_dilemma_interpretation"])
    
        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : alternatives ouvertes\n"
            "🟡 Modérée : simplification partielle\n"
            "🟠 Élevée : opposition binaire dominante\n"
            "🔴 Très élevée : réduction forte du réel à deux choix"
        )
    
        st.markdown("**Attention**")
        st.write(
            "Un faux dilemme élevé ne signifie pas que le texte est faux. "
            "Il indique une simplification excessive qui peut masquer d’autres possibilités."
        )
# -----------------------------
#  Confusion descriptif / normatif
# -----------------------------
with al4:
    st.markdown("### Confusion descriptif / normatif")
    st.caption("Glissement d’une description vers une injonction sans justification suffisante.")

    value = result["descriptive_normative_confusion_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["descriptive_normative_confusion_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("descriptive_normative_confusion_markers", [])
        if not markers:
            st.info("Aucune confusion descriptif / normatif notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Confusion descriptif / normatif")

        st.write(
            "Cette jauge détecte les situations où un fait ou une description "
            "est transformé en jugement, norme ou injonction sans justification."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de glissement normatif : "
            "passage du descriptif (« ce qui est ») au normatif (« ce qui doit être ») "
            "sans étape argumentative explicite."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "raw_score = len(markers) × 0.30\n"
            "nuance_reduction = min(len(marqueurs_de_nuance) × 0.06, 0.35)\n"
            "score = max(0.0, raw_score - nuance_reduction)",
            language="python"
        )

        markers = result.get("descriptive_normative_confusion_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
        st.write(
            f"Marqueurs de nuance : **{result.get('descriptive_normative_confusion_nuance_count', 0)}**"
        )

        st.markdown("**Interprétation actuelle**")
        st.write(result["descriptive_normative_confusion_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : distinction claire entre faits et jugements\n"
            "🟡 Modérée : glissements ponctuels\n"
            "🟠 Élevée : confusion notable entre description et norme\n"
            "🔴 Très élevée : injonctions déguisées en faits"
        )

        st.markdown("**Attention**")
        st.write(
            "Une confusion descriptif / normatif élevée ne signifie pas que le texte est faux. "
            "Elle indique que des jugements ou normes sont présentés comme des faits."
        )

al5, al6, al7, al8, = st.columns(4)
# -----------------------------
#  Pétition de principe
# -----------------------------
with al5:
    st.markdown("### Pétition de principe")
    st.caption("Conclusion répétée comme si elle constituait une preuve.")

    value = result["petition_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["petition_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("petition_markers", [])
        if not markers:
            st.info("Aucune pétition de principe notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Pétition de principe")

        st.write(
            "Cette jauge détecte les raisonnements circulaires : "
            "la conclusion est répétée ou présupposée comme si elle constituait une preuve."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est analysé pour repérer les formulations où une idée est tenue pour vraie "
            "parce qu’elle est répétée, posée comme évidente ou utilisée comme sa propre justification."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de pétition de principe détectés\n"
            "score = min(len(markers) * coefficient, 1.0)",
            language="python"
        )

        markers = result.get("petition_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["petition_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : peu de circularité argumentative\n"
            "🟡 Modérée : circularité légère ou évidence présupposée\n"
            "🟠 Élevée : conclusion souvent posée comme preuve\n"
            "🔴 Très élevée : raisonnement fortement circulaire"
        )

        st.markdown("**Attention**")
        st.write(
            "Une pétition de principe élevée ne signifie pas que la conclusion est fausse. "
            "Elle indique que le texte tend à présupposer ou répéter sa conclusion au lieu de la démontrer."
        )
# -----------------------------
# Cherry Picking
# -----------------------------
with al6:
    st.markdown("### Cherry Picking")
    st.caption(
        "Sélection biaisée d’exemples, de cas ou de preuves allant dans un seul sens."
    )

    value = result.get("cherry_picking_score", 0.0)

    markers = result.get("cherry_picking_markers", [])
    omissions = result.get("cherry_picking_omission_markers", [])
    structural = result.get("cherry_picking_structural_markers", [])

    # Sécurité : impossible d'avoir 100 % sans preuve
    if not markers and not omissions and not structural:
        value = 0.0

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["cherry_picking_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):

        if not markers and not omissions and not structural:
            st.info("Aucune sélection biaisée notable détectée.")

        else:

            if markers:
                st.markdown("**Exemples isolés / preuves uniques**")
                for marker in markers:
                    st.warning(marker)

            if omissions:
                st.markdown("**Indices d’omission stratégique**")
                for marker in omissions:
                    st.error(marker)

            if structural:
                st.markdown("**Structures exemple → conclusion**")
                for marker in structural:
                    st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):

        st.markdown("### Cherry Picking")

        st.write(
            "Cette jauge détecte les situations où le texte sélectionne certains exemples, "
            "cas ou preuves allant dans un seul sens, tout en laissant de côté les éléments contraires."
        )

        st.markdown("**Principe**")

        st.write(
            "Le texte est comparé à deux familles de signaux : "
            "les exemples isolés ou preuves uniques, "
            "et les indices d’omission stratégique."
        )

        st.markdown("**Formule utilisée**")

        st.code(
            "markers = exemples isolés détectés\n"
            "omissions = indices d’omission stratégique\n"
            "structural = structures exemple → conclusion\n"
            "score = min((len(markers)*0.25 + "
            "len(omissions)*0.35 + "
            "len(structural)*0.35), 1.0)",
            language="python"
        )

        st.markdown("**Valeur actuelle**")

        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")

        st.write(
            f"Exemples / preuves uniques : **{len(markers)}**"
        )

        st.write(
            f"Omissions stratégiques : **{len(omissions)}**"
        )

        st.write(
            f"Structures détectées : **{len(structural)}**"
        )

        st.markdown("**Interprétation actuelle**")

        st.write(
            result["cherry_picking_interpretation"]
        )

        st.markdown("**Lecture**")

        st.write(
            "🟢 Faible : sélection peu biaisée\n"
            "🟡 Modérée : quelques exemples orientés\n"
            "🟠 Élevée : sélection fortement unilatérale\n"
            "🔴 Très élevée : omission ou sélection stratégique probable"
        )

        st.markdown("**Attention**")

        st.write(
            "Un score élevé ne signifie pas que les exemples cités sont faux. "
            "Il indique que le texte peut choisir certains éléments favorables "
            "en négligeant d’autres données nécessaires à l’équilibre de l’analyse."
        )
# -----------------------------
#  Sophismes syllogistiques détectés
# -----------------------------
with al7:
    st.markdown("### Sophismes syllogistiques détectés")
    st.caption("Failles formelles ou conclusions invalides dans les raisonnements syllogistiques.")

    value = min(result["fallacy_signal"] / 2, 1.0)

    if result["fallacy_signal"] == 0:
        label, color = "Aucun signal", "#ca8a04"
    elif result["fallacy_signal"] == 1:
        label, color = "Signal faible", "#f97316"
    elif result["fallacy_signal"] <= 3:
        label, color = "Signal modéré", "#ea580c"
    else:
        label, color = "Signal fort", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{result['fallacy_label']}</b> — {result['fallacy_signal']} repéré(s)",
        unsafe_allow_html=True
    )

    st.caption("Terme moyen absent, forme invalide ou conclusion trop forte.")

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Sophismes détectés")

        st.write(
            "Cette jauge repère les failles formelles dans les raisonnements de type syllogistique : "
            "enchaînements invalides, terme moyen absent ou conclusion plus forte que les prémisses."
        )

        st.markdown("**Principe**")
        st.write(
            "Elle s’appuie sur l’analyse logique des prémisses et des conclusions détectées dans le texte. "
            "Contrairement aux jauges rhétoriques, elle ne cherche pas des mots chargés, mais une faiblesse de structure argumentative."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "fallacy_signal = nombre de sophismes syllogistiques détectés\n"
            "value = min(fallacy_signal / 2, 1.0)",
            language="python"
        )

        st.markdown("**Valeur actuelle**")
        st.write(f"Signal : **{result['fallacy_signal']} repéré(s)**")
        st.write(f"Niveau : **{result['fallacy_label']}**")
        st.write(f"Score jauge : **{round(value * 100, 1)}%**")

        st.markdown("**Lecture**")
        st.write(
            "🟢 Aucun signal : aucune faille formelle repérée\n"
            "🟡 Signal faible : fragilité logique ponctuelle\n"
            "🟠 Signal modéré : plusieurs failles ou conclusion fragile\n"
            "🔴 Signal fort : structure argumentative fortement invalide"
        )

        st.markdown("**Attention**")
        st.write(
            "L’absence de sophisme détecté ne signifie pas que le texte est vrai. "
            "Elle signifie seulement qu’aucune faille syllogistique formelle n’a été repérée."
        )

al9, al10, al11, al12 = st.columns(4)
# -----------------------------
#  Syllogismes / Enthymèmes détectés
# -----------------------------
with al8:
    st.markdown("### Syllogismes / Enthymèmes détectés")
    st.caption("Raisonnements incomplets ou implicites repérés dans le texte.")

    value = min(result["enthymeme_signal"] / 4, 1.0)

    if result["enthymeme_signal"] == 0:
        label, color = "Aucun signal", "#16a34a"
    elif result["enthymeme_signal"] == 1:
        label, color = "Signal faible", "#ca8a04"
    elif result["enthymeme_signal"] <= 3:
        label, color = "Signal modéré", "#f97316"
    else:
        label, color = "Signal fort", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{result['enthymeme_label']}</b> — {result['enthymeme_signal']} repéré(s)",
        unsafe_allow_html=True
    )

    st.caption("Conclusion présente, prémisse partiellement implicite.")

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Enthymèmes détectés")

        st.write(
            "Cette jauge repère les raisonnements incomplets : une conclusion est présente, "
            "mais une partie de la démonstration reste implicite."
        )

        st.markdown("**Principe**")
        st.write(
            "Elle cherche les cas où le texte suggère une conclusion sans expliciter toutes les prémisses nécessaires."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "enthymeme_signal = nombre d’enthymèmes détectés\n"
            "value = min(enthymeme_signal / 4, 1.0)",
            language="python"
        )

        st.markdown("**Valeur actuelle**")
        st.write(f"Signal : **{result['enthymeme_signal']} repéré(s)**")
        st.write(f"Niveau : **{result['enthymeme_label']}**")
        st.write(f"Score jauge : **{round(value * 100, 1)}%**")

        st.markdown("**Lecture**")
        st.write(
            "🟢 Aucun signal : aucun raisonnement implicite repéré\n"
            "🟡 Signal faible : prémisse implicite ponctuelle\n"
            "🟠 Signal modéré : plusieurs raisonnements incomplets\n"
            "🔴 Signal fort : forte dépendance à des prémisses non explicitées"
        )

        st.markdown("**Attention**")
        st.write(
            "Un enthymème n’est pas forcément une erreur. "
            "Il indique seulement qu’une partie du raisonnement est laissée implicite."
        )
# -----------------------------
# Fausse analogie
# -----------------------------
with al9:
    st.markdown("### Fausse analogie")
    st.caption("Comparaisons trompeuses qui court-circuitent l’analyse.")

    value = result["false_analogy_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["false_analogy_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("false_analogy_markers", [])
        if not markers:
            st.info("Aucune fausse analogie notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Fausse analogie")

        st.write(
            "Cette jauge détecte les comparaisons qui rapprochent deux situations "
            "de manière trompeuse ou simplificatrice."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs d’analogie douteuse : "
            "rapprochements abusifs, comparaisons rapides ou équivalences non démontrées."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = analogies trompeuses détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("false_analogy_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["false_analogy_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : comparaisons pertinentes ou absentes\n"
            "🟡 Modérée : analogies discutables ponctuelles\n"
            "🟠 Élevée : analogies trompeuses notables\n"
            "🔴 Très élevée : analogies abusives dominantes"
        )

        st.markdown("**Attention**")
        st.write(
            "Une fausse analogie élevée ne signifie pas que le texte est faux. "
            "Elle indique que le raisonnement repose sur des comparaisons fragiles."
        )
# -----------------------------
#  Surinterprétation factuelle
# -----------------------------
with al10:
    st.markdown("### Surinterprétation factuelle")
    st.caption("Conclusions excessives tirées à partir d’indices partiels.")

    value = result["factual_overinterpretation_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["factual_overinterpretation_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("factual_overinterpretation_markers", [])
        if not markers:
            st.info("Aucune surinterprétation factuelle notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Surinterprétation factuelle")

        st.write(
            "Cette jauge détecte les situations où des conclusions sont tirées "
            "à partir d’indices partiels, insuffisants ou mal étayés."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de surinterprétation : "
            "généralisation rapide, extrapolation excessive, ou conclusions "
            "qui dépassent les éléments disponibles."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = surinterprétations détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("factual_overinterpretation_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["factual_overinterpretation_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : conclusions proportionnées aux faits\n"
            "🟡 Modérée : extrapolations ponctuelles\n"
            "🟠 Élevée : conclusions excessives notables\n"
            "🔴 Très élevée : surinterprétation dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une surinterprétation factuelle élevée ne signifie pas que le texte est faux. "
            "Elle indique que les conclusions dépassent les éléments réellement disponibles."
        )
# =============================
# Fausse causalité (simple)
# =============================
with al11:
    st.markdown("### Fausse causalité (simple)")
    st.caption("Lien causal affirmé sans démonstration suffisante.")

    value = result["false_causality_basic_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["false_causality_basic_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("false_causality_basic_markers", [])
        if not markers:
            st.info("Aucune fausse causalité simple notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Fausse causalité (simple)")

        st.write(
            "Cette jauge détecte les situations où un lien de cause à effet est affirmé "
            "sans preuve suffisante ou sans démonstration rigoureuse."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de causalité abusive : "
            "enchaînement rapide d’événements, corrélation présentée comme causalité, "
            "ou conclusion causale non justifiée."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = causalités abusives détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("false_causality_basic_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["false_causality_basic_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : causalité peu affirmée ou prudente\n"
            "🟡 Modérée : liens causaux discutables ponctuels\n"
            "🟠 Élevée : causalité abusive notable\n"
            "🔴 Très élevée : causalité non démontrée dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une fausse causalité élevée ne signifie pas que la relation est fausse. "
            "Elle indique que le lien causal est affirmé plus vite qu’il n’est démontré."
        )
al13, al14 = st.columns(2)
# -----------------------------
#  Généralisation abusive
# -----------------------------
with al12:
    st.markdown("### Généralisation abusive")
    st.caption("Simplification du réel par catégories globales.")

    generalization_value = result["generalization_score"]

    if generalization_value < 0.20:
        generalization_label, generalization_color = "Faible", "#ca8a04"
    elif generalization_value < 0.40:
        generalization_label, generalization_color = "Modérée", "#f97316"
    elif generalization_value < 0.70:
        generalization_label, generalization_color = "Élevée", "#ea580c"
    else:
        generalization_label, generalization_color = "Très élevée", "#dc2626"

    render_custom_gauge(generalization_value, generalization_color)

    st.markdown(
        f"<b style='color:{generalization_color}'>{generalization_label}</b> — {round(generalization_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["generalization_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("generalization_markers", [])
        if not markers:
            st.info("Aucune généralisation abusive notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Généralisation abusive")

        st.write(
            "Cette jauge détecte les situations où des cas particuliers sont transformés "
            "en règles générales ou en vérités globales."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de généralisation : "
            "emploi de termes globaux (toujours, jamais, tous, etc.), "
            "ou extension abusive d’un cas à l’ensemble."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = généralisations détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("generalization_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(generalization_value * 100, 1)}%**")
        st.write(f"Niveau : **{generalization_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["generalization_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours nuancé\n"
            "🟡 Modérée : généralisations ponctuelles\n"
            "🟠 Élevée : généralisation notable\n"
            "🔴 Très élevée : généralisation dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une généralisation abusive élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours simplifie excessivement la réalité."
        )

st.divider()
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# =============================
# 🧪 6. BIAIS DE FORMULATION
# =============================
st.subheader("🧪 Biais de formulation")
st.caption("Biais liés au langage, à la présentation et à l’apparence de crédibilité.")

bf1, bf2, bf3, bf4 = st.columns(4)
# -----------------------------
#  Autorité vague
# -----------------------------
with bf1:
    st.markdown("### Autorité vague")
    st.caption("Appels à des experts, études ou spécialistes sans source précise.")

    vague_auth_value = result["vague_authority_score"]

    if vague_auth_value < 0.20:
        vague_auth_label, vague_auth_color = "Faible", "#ca8a04"
    elif vague_auth_value < 0.40:
        vague_auth_label, vague_auth_color = "Modérée", "#f97316"
    elif vague_auth_value < 0.70:
        vague_auth_label, vague_auth_color = "Élevée", "#ea580c"
    else:
        vague_auth_label, vague_auth_color = "Très élevée", "#dc2626"

    render_custom_gauge(vague_auth_value, vague_auth_color)

    st.markdown(
        f"<b style='color:{vague_auth_color}'>{vague_auth_label}</b> — {round(vague_auth_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["vague_authority_interpretation"])

    # 🔎 Marqueurs
    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("vague_authority_markers", [])
        if not markers:
            st.info("Aucun marqueur d'autorité vague détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    # ℹ️ Explication
    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Autorité vague")

        st.write(
            "Cette jauge détecte les appels à l’autorité non vérifiables : experts non nommés, "
            "études sans source, ou références imprécises."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs d’autorité vague : formulations du type "
            "“selon des experts”, “des études montrent”, sans précision ni source traçable."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs d’autorité vague détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("vague_authority_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(vague_auth_value * 100, 1)}%**")
        st.write(f"Niveau : **{vague_auth_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["vague_authority_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : sources explicites ou absentes\n"
            "🟡 Modérée : références peu précises\n"
            "🟠 Élevée : appui fréquent sur des autorités vagues\n"
            "🔴 Très élevée : argument d’autorité dominant et non vérifiable"
        )

        st.markdown("**Attention**")
        st.write(
            "Une autorité vague élevée ne signifie pas que l’information est fausse. "
            "Elle indique que les sources sont insuffisamment précises pour être vérifiées."
        )
# -----------------------------
#  Qualifications normatives
# -----------------------------
with bf2:
    st.markdown("### Qualification normative")
    st.caption("Jugements de valeur présentés comme des faits.")

    normative_value = result.get("normative_charge_score", 0)

    if normative_value < 0.20:
        normative_label, normative_color = "Faible", "#ca8a04"
    elif normative_value < 0.40:
        normative_label, normative_color = "Modérée", "#f97316"
    elif normative_value < 0.70:
        normative_label, normative_color = "Élevée", "#ea580c"
    else:
        normative_label, normative_color = "Très élevée", "#dc2626"

    render_custom_gauge(normative_value, normative_color)

    st.markdown(
        f"<b style='color:{normative_color}'>{normative_label}</b> — {round(normative_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["normative_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        normative_terms = result.get("normative_terms", [])
        judgment_markers = result.get("normative_judgment_markers", [])

        if not normative_terms and not judgment_markers:
            st.info("Aucun marqueur saillant détecté.")
        else:
            if normative_terms:
                st.markdown("**Termes normatifs**")
                for term in normative_terms:
                    st.error(term)

            if judgment_markers:
                st.markdown("**Marqueurs de jugement**")
                for term in judgment_markers:
                    st.warning(term)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Qualification normative")

        st.write(
            "Cette jauge détecte les jugements de valeur présentés comme s’ils étaient des faits. "
            "Elle repère les formulations qui qualifient moralement, politiquement ou affectivement une réalité "
            "sans toujours distinguer description et jugement."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à deux familles de signaux : les termes normatifs "
            "et les marqueurs explicites de jugement."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "normative_terms = termes normatifs détectés\n"
            "judgment_markers = marqueurs de jugement détectés\n"
            "score = min((len(normative_terms) + len(judgment_markers)) * coefficient / 10, 1.0)",
            language="python"
        )

        normative_terms = result.get("normative_terms", [])
        judgment_markers = result.get("normative_judgment_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(normative_value * 100, 1)}%**")
        st.write(f"Niveau : **{normative_label}**")
        st.write(f"Termes normatifs : **{len(normative_terms)}**")
        st.write(f"Marqueurs de jugement : **{len(judgment_markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["normative_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours surtout descriptif\n"
            "🟡 Modérée : quelques jugements intégrés au discours\n"
            "🟠 Élevée : forte présence de qualification normative\n"
            "🔴 Très élevée : jugement de valeur dominant"
        )

        st.markdown("**Attention**")
        st.write(
            "Une qualification normative élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours présente davantage des jugements comme des évidences "
            "que des faits strictement démontrés."
        )
# -----------------------------
#  Scientificité rhétorique
# -----------------------------
with bf3:
    st.markdown("### Scientificité rhétorique")
    st.caption("Simulation d’objectivité scientifique sans base identifiable.")

    sim_value = result["scientific_simulation_score"]

    if sim_value < 0.20:
        sim_label, sim_color = "Faible", "#ca8a04"
    elif sim_value < 0.40:
        sim_label, sim_color = "Modérée", "#f97316"
    elif sim_value < 0.70:
        sim_label, sim_color = "Élevée", "#ea580c"
    else:
        sim_label, sim_color = "Très élevée", "#dc2626"

    render_custom_gauge(sim_value, sim_color)

    st.markdown(
        f"<b style='color:{sim_color}'>{sim_label}</b> — {round(sim_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["scientific_simulation_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("scientific_simulation_markers", [])
        if not markers:
            st.info("Aucun marqueur de scientificité rhétorique détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Scientificité rhétorique")

        st.write(
            "Cette jauge détecte les formulations qui donnent une apparence scientifique au discours "
            "sans fournir de base identifiable, vérifiable ou sourcée."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de scientificité rhétorique : vocabulaire technique, "
            "références à des études, chiffres ou méthodes sans ancrage précis."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de scientificité rhétorique détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("scientific_simulation_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(sim_value * 100, 1)}%**")
        st.write(f"Niveau : **{sim_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["scientific_simulation_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : peu d’apparence scientifique non fondée\n"
            "🟡 Modérée : quelques signaux d’objectivité rhétorique\n"
            "🟠 Élevée : forte apparence scientifique à vérifier\n"
            "🔴 Très élevée : simulation scientifique dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une scientificité rhétorique élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours mobilise une apparence de science sans rendre ses bases clairement vérifiables."
        )     
# -----------------------------
#  Glissement sémantique
# -----------------------------
with bf4:
    st.markdown("### Glissement sémantique")
    st.caption("Recadrage lexical stratégique du réel par des termes orientés.")

    semantic_value = result["semantic_shift_score"]

    if semantic_value < 0.20:
        semantic_label, semantic_color = "Faible", "#ca8a04"
    elif semantic_value < 0.40:
        semantic_label, semantic_color = "Modérée", "#f97316"
    elif semantic_value < 0.70:
        semantic_label, semantic_color = "Élevée", "#ea580c"
    else:
        semantic_label, semantic_color = "Très élevée", "#dc2626"

    render_custom_gauge(semantic_value, semantic_color)

    st.markdown(
        f"<b style='color:{semantic_color}'>{semantic_label}</b> — {round(semantic_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["semantic_shift_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("semantic_shift_markers", [])
        if not markers:
            st.info("Aucun glissement sémantique notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Glissement sémantique")

        st.write(
            "Cette jauge détecte les recadrages lexicaux : un mot ou une expression peut déplacer "
            "la perception du réel en imposant une lecture orientée."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de glissement sémantique : termes qui déplacent "
            "le sens, requalifient une situation ou transforment une description en cadrage interprétatif."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de glissement sémantique détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("semantic_shift_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(semantic_value * 100, 1)}%**")
        st.write(f"Niveau : **{semantic_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["semantic_shift_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : vocabulaire peu recadrant\n"
            "🟡 Modérée : quelques termes orientent la lecture\n"
            "🟠 Élevée : recadrage lexical notable\n"
            "🔴 Très élevée : forte requalification stratégique du réel"
        )

        st.markdown("**Attention**")
        st.write(
            "Un glissement sémantique élevé ne signifie pas que le texte est faux. "
            "Il indique que le choix des mots peut déplacer l’interprétation du lecteur."
        )

bf5, bf6, bf7, bf8 = st.columns(4)
# -----------------------------
#  Faux consensus
# -----------------------------
with bf5:
    st.markdown("### Faux consensus")
    st.caption("Simulation d’un accord collectif présenté comme évident.")

    false_consensus_value = result["false_consensus_score"]

    if false_consensus_value < 0.15:
        false_consensus_label, false_consensus_color = "Faible", "#ca8a04"
    elif false_consensus_value < 0.35:
        false_consensus_label, false_consensus_color = "Modérée", "#f97316"
    elif false_consensus_value < 0.60:
        false_consensus_label, false_consensus_color = "Élevée", "#ea580c"
    else:
        false_consensus_label, false_consensus_color = "Très élevée", "#dc2626"

    render_custom_gauge(false_consensus_value, false_consensus_color)

    st.markdown(
        f"<b style='color:{false_consensus_color}'>{false_consensus_label}</b> — {round(false_consensus_value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["false_consensus_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("false_consensus_markers", [])
        if not markers:
            st.info("Aucun faux consensus notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Faux consensus")

        st.write(
            "Cette jauge détecte les formulations qui donnent l’impression qu’un accord collectif existe, "
            "alors que cet accord n’est pas démontré."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de consensus apparent : expressions comme "
            "“tout le monde sait”, “personne ne conteste”, ou formes équivalentes."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de faux consensus détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("false_consensus_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(false_consensus_value * 100, 1)}%**")
        st.write(f"Niveau : **{false_consensus_label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["false_consensus_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : pas de consensus simulé\n"
            "🟡 Modérée : accord collectif suggéré ponctuellement\n"
            "🟠 Élevée : consensus apparent notable\n"
            "🔴 Très élevée : accord collectif fortement présenté comme évident"
        )

        st.markdown("**Attention**")
        st.write(
            "Un faux consensus élevé ne signifie pas que l’idée est fausse. "
            "Il indique seulement que le texte présente un accord collectif sans le démontrer clairement."
        )      
    # =============================
    # Autorité vague (simple)
    # =============================
    with bf6:
        st.markdown("### Autorité déclarative")
        st.caption(
            "Détection brute des appels à une autorité évoquée sans référence explicite."
        )
        value = result["vague_authority_basic_score"]
    
        if value < 0.15:
            label, color = "Faible", "#ca8a04"
        elif value < 0.35:
            label, color = "Modérée", "#f97316"
        elif value < 0.60:
            label, color = "Élevée", "#ea580c"
        else:
            label, color = "Très élevée", "#dc2626"
    
        render_custom_gauge(value, color)
    
        st.markdown(
            f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
            unsafe_allow_html=True
        )
    
        st.caption(result["vague_authority_basic_interpretation"])
    
        with st.expander("🔎 Voir les marqueurs", expanded=False):
            markers = result.get("vague_authority_basic_markers", [])
            if not markers:
                st.info("Aucune autorité déclarative notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)
    
        with st.popover("ℹ️ Comprendre cette jauge"):
            st.markdown("### Autorité déclarative")
    
            st.write(
                "Cette jauge détecte uniquement les formulations déclaratives invoquant une autorité sans référence explicite."
                "experts, études ou sources évoqués sans référence vérifiable."
            )
    
            st.markdown("**Principe**")
            st.write(
                "Le texte est comparé à des marqueurs d’autorité vague : "
                "expressions comme « des experts », « des études montrent », "
                "sans indication claire de source."
            )
    
            st.markdown("**Formule utilisée**")
            st.code(
                "markers = autorités vagues détectées\n"
                "score = min(len(markers) * coefficient / 10, 1.0)",
                language="python"
            )
    
            markers = result.get("vague_authority_basic_markers", [])
    
            st.markdown("**Valeur actuelle**")
            st.write(f"Score : **{round(value * 100, 1)}%**")
            st.write(f"Niveau : **{label}**")
            st.write(f"Marqueurs détectés : **{len(markers)}**")
    
            st.markdown("**Interprétation actuelle**")
            st.write(result["vague_authority_basic_interpretation"])
    
            st.markdown("**Lecture**")
            st.write(
                "🟢 Faible : sources précises ou absentes\n"
                "🟡 Modérée : références floues ponctuelles\n"
                "🟠 Élevée : recours notable à des autorités non identifiées\n"
                "🔴 Très élevée : argument d’autorité flou dominant"
            )
    
            st.markdown("**Attention**")
            st.write(
                "Une autorité vague élevée ne signifie pas que le contenu est faux. "
                "Elle indique que les sources invoquées ne sont pas clairement vérifiables."
            )
# -----------------------------
#  Saturation normative
# -----------------------------
with bf7:
    st.markdown("### Saturation normative")
    st.caption("Accumulation de jugements moraux à la place de l’analyse.")

    value = result["normative_saturation_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["normative_saturation_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("normative_saturation_markers", [])
        if not markers:
            st.info("Aucune saturation normative notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Saturation normative")

        st.write(
            "Cette jauge détecte l’accumulation de jugements moraux ou évaluatifs "
            "qui peuvent remplacer l’analyse démonstrative."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de saturation normative : "
            "enchaînement de qualifications morales, jugements de valeur répétés, "
            "ou vocabulaire évaluatif dominant."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de saturation normative détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("normative_saturation_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["normative_saturation_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : peu de saturation normative\n"
            "🟡 Modérée : quelques jugements accumulés\n"
            "🟠 Élevée : forte densité de jugements\n"
            "🔴 Très élevée : jugement moral dominant au détriment de l’analyse"
        )

        st.markdown("**Attention**")
        st.write(
            "Une saturation normative élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours accumule des jugements de valeur, parfois au détriment de la démonstration."
        )
st.divider()

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# -----------------------------
# Manipulation statistique
# -----------------------------
st.subheader("📊 Analyse statistique et quantitative")

sq1, sq2, sq3 = st.columns(3)

with sq1:
    st.markdown("### Manipulation statistique")
    st.caption("Usage orienté ou dramatisé des chiffres et statistiques.")

    value = result["statistical_manipulation_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["statistical_manipulation_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("statistical_manipulation_markers", [])

        if not markers:
            st.info("Aucune manipulation statistique notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Manipulation statistique")

        st.write(
            "Cette jauge détecte les usages orientés, dramatisés ou insuffisamment contextualisés "
            "des chiffres et statistiques."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de manipulation statistique : "
            "pourcentages alarmistes, chiffres sans contexte, amplification quantitative "
            "ou formulations donnant aux statistiques une apparence de preuve absolue."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs statistiques détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("statistical_manipulation_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["statistical_manipulation_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : statistiques utilisées avec prudence\n"
            "🟡 Modérée : quelques usages orientés des chiffres\n"
            "🟠 Élevée : plusieurs procédés statistiques fragiles ou dramatisés\n"
            "🔴 Très élevée : chiffres fortement utilisés pour orienter la perception"
        )

        st.markdown("**Attention**")
        st.write(
            "Une manipulation statistique élevée ne signifie pas que les chiffres sont faux. "
            "Elle indique que leur présentation peut orienter l’interprétation du lecteur."
        )
# -----------------------------
# Comparaison trompeuse
# -----------------------------
with sq2:
    st.markdown("### Comparaison trompeuse")
    st.caption("Comparaisons quantitatives sans référentiel ou contexte suffisant.")

    value = result["misleading_comparison_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["misleading_comparison_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("misleading_comparison_markers", [])

        if not markers:
            st.info("Aucune comparaison trompeuse notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Comparaison trompeuse")

        st.write(
            "Cette jauge détecte les comparaisons quantitatives utilisées sans référentiel clair "
            "ou de manière potentiellement orientée."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est comparé à des marqueurs de comparaison fragile : "
            "écarts sans base comparative précise, amplifications historiques "
            "ou formulations quantitatives impressionnistes."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = comparaisons problématiques détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["misleading_comparison_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : comparaisons contextualisées\n"
            "🟡 Modérée : quelques comparaisons fragiles\n"
            "🟠 Élevée : comparaisons orientées notables\n"
            "🔴 Très élevée : usage massif de comparaisons potentiellement trompeuses"
        )

        st.markdown("**Attention**")
        st.write(
            "Une comparaison trompeuse élevée ne signifie pas que les données sont fausses. "
            "Elle indique que la comparaison utilisée peut orienter fortement la perception."
        )

# -----------------------------
# Données sans référentiel
# -----------------------------
with sq3:
    st.markdown("### Données sans référentiel")
    st.caption("Chiffres ou projections présentés sans base méthodologique claire.")

    value = result["missing_reference_score"]

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["missing_reference_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("missing_reference_markers", [])

        if not markers:
            st.info("Aucune donnée sans référentiel notable détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Données sans référentiel")

        st.write(
            "Cette jauge détecte les chiffres, statistiques ou projections "
            "présentés sans source, méthodologie ou contexte suffisamment explicites."
        )

        st.markdown("**Principe**")
        st.write(
            "Le texte est analysé afin d’identifier les données quantitatives "
            "utilisées sans référentiel clair : absence d’échantillon, de source, "
            "de période, de modèle ou de méthodologie identifiable."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = données insuffisamment référencées détectées\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result["missing_reference_interpretation"])

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : données bien contextualisées\n"
            "🟡 Modérée : quelques références méthodologiques manquent\n"
            "🟠 Élevée : plusieurs données insuffisamment sourcées\n"
            "🔴 Très élevée : usage massif de chiffres sans référentiel clair"
        )

        st.markdown("**Attention**")
        st.write(
            "Une donnée sans référentiel ne signifie pas nécessairement qu’elle est fausse. "
            "Elle indique que son cadre méthodologique reste insuffisamment explicité."
        )

st.divider()

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# =============================
# Jauges structurelles avancées
# =============================

result = st.session_state.get("last_result")
article_for_analysis = st.session_state.get("last_article", "")

if not result:
    st.info(T["paste_text_or_load_url"])
    st.stop()

st.subheader("Jauges structurelles avancées")

js1, js2, js3 = st.columns(3)

# -----------------------------
# 1) Saut logique
# -----------------------------
with js1:
    st.markdown("### Saut logique")
    st.caption("Rupture ou accélération excessive dans l’enchaînement du raisonnement.")

    value = result.get("logical_jump_score", 0)

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result.get("logical_jump_interpretation", ""))

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("logical_jump_markers", [])
        if not markers:
            st.info("Aucun saut logique notable détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Saut logique")

        st.write(
            "Cette jauge détecte les passages où le raisonnement avance trop vite : "
            "une conclusion apparaît sans transition suffisante ou sans étapes argumentatives explicites."
        )

        st.markdown("**Principe**")
        st.write(
            "Elle repère les ruptures dans l’enchaînement logique : passage brusque d’un fait à une conclusion, "
            "enchaînement causal insuffisant, ou absence d’étapes intermédiaires."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "markers = marqueurs de saut logique détectés\n"
            "score = min(len(markers) * coefficient / 10, 1.0)",
            language="python"
        )

        markers = result.get("logical_jump_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result.get("logical_jump_interpretation", ""))

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : enchaînement progressif\n"
            "🟡 Modérée : quelques transitions rapides\n"
            "🟠 Élevée : conclusion avancée trop vite\n"
            "🔴 Très élevée : rupture logique dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Un saut logique élevé ne signifie pas que la conclusion est fausse. "
            "Il indique que le chemin argumentatif entre les prémisses et la conclusion est insuffisamment explicité."
        )

# -----------------------------
# 2) Densité argumentative
# -----------------------------
with js2:
    st.markdown("### Densité argumentative")
    st.caption("Quantité d’éléments argumentatifs présents dans le texte.")

    value = result.get("argument_density_score", 0)

    if value < 0.15:
        label, color = "Très faible", "#dc2626"
    elif value < 0.35:
        label, color = "Faible", "#f97316"
    elif value < 0.60:
        label, color = "Correcte", "#ca8a04"
    elif value < 0.80:
        label, color = "Solide", "#84cc16"
    else:
        label, color = "Très élevée", "#16a34a"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result.get("argument_density_interpretation", ""))

    with st.expander("🔎 Voir les indicateurs", expanded=False):
        markers = result.get("argument_density_markers", [])
        if not markers:
            st.info("Aucun indicateur argumentatif détaillé disponible.")
        else:
            for marker in markers:
                st.success(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Densité argumentative")

        st.write(
            "Cette jauge mesure la présence d’éléments argumentatifs dans le texte : "
            "raisons, justifications, connecteurs logiques, exemples ou développements explicatifs."
        )

        st.markdown("**Principe**")
        st.write(
            "Contrairement aux jauges de risque, une densité argumentative élevée est plutôt positive : "
            "elle indique que le texte développe davantage ses raisons au lieu d’énoncer simplement une conclusion."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "argumentative_units = raisons + conclusions + (nuances × 0.35)\n"
            "score = min((argumentative_units / nombre_de_mots) × 22, 1.0)",
            language="python"
        )

        markers = result.get("argument_density_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Indicateurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result.get("argument_density_interpretation", ""))

        st.markdown("**Lecture**")
        st.write(
            "🔴 Très faible : peu d’argumentation explicite\n"
            "🟠 Faible : justification limitée\n"
            "🟡 Correcte : argumentation présente\n"
            "🟢 Solide : bonne densité argumentative\n"
            "🟢 Très élevée : texte fortement argumenté"
        )

        st.markdown("**Attention**")
        st.write(
            "Une forte densité argumentative ne garantit pas que le texte est vrai. "
            "Elle indique seulement que le discours contient davantage de matière argumentative."
        )

# -----------------------------
# 3) Certitude forte composée
# -----------------------------
with js3:
    st.markdown("### Certitude forte composée")
    st.caption("Accumulation de marqueurs de certitude renforçant le verrouillage du discours.")

    value = result.get("strong_certainty_score", 0)

    if value < 0.15:
        label, color = "Faible", "#ca8a04"
    elif value < 0.35:
        label, color = "Modérée", "#f97316"
    elif value < 0.60:
        label, color = "Élevée", "#ea580c"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result.get("strong_certainty_interpretation", ""))

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("strong_certainty_markers", [])
        if not markers:
            st.info("Aucun marqueur de certitude forte détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):
        st.markdown("### Certitude forte composée")

        st.write(
            "Cette jauge détecte l’accumulation de formulations de certitude : "
            "affirmations catégoriques, absence de nuance, impossibilité suggérée du doute."
        )

        st.markdown("**Principe**")
        st.write(
            "Elle mesure non pas une certitude isolée, mais leur accumulation. "
            "Plus les marqueurs de certitude se multiplient, plus le discours tend à se fermer."
        )

        st.markdown("**Formule utilisée**")
        st.code(
            "raw_score = (len(markers) / nombre_de_phrases) × 3.0\n"
            "hedge_reduction = min(len(marqueurs_de_prudence) × 0.08, 0.45)\n"
            "score = max(0.0, raw_score - hedge_reduction)"
        )

        markers = result.get("strong_certainty_markers", [])

        st.markdown("**Valeur actuelle**")
        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
        st.write(f"Marqueurs de prudence : **{result.get('strong_certainty_hedge_count', 0)}**")

        st.markdown("**Interprétation actuelle**")
        st.write(result.get("strong_certainty_interpretation", ""))

        st.markdown("**Lecture**")
        st.write(
            "🟢 Faible : discours ouvert et nuancé\n"
            "🟡 Modérée : quelques affirmations fortes\n"
            "🟠 Élevée : certitude marquée\n"
            "🔴 Très élevée : fermeture argumentative dominante"
        )

        st.markdown("**Attention**")
        st.write(
            "Une certitude forte composée élevée ne signifie pas que le texte est faux. "
            "Elle indique que le discours laisse peu de place à la nuance ou à la remise en question."
        )
js4, js5, js6 = st.columns(3)
# =============================
#  Cohérence trompeuse avancée
# =============================
with js4:
    st.markdown("### Cohérence trompeuse avancée")
    st.caption(
        "Discours paraissant très cohérent malgré une base démonstrative fragile ou orientée."
    )

    value = result["advanced_deceptive_coherence_score"]

    if value < 0.15:
        label, color = "Faible", "#16a34a"
    elif value < 0.35:
        label, color = "Modérée", "#ca8a04"
    elif value < 0.60:
        label, color = "Élevée", "#f97316"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["advanced_deceptive_coherence_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):
        markers = result.get("advanced_deceptive_coherence_markers", [])

        if not markers:
            st.info("Aucune cohérence trompeuse avancée détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):

        st.markdown("### Cohérence trompeuse avancée")

        st.write(
            "Cette jauge détecte les discours qui donnent une forte impression "
            "de cohérence logique tout en restant fragiles, peu démonstratifs "
            "ou fortement orientés."
        )

        st.markdown("**Principe**")

        st.write(
            "Le moteur compare la cohérence apparente du raisonnement "
            "à la solidité réelle des démonstrations, des preuves "
            "et de la révisabilité du discours."
        )

        st.markdown("**Formule utilisée**")

        st.code(
            "raw_score = len(markers) × 0.18\n"
            "nuance_reduction = min(len(marqueurs_de_nuance) × 0.04, 0.25)\n"
            "score = max(0.0, raw_score - nuance_reduction)",
            language="python"
        )

        markers = result.get("advanced_deceptive_coherence_markers", [])

        st.markdown("**Valeur actuelle**")

        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")
        st.write(
            f"Marqueurs de nuance : **{result.get('advanced_deceptive_coherence_nuance_count', 0)}**"
        )

        st.markdown("**Interprétation actuelle**")

        st.write(
            result["advanced_deceptive_coherence_interpretation"]
        )

        st.markdown("**Lecture**")

        st.write(
            "🟢 Faible : cohérence globalement saine\n"
            "🟡 Modérée : cohérence partiellement orientée\n"
            "🟠 Élevée : cohérence persuasive mais fragile\n"
            "🔴 Très élevée : architecture rhétorique fortement trompeuse"
        )

        st.markdown("**Attention**")

        st.write(
            "Une cohérence trompeuse élevée ne signifie pas automatiquement "
            "que le texte est faux. Elle indique qu’un raisonnement "
            "peut paraître solide tout en reposant sur des bases fragiles "
            "ou insuffisamment démontrées."
        )

# =============================
# Enthymèmes implicites complexes
# =============================
with js5:
    st.markdown("### Enthymèmes implicites complexes")
    st.caption(
        "Raisonnements incomplets ou implicites nécessitant des prémisses non formulées."
    )

    value = result["complex_enthymeme_score"]

    if value < 0.15:
        label, color = "Faible", "#16a34a"
    elif value < 0.35:
        label, color = "Modérée", "#ca8a04"
    elif value < 0.60:
        label, color = "Élevée", "#f97316"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["complex_enthymeme_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):

        markers = result.get("complex_enthymeme_markers", [])

        if not markers:
            st.info("Aucun enthymème complexe détecté.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):

        st.markdown("### Enthymèmes implicites complexes")

        st.write(
            "Cette jauge détecte les raisonnements qui paraissent logiques "
            "mais dont certaines prémisses restent implicites ou non démontrées."
        )

        st.markdown("**Principe**")

        st.write(
            "Le moteur recherche des enchaînements où une conclusion "
            "semble découler naturellement d’un raisonnement, "
            "alors que plusieurs étapes logiques restent cachées."
        )

        st.markdown("**Formule utilisée**")

        st.code(
            "markers = prémisses implicites + conclusions forcées\n"
            "score = min(len(markers) * coefficient, 1.0)",
            language="python"
        )

        markers = result.get("complex_enthymeme_markers", [])

        st.markdown("**Valeur actuelle**")

        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")

        st.write(
            result["complex_enthymeme_interpretation"]
        )

        st.markdown("**Lecture**")

        st.write(
            "🟢 Faible : raisonnement plutôt explicite\n"
            "🟡 Modérée : quelques prémisses implicites\n"
            "🟠 Élevée : raisonnement fortement incomplet\n"
            "🔴 Très élevée : architecture logique largement implicite"
        )

        st.markdown("**Attention**")

        st.write(
            "Un enthymème complexe élevé ne signifie pas forcément "
            "que le texte est faux. Il indique que le raisonnement "
            "demande au lecteur d’accepter plusieurs prémisses "
            "non démontrées."
        )

# =============================
# Auto-validation narrative
# =============================
with js6:
    st.markdown("### Auto-validation narrative")
    st.caption(
        "Le discours transforme les critiques ou oppositions en confirmation implicite."
    )

    value = result["self_validating_score"]

    if value < 0.15:
        label, color = "Faible", "#16a34a"
    elif value < 0.35:
        label, color = "Modérée", "#ca8a04"
    elif value < 0.60:
        label, color = "Élevée", "#f97316"
    else:
        label, color = "Très élevée", "#dc2626"

    render_custom_gauge(value, color)

    st.markdown(
        f"<b style='color:{color}'>{label}</b> — {round(value * 100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption(result["self_validating_interpretation"])

    with st.expander("🔎 Voir les marqueurs", expanded=False):

        markers = result.get("self_validating_markers", [])

        if not markers:
            st.info("Aucune auto-validation narrative détectée.")
        else:
            for marker in markers:
                st.warning(marker)

    with st.popover("ℹ️ Comprendre cette jauge"):

        st.markdown("### Auto-validation narrative")

        st.write(
            "Cette jauge détecte les discours qui utilisent "
            "les critiques, oppositions ou censures comme preuve "
            "de leur propre validité."
        )

        st.markdown("**Principe**")

        st.write(
            "Le moteur recherche des structures circulaires où "
            "la contradiction devient elle-même un argument de confirmation."
        )

        st.markdown("**Formule utilisée**")

        st.code(
            "critique → validation implicite\n"
            "censure → preuve de vérité\n"
            "opposition → confirmation du récit",
            language="python"
        )

        markers = result.get("self_validating_markers", [])

        st.markdown("**Valeur actuelle**")

        st.write(f"Score : **{round(value * 100, 1)}%**")
        st.write(f"Niveau : **{label}**")
        st.write(f"Marqueurs détectés : **{len(markers)}**")

        st.markdown("**Interprétation actuelle**")

        st.write(
            result["self_validating_interpretation"]
        )

        st.markdown("**Lecture**")

        st.write(
            "🟢 Faible : discours ouvert à la contradiction\n"
            "🟡 Modérée : quelques boucles narratives\n"
            "🟠 Élevée : contradiction absorbée par le récit\n"
            "🔴 Très élevée : système discursif auto-validant"
        )

        st.markdown("**Attention**")

        st.write(
            "Une auto-validation narrative élevée ne signifie pas "
            "automatiquement que le texte est faux. "
            "Elle indique que le discours tend à neutraliser "
            "la contradiction en l’intégrant dans son propre récit."
        )
        
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

st.subheader("Structure cognitive du texte analysé")
st.info(T["llm_intro"])

cog = Cognition(result["G"], result["N"], result["D"])
overconfidence = result["D"] - (result["G"] + result["N"])
calibration = result["D"] / (result["G"] + result["N"]) if (result["G"] + result["N"]) > 0 else 10
revisability = (result["G"] + result["N"] + result["V"]) - result["D"]
closure = (result["D"] * (1 + len(result["red_flags"]) / 5)) / (result["G"] + result["N"]) if (result["G"] + result["N"]) > 0 else 10

c1, c2 = st.columns(2)
c1.metric(T["overconfidence"], round(overconfidence, 2))
c2.metric(T["calibration"], round(calibration, 2))
c3, c4 = st.columns(2)
c3.metric(T["revisability"], round(revisability, 2))
c4.metric(T["cognitive_closure"], round(closure, 2))

st.divider()

st.subheader("Jauge de clôture cognitive")

st.caption(
    "Cette jauge mesure le degré de verrouillage cognitif du texte. "
    "Plus elle monte, plus la certitude domine le savoir et l’intégration."
)

closure_gauge = min(closure / 1.5, 1.0)

closure_label, closure_color, closure_text = interpret_closure_gauge(closure)

render_custom_gauge(closure_gauge, closure_color)

st.markdown(
    f"<b style='color:{closure_color}'>{closure_label}</b> — {round(closure,2)}",
    unsafe_allow_html=True
)

st.caption("Ouverture cognitive ⟵⟶ Clôture cognitive")

st.caption(closure_text)
st.markdown(f"**{T['interpretation']} :** {cog.interpret()}")

# =============================
# Ancrage au réel
# =============================

st.markdown("──── 🧪 ────")
st.subheader("Ancrage au réel")

st.caption(
    "Cette jauge mesure dans quelle mesure le discours reste contraint "
    "par l’expérience, la reproductibilité, la falsifiabilité et "
    "la reconnaissance explicite de ses limites."
)

anchor_score = result.get("real_anchor_score", 0)
anchor_label = result.get("real_anchor_label", "Non calculé")
anchor_text = result.get("real_anchor_interpretation", "")

if anchor_score < 3:
    anchor_color = "#7f1d1d"   # rouge sombre
    anchor_label = "Très faible"

elif anchor_score < 7:
    anchor_color = "#b45309"   # cuivre
    anchor_label = "Fragile"

elif anchor_score < 12:
    anchor_color = "#a16207"   # ambre
    anchor_label = "Modéré"

elif anchor_score < 16:
    anchor_color = "#57534e"   # pierre / neutre
    anchor_label = "Fort"

else:
    anchor_color = "#334155"   # bleu acier
    anchor_label = "Très fort"

render_custom_gauge(anchor_score / 20, anchor_color)

st.markdown(
    f"<b style='color:{anchor_color}'>{anchor_label}</b> — {anchor_score}/20",
    unsafe_allow_html=True
)

st.caption(anchor_text)

st.caption("Spéculation libre ⟵⟶ Contrainte du réel")

st.caption(
    "Contrairement aux jauges morales classiques, cette palette ne récompense "
    "pas une supposée vérité. Elle visualise la tension entre spéculation libre "
    "et contrainte du réel. Les couleurs froides et minérales indiquent "
    "une structure davantage stabilisée par l’expérience et la reproductibilité."
)

# =============================
# Composantes
# =============================

st.markdown("### Composantes de l’ancrage")

c1, c2 = st.columns(2)
c3, c4 = st.columns(2)
c5, _ = st.columns(2)

c1.metric("Empirie", result.get("real_anchor_E", 0))
c2.metric("Reproductibilité", result.get("real_anchor_R", 0))
c3.metric("Falsifiabilité", result.get("real_anchor_F", 0))
c4.metric("Limites", result.get("real_anchor_L", 0))
c5.metric("Spéculation", result.get("real_anchor_S", 0))

# =============================
# Delta réalité / mécroyance
# =============================

st.markdown("### Tension réalité / cohérence")

delta = result.get("delta_reality", 0)
delta_label = result.get("delta_reality_label", "Non calculé")
delta_text = result.get("delta_reality_interpretation", "")

if delta <= -5:
    delta_color = "#16a34a"

elif delta <= 2:
    delta_color = "#ca8a04"

else:
    delta_color = "#dc2626"

st.markdown(
    f"<b style='color:{delta_color}'>{delta_label}</b> — Δ = {delta}",
    unsafe_allow_html=True
)

st.caption(delta_text)

# =============================
# Marqueurs détectés
# =============================

with st.expander("Voir les marqueurs d’ancrage", expanded=False):

    st.write(
        "**Empirie :**",
        result.get("real_anchor_empirical_markers", [])
    )

    st.write(
        "**Reproductibilité :**",
        result.get("real_anchor_reproducibility_markers", [])
    )

    st.write(
        "**Falsifiabilité :**",
        result.get("real_anchor_falsifiability_markers", [])
    )

    st.write(
        "**Limites explicites :**",
        result.get("real_anchor_limits_markers", [])
    )

    st.write(
        "**Spéculation extrapolative :**",
        result.get("real_anchor_speculation_markers", [])
    )

st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

st.subheader(T["hard_fact_checking_by_claim"])
claims_df = pd.DataFrame(
    [
        {
            T["claim"]: c.text,
            "Type": ", ".join(c.claim_types),
            "Forme": c.aristotelian_type if c.aristotelian_type else "-",
            "Sujet": c.subject_term if c.subject_term else "-",
            "Prédicat": c.predicate_term if c.predicate_term else "-",
            T["status"]: c.status,
            f"{T['verifiability']} /20": c.verifiability,
            f"{T['risk']} /20": c.risk,
            "Ajustement": c.short_adjustment,
            "Note épistémique": c.epistemic_note,
            T["number"]: T["yes"] if c.has_number else T["no"],
            T["date"]: T["yes"] if c.has_date else T["no"],
            T["named_entity"]: T["yes"] if c.has_named_entity else T["no"],
            T["attributed_source"]: T["yes"] if c.has_source_cue else T["no"],
        }
        for c in result["claims"]
    ]
)

if not claims_df.empty:
    st.dataframe(claims_df, use_container_width=True, hide_index=True)
else:
    st.info(T["paste_longer_text"])
    
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

st.divider()
st.subheader("Analyse syllogistique")

if result.get("syllogisms"):
    for i, s in enumerate(result["syllogisms"], start=1):
        with st.expander(f"Syllogisme potentiel {i}", expanded=False):
            st.write(f"**Forme** : {s['form']}")
            st.write(f"**Terme moyen** : {s['middle_term'] if s['middle_term'] else '-'}")
            st.write(f"**Figure** : {s['figure'] if s['figure'] else '-'}")
            st.write(f"**Statut** : {s['status']}")

            st.write("**Prémisse 1**")
            st.write(s["premise_1"])
            if "p1_terms" in s:
                st.caption(f"Sujet : {s['p1_terms']['subject']} | Prédicat : {s['p1_terms']['predicate']}")

            st.write("**Prémisse 2**")
            st.write(s["premise_2"])
            if "p2_terms" in s:
                st.caption(f"Sujet : {s['p2_terms']['subject']} | Prédicat : {s['p2_terms']['predicate']}")

            st.write("**Conclusion**")
            st.write(s["conclusion"])
            if "c_terms" in s:
                st.caption(f"Sujet : {s['c_terms']['subject']} | Prédicat : {s['c_terms']['predicate']}")
else:
    st.info("Aucun syllogisme détecté.")

st.divider()

st.subheader("Enthymèmes détectés")

if result.get("enthymemes"):
    for i, e in enumerate(result["enthymemes"], start=1):
        with st.expander(f"Enthymème potentiel {i}", expanded=False):
            st.write(f"**Forme** : {e['form']}")
            st.write(f"**Sujet** : {e['subject']}")
            st.write(f"**Prédicat** : {e['predicate']}")
            st.write(f"**Statut** : {e['status']}")

            st.write("**Conclusion**")
            st.write(e["conclusion"])

            if e["context"]:
                st.write("**Contexte précédent**")
                for line in e["context"]:
                    st.write(f"- {line}")
else:
    st.info("Aucun enthymème détecté.")

st.divider()

st.subheader("Sophismes syllogistiques")

if result.get("fallacies"):
    for i, f in enumerate(result["fallacies"], start=1):
        with st.expander(f"Sophisme détecté {i}", expanded=False):
            st.write(f"**Type** : {f['type']}")
            st.write(f"**Description** : {f['description']}")

            s = f["syllogism"]

            st.write("**Prémisse 1**")
            st.write(s["premise_1"])

            st.write("**Prémisse 2**")
            st.write(s["premise_2"])

            st.write("**Conclusion**")
            st.write(s["conclusion"])
else:
    st.info("Aucun sophisme syllogistique détecté.")

st.divider()  
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

st.subheader(T["ai_module"])
st.caption(T["ai_module_caption"])

if client is None:
    st.warning(T["ai_unavailable"])
else:
    if st.button(T["generate_ai_analysis"], key="generate_ai_analysis"):
        with st.spinner("Analyse IA en cours..."):
            ai_summary = generate_ai_summary(article_for_analysis, result)
        st.subheader(T["ai_analysis_result"])
        st.markdown(ai_summary)

if st.session_state.get("article_source") == "paste":
    st.divider()
    st.subheader(T["external_corroboration_module"])
    st.caption(T["external_corroboration_caption"])
    with st.spinner(T["corroboration_in_progress"]):
        corroboration = corroborate_claims(article_for_analysis, max_claims=5, max_results_per_claim=3)
    if corroboration:
        for i, item in enumerate(corroboration, start=1):
            title_preview = item["claim"][:140] + ("..." if len(item["claim"]) > 140 else "")
            with st.expander(f"{T['claim']} {i} : {title_preview}", expanded=(i == 1)):
                st.markdown(f"**{T['corroboration_verdict']} :** {display_corroboration_verdict(item['verdict'])}")
                st.markdown(f"**{T['generated_query']} :** `{item['query']}`")
                if item["matches"]:
                    for match in item["matches"]:
                        st.markdown(f"**[{match['title']}]({match['url']})**")
                        st.markdown(
                            f"- **{T['match_score']}** : {match['match_score']['score']}\n"
                            f"- **{T['contradiction_signal']}** : {T['detected'] if match['match_score']['contradiction_signal'] else T['not_detected']}"
                        )
                        if match["snippet"]:
                            st.caption(match["snippet"])
                else:
                    st.warning(T["no_strong_sources_found"])
    else:
        st.info(T["no_corroboration_found"])
        
st.divider()        
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# -----------------------------
# Méthode
# -----------------------------
if show_method:

    st.subheader(T["method"])

    method_text = f"""
### {T['original_formula']}

`M = (G + N) - D`

- {T['articulated_knowledge_density']}
- {T['integration']}
- {T['assertive_rigidity']}

### {T['llm_metrics']}

- **{T['overconfidence']}** : `D - (G + N)`
- **{T['calibration']}** : `D / (G + N)`
- **{T['revisability']}** : `(G + N + V) - D`
- **{T['cognitive_closure']}** : `(D * S) / (G + N)`

{T['disclaimer']}
"""

    st.markdown(method_text)
st.divider()    
st.markdown("""
<div style="text-align:center; margin:25px 0; color:#888;">
──── 🧠 ────
</div>
""", unsafe_allow_html=True)

# -----------------------------
# Laboratoire interactif
# -----------------------------
st.divider()
st.subheader("Laboratoire interactif de la mécroyance")
st.caption(
    "Expérimentez la formule cognitive : M = (G + N) − D. "
    "Modifiez les paramètres pour observer l’évolution des stades cognitifs."
)

g_game = st.slider("G — gnōsis (savoir articulé)", 0.0, 10.0, 5.0, 0.5)
n_game = st.slider("N — nous (intégration vécue)", 0.0, 10.0, 5.0, 0.5)
d_game = st.slider("D — doxa (certitude / saturation)", 0.0, 10.0, 5.0, 0.5)

m_game = round((g_game + n_game) - d_game, 1)

st.markdown(
    f"""
    <div style="
        background:#f1f5f9;
        border-radius:14px;
        padding:18px;
        margin-top:10px;
        border:1px solid #dbe3ec;
        text-align:center;
        font-size:1.3rem;
        font-weight:700;
    ">
        M = ({g_game:.1f} + {n_game:.1f}) - {d_game:.1f}
        <span style="color:#0b6e4f;">{m_game:.1f}</span>
    </div>
    """,
    unsafe_allow_html=True,
)

if m_game < 0:
    stage = "Fermeture cognitive"
    explanation = "La certitude dépasse la compréhension : la pensée se verrouille."
    percent = 10
elif m_game <= 4:
    stage = "Enfance cognitive"
    explanation = "Structure cognitive naissante, encore fragile."
    percent = 25
elif m_game <= 10:
    stage = "Adolescence cognitive"
    explanation = "Cognition stable mais encore agitée."
    percent = 50
elif m_game <= 17:
    stage = "Maturité cognitive"
    explanation = "Équilibre entre savoir, expérience et doute."
    percent = 75
elif m_game < 19:
    stage = "Sagesse structurelle"
    explanation = "État rare d’équilibre cognitif."
    percent = 90
else:
    stage = "Asymptote de vérité"
    explanation = "Horizon théorique de cohérence maximale."
    percent = 100

st.markdown(f"**Stade actuel : {stage}**")
st.progress(percent / 100)
st.caption(f"M = {m_game} — {explanation}")

st.markdown("### Évolution cognitive")

stages = [
    ("Fermeture", -10, 0),
    ("Enfance", 0, 4.1),
    ("Adolescence", 4.1, 10.1),
    ("Maturité", 10.1, 17.1),
    ("Sagesse", 17.1, 19.1),
    ("Asymptote", 19.1, 21),
]

cols = st.columns(len(stages))
for i, (name, low, high) in enumerate(stages):
    active = low <= m_game < high
    with cols[i]:
        if active:
            st.success(name)
        else:
            st.info(name)

st.caption("Lorsque G et N augmentent sans inflation de D, la cognition gagne en revisabilité.")

# =============================
# Formulaire de feedback
# =============================

import os
from datetime import datetime
import pandas as pd

st.divider()
st.subheader("📩 Feedback")
st.caption("Signalez un bug, proposez une amélioration ou laissez un commentaire sur DOXA Detector.")

FEEDBACK_FILE = "feedback_doxa.csv"

with st.form("feedback_form"):
    feedback_type = st.selectbox(
        "Type de retour",
        ["Bug", "Suggestion", "Problème d'affichage", "Résultat incompris", "Autre"]
    )

    user_email = st.text_input(
        "Votre email — facultatif",
        placeholder="exemple@email.com"
    )

    message = st.text_area(
        "Votre message",
        placeholder="Décrivez le problème ou votre suggestion...",
        height=160
    )

    feedback_submitted = st.form_submit_button("Envoyer le feedback")

if feedback_submitted:
    if not message.strip():
        st.warning("Veuillez écrire un message avant d’envoyer.")
    else:
        new_feedback = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": feedback_type,
            "email": user_email.strip(),
            "message": message.strip()
        }

        if os.path.exists(FEEDBACK_FILE):
            df = pd.read_csv(FEEDBACK_FILE)
            df = pd.concat([df, pd.DataFrame([new_feedback])], ignore_index=True)
        else:
            df = pd.DataFrame([new_feedback])

        df.to_csv(FEEDBACK_FILE, index=False)

        st.success("Merci, votre feedback a bien été enregistré.")

# =============================
# Bloc admin (lecture feedbacks)
# =============================

st.divider()
st.subheader("🔒 Admin — Feedbacks reçus")

with st.expander("Afficher les feedbacks"):
    admin_code = st.text_input("Code admin", type="password")

    if admin_code == st.secrets.get("ADMIN_CODE", ""):
        if os.path.exists("feedback_doxa.csv"):
            import pandas as pd
            df = pd.read_csv("feedback_doxa.csv")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Aucun feedback enregistré.")
    elif admin_code:
        st.error("Code incorrect.")
