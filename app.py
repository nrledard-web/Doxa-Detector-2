import streamlit as st
import json
import re
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
div[data-testid="stProgressBar"] > div > div > div > div {
    height: 20px;
    border-radius: 8px;
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
    tri = Poly3DCollection(verts, alpha=0.18, edgecolor="black", linewidths=1.5)
    ax.add_collection3d(tri)

    ax.plot([G_pt[0], N_pt[0]], [G_pt[1], N_pt[1]], [G_pt[2], N_pt[2]], linewidth=2)
    ax.plot([N_pt[0], D_pt[0]], [N_pt[1], D_pt[1]], [N_pt[2], D_pt[2]], linewidth=2)
    ax.plot([D_pt[0], G_pt[0]], [D_pt[1], G_pt[1]], [D_pt[2], G_pt[2]], linewidth=2)

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
st.title("DOXA Detector")

with st.container(border=True):
    st.subheader("Analyser la fiabilité d’un texte")
    st.write(
        "DOXA Detector aide à comprendre si un texte repose sur des faits solides "
        "ou sur une rhétorique persuasive."
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### 1️⃣ Coller un texte")
        st.write("Copiez un article ou un extrait dans la zone d’analyse.")

    with col2:
        st.markdown("### 2️⃣ Analyser")
        st.write("L’application examine les sources, les affirmations et la nuance.")

    with col3:
        st.markdown("### 3️⃣ Comprendre")
        st.write("Obtenez un score de crédibilité et une analyse des affirmations.")

    st.caption(
        "Cet outil n’affirme pas si un texte est vrai ou faux : "
        "il aide simplement à mieux comprendre la solidité de l’information."
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

    vague_authority_terms = [
        "experts say", "sources say", "insiders say", "many specialists",
        "according to sources", "internal sources", "reports confirm",
        "les experts disent", "des sources affirment", "selon des sources",
        "des spécialistes", "des rapports confirment", "sources internes"
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
    absolute_claims = count_hits(absolute_claim_terms)
    vague_authority = count_hits(vague_authority_terms)
    dramatic_framing = count_hits(dramatic_framing_terms)
    nuance_hits = count_hits(nuance_terms)

    lack_of_nuance = 2 if nuance_hits == 0 else 1 if nuance_hits <= 2 else 0

    raw_score = (
        rhetorical_pressure
        + absolute_claims
        + vague_authority
        + dramatic_framing
        + lack_of_nuance
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

# -----------------------------
# Bibliothèques rhétoriques
# -----------------------------
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
MORALISATION_DISCOURS = [
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
        "moralisation_discours": MORALISATION_DISCOURS,
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
    Calcule une pression rhétorique pondérée entre 0.0 et 1.0
    à partir des catégories détectées.
    """
    weights = {
        "certitude": 1.2,
        "autorite": 1.0,
        "dramatisation": 1.3,
        "generalisation": 1.1,
        "naturalisation": 1.4,
        "ennemi": 1.5,
        "causalite": 1.4,
        "moralisation": 1.2,
    }

    weighted_score = 0.0

    for cat, count in results.items():
        weighted_score += count * weights.get(cat, 1.0)

    return min(weighted_score / 10, 1.0)


def interpret_rhetorical_pressure(value: float):
    """
    Traduit la pression rhétorique en étiquette + couleur.
    """
    if value < 0.20:
        return "Faible", "#16a34a"
    elif value < 0.40:
        return "Modérée", "#ca8a04"
    elif value < 0.70:
        return "Élevée", "#f97316"
    else:
        return "Très élevée", "#dc2626"
def compute_propaganda_gauge(
    lie_gauge: float,
    rhetorical_pressure: float,
    political_pattern_score: int,
    closure: float
) -> float:
    """
    Jauge propagandiste globale entre 0 et 1.
    Combine :
    - tension cognitive
    - pression rhétorique
    - motifs politiques/idéologiques détectés
    - fermeture cognitive
    """
    pattern_factor = min(political_pattern_score / 8, 1.0)
    closure_factor = min(closure / 1.2, 1.0)

    score = (
        0.30 * lie_gauge +
        0.35 * rhetorical_pressure +
        0.20 * pattern_factor +
        0.15 * closure_factor
    )

    return min(max(score, 0.0), 1.0)


def interpret_propaganda_gauge(value: float):
    """
    Traduit l'indice propagandiste en étiquette + couleur + commentaire.
    """
    if value < 0.20:
        return "Très faible", "#16a34a", "Le texte ne présente pas de structure propagandiste marquée."
    elif value < 0.40:
        return "Faible", "#84cc16", "Le discours peut orienter légèrement la perception, sans verrouillage fort."
    elif value < 0.60:
        return "Modéré", "#ca8a04", "Le texte contient plusieurs éléments compatibles avec une mise en orientation du lecteur."
    elif value < 0.80:
        return "Élevé", "#f97316", "Le discours semble fortement orienté et cherche à imposer un cadrage interprétatif."
    else:
        return "Très élevé", "#dc2626", "Le texte présente une structure fortement propagandiste ou de verrouillage idéologique."       

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
    elif propaganda_gauge >= 0.45 or rhetorical_pressure >= 0.45:
        return "Discours fortement orienté"
    elif lie_gauge < 0.40 and rhetorical_pressure < 0.35:
        return "Discours plutôt sincère ou peu verrouillant"
    else:
        return "Discours ambigu ou mixte"

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
        return article.text
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
        with DDGS() as ddgs:
            query = f"{keyword} actualité France"
            results = list(ddgs.text(query, max_results=max_results * 5))

            for r in results:
                url = r.get("href", "")
                title = r.get("title", "Sans titre")

                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)

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
    0.0 = mécroyance maximale
    0.5 = zone ambiguë / mixte
    1.0 = mensonge maximal
    """

    delta = ME - M
    amp = 8.0
    strength = min(abs(delta) / amp, 1.0)

    if delta <= 0:
        gauge = 0.5 * (1 - strength)

        if gauge > 0.35:
            label = "Mécroyance modérée"
            color = "#ca8a04"
        else:
            label = "Mécroyance forte"
            color = "#a16207"
    else:
        gauge = 0.5 + (0.5 * strength)

        if gauge < 0.65:
            label = "Mensonge possible"
            color = "#f97316"
        elif gauge < 0.85:
            label = "Mensonge probable"
            color = "#dc2626"
        else:
            label = "Mensonge extrême"
            color = "#991b1b"

    if gauge <= 0.5:
        intensity = (0.5 - gauge) / 0.5
    else:
        intensity = (gauge - 0.5) / 0.5

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


SOURCE_CUES = [
    "selon", "affirme", "déclare", "rapport", "étude", "expert",
    "source", "dit", "écrit", "publié", "annonce", "confirme", "révèle",
]

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
# Cohérence discursive / nouveaux modules
# -----------------------------
LOGICAL_CONNECTORS = [
    "car", "donc", "ainsi", "puisque", "parce que",
    "cependant", "pourtant", "toutefois", "néanmoins",
    "en effet", "or", "alors", "mais",
    "de plus", "en outre", "par conséquent", "dès lors"
]

DISCURSIVE_CONTRADICTION_PATTERNS = [
    r"\btoujours\b.*\bjamais\b",
    r"\bjamais\b.*\btoujours\b",
    r"\btout\b.*\bsauf\b",
    r"\brien\b.*\bmais\b",
    r"\baucun\b.*\bmais\b",
    r"\bobligatoire\b.*\bfacultatif\b",
    r"\bimpossible\b.*\bpossible\b"
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
        "according to studies", "science proves", "research shows"
    ],
    "technicite_rhetorique": [
        "système", "structure", "dynamique", "modèle",
        "mécanisme", "processus", "paradigme",
        "system", "structure", "dynamics", "model", "mechanism", "process"
    ],
    "chiffres_sans_source": [
        "pour cent",
        "une étude récente",
        "plusieurs recherches",
        "des statistiques montrent",
        "recent study",
        "statistics show"
    ]
}

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
        return {"score": 0.0, "details": {}, "markers": [], "interpretation": "Aucune prémisse implicite détectée."}

    t = text.lower()
    score = 0
    details = {}
    markers = []

    for category, terms in IMPLICIT_PREMISE_MARKERS.items():
        hits = [term for term in terms if contains_term(t, term)]
        details[category] = len(hits)
        markers.extend(hits)
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
    "therefore",
    "this proves that",
    "this shows that",
    "this leads to",
    "which explains",
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
    "according to experts",
    "experts say",
    "studies show",
    "research suggests",
    "scientific consensus",
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
    "la preuve que"
]

EMOTIONAL_INTENSITY_TERMS = [
    "scandale",
    "honte",
    "catastrophe",
    "désastre",
    "trahison",
    "danger",
    "peur",
    "menace",
    "crise",
    "urgent",
    "incroyable",
    "terrible",
    "révolution",
    "effondrement",
    "panique",
    "massacre",
    "destruction",
    "panic",
    "scandal",
    "outrage",
    "fear",
    "collapse",
    "crisis",
    "urgent",
]
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
    "ceux qui sont contre nous"
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
]

def detect_semantic_shift(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucun glissement sémantique détecté."
        }

    text_lower = text.lower()

    markers = unique_keep_order(
        [w for w in SEMANTIC_SHIFT_MARKERS if contains_term(text_lower, w)]
    )

    score = clamp(len(markers) * 2, 0, 20)

    if score < 5:
        interpretation = "Peu de glissements sémantiques détectés."
    elif score < 10:
        interpretation = "Quelques recadrages lexicaux sont présents."
    else:
        interpretation = "Le texte utilise plusieurs recadrages lexicaux stratégiques."

    return {
        "score": round(score / 20, 3),
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


def detect_ideological_premises(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune prémisse implicite détectée."
        }

    t = text.lower()

    hits = unique_keep_order(
        [m for m in IDEOLOGICAL_PREMISE_MARKERS if contains_term(t, m)]
    )

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


def compute_emotional_intensity(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune charge émotionnelle saillante détectée."
        }

    t = text.lower()
    hits = unique_keep_order([term for term in EMOTIONAL_INTENSITY_TERMS if contains_term(t, term)])
    score = min(len(hits) * 2.2 / 10, 1.0)

    if score < 0.15:
        interpretation = "Le texte reste peu chargé émotionnellement."
    elif score < 0.35:
        interpretation = "Le texte contient quelques marqueurs émotionnels."
    elif score < 0.60:
        interpretation = "Le texte mobilise une charge émotionnelle notable."
    else:
        interpretation = "Le texte repose fortement sur une intensité émotionnelle orientant la lecture."

    return {
        "score": round(score, 3),
        "markers": hits,
        "interpretation": interpretation,
    }

def compute_generalization(text: str):

    text_lower = text.lower()

    hits = [t for t in GENERALIZATION_TERMS if t in text_lower]

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

    hits = [t for t in ABSTRACT_ENEMY_TERMS if t in text_lower]

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

    hits = [t for t in CERTAINTY_TERMS if t in text_lower]

    score = min(len(hits) * 2.5 / 10, 1.0)

    if score < 0.2:
        interpretation = "Discours relativement nuancé."
    elif score < 0.5:
        interpretation = "Certitude rhétorique modérée."
    else:
        interpretation = "Certitude absolue fortement affirmée."

    return score, interpretation, hits

def compute_false_consensus(text: str):
    text_lower = text.lower()

    hits = [t for t in CONSENSUS_TERMS if contains_term(text_lower, t)]

    score = min(len(hits) * 2.5 / 10, 1.0)

    if score < 0.15:
        interpretation = "Aucun faux consensus significatif détecté."
    elif score < 0.35:
        interpretation = "Le texte suggère légèrement une adhésion collective implicite."
    elif score < 0.60:
        interpretation = "Le texte met en scène un consensus supposé."
    else:
        interpretation = "Le texte s'appuie fortement sur un faux consensus rhétorique."

    return score, interpretation, hits


def compute_binary_opposition(text: str):
    text_lower = text.lower()

    hits = [t for t in BINARY_OPPOSITION_TERMS if contains_term(text_lower, t)]

    score = min(len(hits) * 3 / 10, 1.0)

    if score < 0.15:
        interpretation = "Aucune opposition binaire significative détectée."
    elif score < 0.35:
        interpretation = "Tendance légère à structurer le discours en camps opposés."
    elif score < 0.60:
        interpretation = "Opposition binaire marquée entre groupes."
    else:
        interpretation = "Discours fortement structuré en camps antagonistes."

    return score, interpretation, hits


THREAT_AMPLIFICATION_TERMS = [
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
]

def compute_threat_amplification(text: str):
    text_lower = text.lower()

    hits = [t for t in THREAT_AMPLIFICATION_TERMS if contains_term(text_lower, t)]

    score = min(len(hits) * 3 / 10, 1.0)

    if score < 0.15:
        interpretation = "Aucune amplification de menace significative détectée."
    elif score < 0.35:
        interpretation = "Le texte contient quelques formulations alarmistes."
    elif score < 0.60:
        interpretation = "Le texte amplifie notablement la perception de menace."
    else:
        interpretation = "Le discours repose fortement sur une amplification dramatique de la menace."

    return score, interpretation, hits


# -----------------------------
# 19) Fausse analogie
# -----------------------------
FALSE_ANALOGY_TERMS = [
    "comme si", "c'est comme", "de la même manière que",
    "exactement comme", "rien de différent de",
    "comparable à", "similaire à", "équivalent à",
    "just like", "exactly like", "similar to", "equivalent to"
]

def compute_false_analogy(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune fausse analogie saillante détectée."
        }

    text_lower = text.lower()
    hits = [t for t in FALSE_ANALOGY_TERMS if contains_term(text_lower, t)]
    score = min(len(hits) * 2.5 / 10, 1.0)

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
    hits = [t for t in FACTUAL_OVERINTERPRETATION_TERMS if contains_term(text_lower, t)]
    score = min(len(hits) * 2.5 / 10, 1.0)

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
        "markers": hits,
        "interpretation": interpretation,
    }


# -----------------------------
# 21) Dissonance interne
# -----------------------------
INTERNAL_DISSONANCE_PATTERNS = [
    r"\bil n'y a pas de preuve\b.*\bc'est certain\b",
    r"\bon ne sait pas\b.*\bil est évident\b",
    r"\bjamais\b.*\btoujours\b",
    r"\btoujours\b.*\bjamais\b",
    r"\baucun\b.*\btous\b",
    r"\btous\b.*\baucun\b",
    r"\bimpossible\b.*\bpossible\b",
    r"\bpossible\b.*\bimpossible\b",
]

def compute_internal_dissonance(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune dissonance interne saillante détectée."
        }

    text_lower = text.lower()
    hits = []

    for pattern in INTERNAL_DISSONANCE_PATTERNS:
        if re.search(pattern, text_lower, flags=re.DOTALL):
            hits.append(pattern)

    score = min(len(hits) * 3 / 10, 1.0)

    if score < 0.15:
        interpretation = "Peu de contradictions internes détectées."
    elif score < 0.35:
        interpretation = "Le texte contient quelques tensions internes."
    elif score < 0.60:
        interpretation = "Le texte présente plusieurs contradictions ou incohérences."
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
    "scandalous", "unacceptable", "shameful", "immoral", "criminal"
]

def compute_normative_saturation(text: str):
    if not text or not text.strip():
        return {
            "score": 0.0,
            "markers": [],
            "interpretation": "Aucune saturation normative saillante détectée."
        }

    text_lower = text.lower()
    hits = [t for t in SATURATION_NORMATIVE_TERMS if contains_term(text_lower, t)]
    score = min(len(hits) * 2.2 / 10, 1.0)

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

    absolutism = sum(1 for word in ABSOLUTIST_WORDS if word in s)
    emotional_charge = sum(1 for word in EMOTIONAL_WORDS if word in s)

    # Vérifiabilité brute
    v_score = clamp(
        (has_number * 5) +
        (has_date * 5) +
        (has_named_entity * 5) +
        (has_source_cue * 5),
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

    v_score = clamp(v_score - normative_penalty, 0, 20)

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
    )

def analyze_article(text: str) -> Dict:
    words = text.split()
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 10]
    article_length = len(words)

    source_markers = len(re.findall(r"|".join(re.escape(c) for c in SOURCE_CUES), text.lower()))
    citation_like = len(re.findall(r'"|\'|«|»', text))
    nuance_markers = len(re.findall(r"|".join(re.escape(c) for c in NUANCE_MARKERS), text.lower()))

    G = clamp(source_markers * 1.5 + citation_like * 0.5, 0, 10)
    N = clamp(nuance_markers * 2 + (article_length / 100), 0, 10)

    normative_analysis = detect_normative_charges(text)
    discursive_analysis = compute_discursive_coherence(text)
    premise_analysis = compute_implicit_premises(text)
    logic_confusion_analysis = compute_logic_confusion(text)
    scientific_simulation_analysis = compute_scientific_simulation(text)
    propaganda_analysis = detect_propaganda_narrative(text)
    short_form_analysis = detect_short_form_mode(text)
    causal_overreach_analysis = compute_causal_overreach(text)
    vague_authority_analysis = compute_vague_authority(text)
    emotional_intensity_analysis = compute_emotional_intensity(text)
    generalization_analysis = compute_generalization(text)
    abstract_enemy_analysis = compute_abstract_enemy(text)
    certainty_analysis = compute_certainty(text)
    false_consensus_analysis = compute_false_consensus(text)
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

    certainty = len(re.findall(r"certain|absolument|prouvé|évident|incontestable", text.lower()))
    emotional = len(re.findall(r"|".join(re.escape(w) for w in EMOTIONAL_WORDS), text.lower()))

    D = clamp(certainty * 2 + emotional * 1.5, 0, 10)
    M = round((G + N) - D, 1)
    V = clamp(G * 0.8 + N * 0.2, 0, 10)
    R = clamp(D * 0.7 + (emotional * 1.2), 0, 10)
    improved = round((G + N + V) - (D + R), 1)

    claims = [analyze_claim(s) for s in sentences[:15]]
    avg_claim_verifiability = sum(c.verifiability for c in claims) / len(claims) if claims else 0
    avg_claim_risk = sum(c.risk for c in claims) / len(claims) if claims else 0
    source_quality = clamp(source_markers * 3 - (emotional * 2), 0, 20)

    red_flags = []
    if D > 8:
        red_flags.append("Doxa saturée")
    if emotional > 5:
        red_flags.append("Pathos excessif")
    if G < 2:
        red_flags.append("Désert documentaire")
    if article_length < 50:
        red_flags.append("Format indigent")

    hard_fact_score_raw = (
        (0.18 * G + 0.12 * N + 0.20 * V + 0.22 * source_quality + 0.18 * avg_claim_verifiability)
        - (0.16 * D + 0.12 * R + 0.18 * avg_claim_risk + 0.9 * len(red_flags))
    )
    hard_fact_score = round(clamp(hard_fact_score_raw + 8, 0, 20), 1)

    if hard_fact_score < 6:
        verdict = T["low_credibility"]
    elif hard_fact_score < 10:
        verdict = T["prudent_credibility"]
    elif hard_fact_score < 15:
        verdict = T["rather_credible"]
    else:
        verdict = T["strong_credibility"]

    if short_form_analysis["is_short_form"]:
        hard_fact_score = round(clamp(hard_fact_score - 1.5, 0, 20), 1)
    if hard_fact_score < 6:
        verdict = T["low_credibility"]
    elif hard_fact_score < 10:
        verdict = T["prudent_credibility"]
    elif hard_fact_score < 15:
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

    political_pattern_score, political_results, matched_terms = detect_political_patterns(text)
    rhetorical_pressure = compute_rhetorical_pressure(political_results)

    ME_base = max(0, (2 * D) - (G + N))

    discursive_boost = (
        normative_analysis["score"] * 2.0 +
        premise_analysis["score"] * 1.5 +
        logic_confusion_analysis["score"] * 1.5 +
        scientific_simulation_analysis["score"] * 1.2 +
        propaganda_analysis["score"] * 2.5
    )

    ME = round((ME_base * L) + discursive_boost, 2)

    return {
        "words": len(words),
        "sentences": len(sentences),
        "G": G,
        "N": N,
        "D": D,
        "M": M,
        "ME_base": ME_base,
        "ME": ME,
        "L": L,
        "normative_score": normative_analysis["score"],
        "normative_terms": normative_analysis["normative_terms"],
        "normative_judgment_markers": normative_analysis["judgment_markers"],
        "normative_interpretation": normative_analysis["interpretation"],
        
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

                "ideological_premise_score": ideological_premise_analysis["score"],
        "ideological_premise_markers": ideological_premise_analysis["markers"],
        "ideological_premise_interpretation": ideological_premise_analysis["interpretation"],

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

        "propaganda_score": propaganda_analysis["score"],
        "propaganda_enemy_terms": propaganda_analysis["enemy_terms"],
        "propaganda_urgency_terms": propaganda_analysis["urgency_terms"],
        "propaganda_certainty_terms": propaganda_analysis["certainty_terms"],
        "propaganda_emotional_terms": propaganda_analysis["emotional_terms"],
        "propaganda_interpretation": propaganda_analysis["interpretation"],

        "linguistic_trigger_count": ling["trigger_count"],
        "linguistic_pressure_hits": ling["rhetorical_pressure"],
        "absolute_claims": ling["absolute_claims"],
        "vague_authority": ling["vague_authority"],
        "dramatic_framing": ling["dramatic_framing"],
        "lack_of_nuance": ling["lack_of_nuance"],
        "political_pattern_score": political_pattern_score,
        "political_results": political_results,
        "matched_terms": matched_terms,
        "rhetorical_pressure": rhetorical_pressure,
        "V": V,
        "R": R,
        "improved": improved,
        "source_quality": source_quality,
        "avg_claim_risk": avg_claim_risk,
        "avg_claim_verifiability": avg_claim_verifiability,
        "hard_fact_score": hard_fact_score,
        "verdict": verdict,
        "profil_solidite": verdict,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "claims": claims,
        "red_flags": red_flags,
    }


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
                filtered = sorted(filtered, key=lambda x: x["match_score"]["score"], reverse=True)[:max_results_per_claim]
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
            if len(full_text) > 120:
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
        except Exception:
            continue

    return results   
    
@st.cache_data(show_spinner=False, ttl=1800)
def fetch_text_for_textarea(url: str) -> str:
    try:
        text = extract_article_from_url(url)
        return (text or "").strip()
    except Exception:
        return ""

# -----------------------------
# Réglages
# -----------------------------
with st.expander(T["settings"], expanded=False):
    use_sample = st.button(T["load_example"])
    show_method = st.toggle(T["show_method"], value=True)
    st.divider()
    st.subheader(T["hard_fact_score_scale"])
    st.markdown(
        f"- **0–5** : {T['scale_0_5']}\n"
        f"- **6–9** : {T['scale_6_9']}\n"
        f"- **10–14** : {T['scale_10_14']}\n"
        f"- **15–20** : {T['scale_15_20']}"
    )

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
st.subheader(T["topic_section"])
keyword = st.text_input(T["topic"], placeholder=T["topic_placeholder"])

if st.button(T["analyze_topic"], key="analyze_topic"):
    if keyword.strip():
        st.info(T["searching"])
        st.session_state.multi_results = analyze_multiple_articles(keyword.strip(), max_results=10)
        st.session_state.last_keyword = keyword.strip()
    else:
        st.session_state.multi_results = []
        st.warning(T["enter_keyword_first"])

if st.session_state.get("multi_results"):
    df_multi = pd.DataFrame(st.session_state.multi_results).sort_values("Hard Fact Score", ascending=False)

    st.success(f"{len(df_multi)} {T['articles_analyzed']}")

    c1, c2 = st.columns(2)
    c1.metric(T["analyzed_articles"], len(df_multi))
    c2.metric(T["avg_hard_fact"], round(df_multi["Hard Fact Score"].mean(), 1))
    st.metric(T["avg_classic_score"], round(df_multi["Score classique"].mean(), 1))

    ecart_type_hf = df_multi["Hard Fact Score"].std()
    indice_doxa = "high" if ecart_type_hf < 1.5 else ("medium" if ecart_type_hf < 3 else "low")
    st.metric(T["topic_doxa_index"], T[indice_doxa])

    st.subheader(T["credibility_score_dispersion"])
    df_plot = df_multi.copy()
    df_plot["Article"] = [f"{T['article_label']} {i+1}" for i in range(len(df_plot))]
    st.bar_chart(df_plot.set_index("Article")["Hard Fact Score"])
    st.dataframe(df_multi, use_container_width=True, hide_index=True)

    st.markdown("### Actions sur les articles trouvés")

    for i, row in df_multi.reset_index(drop=True).iterrows():
        with st.container(border=True):
            st.markdown(f"### {row['Titre']}")
            st.caption(f"{row['Source']}")

            score = row["Hard Fact Score"]
            if score <= 6:
                color, label = "🔴", "Fragile"
            elif score <= 11:
                color, label = "🟠", "Douteux"
            elif score <= 15:
                color, label = "🟡", "Plausible"
            else:
                color, label = "🟢", "Robuste"

            st.markdown(f"**{color} Score de crédibilité : {score:.1f}/20 — {label}**")
            st.progress(score / 20)

            col1, col2 = st.columns(2)
            with col1:
                st.link_button("🌐 Ouvrir l'article", row["URL"], use_container_width=True)
            with col2:
                if st.button(f"📥 Charger pour analyse", key=f"load_article_{i}"):
                    loaded_text = fetch_text_for_textarea(row["URL"])
                    if loaded_text:
                        st.session_state.article = loaded_text
                        st.session_state.article_source = "url"
                        st.session_state.loaded_url = row["URL"]
                        st.success("Article chargé dans la zone de texte.")
                        st.rerun()
                    else:
                        st.warning("Impossible d'extraire le texte.")
elif st.session_state.get("last_keyword"):
    st.warning(T["no_exploitable_articles_found"])


# -----------------------------
# Chargement URL
# -----------------------------
with st.form("url_form"):
    url = st.text_input(T["url"])
    load_url_submitted = st.form_submit_button(T["load_url"])

if load_url_submitted:
    if url:
        texte = extract_article_from_url(url)
        if texte:
            st.session_state.article = texte
            st.session_state.article_source = "url"
            st.session_state.loaded_url = url
            st.success(T["article_loaded_from_url"])
            st.rerun()
        else:
            st.error(T["unable_to_retrieve_text"])
    else:
        st.warning(T["paste_url_first"])


# -----------------------------
# Zone d’analyse
# -----------------------------
previous_article = st.session_state.article

st.markdown("### Zone d’analyse")

with st.container(border=True):
    st.caption("Collez un texte, chargez une URL, ou dictez directement.")

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
            st.session_state.article = spoken_text
            st.session_state.article_source = "paste"
            st.success("Texte dicté reçu.")
            st.rerun()
    else:
        st.info("Microphone indisponible sur cette version.")

    with st.form("article_form"):
        article = st.text_area(
            T["paste"],
            key="article",
            height=220,
            label_visibility="collapsed",
            placeholder=T["paste"]
        )
        analyze_submitted = st.form_submit_button(T["analyze"], use_container_width=True)

if article.strip() != previous_article.strip():
    st.session_state.article_source = "paste"

source_label = T["manual_paste"] if st.session_state.get("article_source") == "paste" else T["loaded_url_source"]
st.caption(f"{T['text_source']} : {source_label}")

if st.session_state.get("loaded_url"):
    st.caption(f"URL : {st.session_state.loaded_url}")


# -----------------------------
# Analyse principale
# -----------------------------
if analyze_submitted:
    st.session_state.last_result = analyze_article(article)
    st.session_state.last_article = article

result = st.session_state.last_result
article_for_analysis = st.session_state.last_article

if result:
    col1, col2, col3 = st.columns(3)
    col1.metric(T["classic_score"], result["M"], help=T["help_classic_score"])
    col2.metric(T["improved_score"], result["improved"], help=T["help_improved_score"])
    col3.metric(T["hard_fact_score"], result["hard_fact_score"], help=T["help_hard_fact_score"])

    score = result["hard_fact_score"]
    if score <= 6:
        couleur, etiquette, message = "🔴", T["fragile"], T["fragile_message"]
    elif score <= 11:
        couleur, etiquette, message = "🟠", T["doubtful"], T["doubtful_message"]
    elif score <= 15:
        couleur, etiquette, message = "🟡", T["plausible"], T["plausible_message"]
    else:
        couleur, etiquette, message = "🟢", T["robust"], T["robust_message"]

    st.subheader(f"{couleur} {T['credibility_gauge']} : {etiquette}")
    st.progress(score / 20)
    st.caption(f"{T['score']} : {score}/20 — {message}")
    
    if result.get("short_form_mode"):
        st.info(f"{result['short_form_label']} — {result['short_form_interpretation']}")
        
    st.caption("Sur cette échelle, un texte véritablement crédible se situe généralement dans la zone robuste.")

    st.subheader("Diagnostic cognitif")
    life_score = round((result["hard_fact_score"] / 20) * 100, 1)
    mecroyance_bar = max(0.0, min(1.0, (result["M"] + 10) / 30))

    col1, col2 = st.columns(2)
    with col1:
        st.write("Vitalité cognitive")
        st.progress(life_score / 100)
        st.caption(f"{life_score}%")
    with col2:
        st.write("Indice de mécroyance")
        st.progress(mecroyance_bar)
        st.caption(f"M = {result['M']}")

    st.subheader(f"{T['verdict']} : {result['verdict']}")
    st.subheader(T["summary"])

    m1, m2 = st.columns(2)
    m1.metric("G — gnōsis", result["G"])
    m2.metric("N — nous", result["N"])
    m3, m4 = st.columns(2)
    m3.metric("D — doxa", result["D"])
    m4.metric("V — vérifiabilité", result["V"])
    m5, m6 = st.columns(2)
    m5.metric("QS", result["source_quality"])
    m6.metric("RC", round(result["avg_claim_risk"], 1))
    m7, m8 = st.columns(2)
    m7.metric("VC", round(result["avg_claim_verifiability"], 1))
    m8.metric("F", len(result["red_flags"]))

    st.divider()
    st.subheader("Triangle cognitif G-N-D")
    st.caption("Le texte est placé dans l’espace de la cognition : savoir articulé, compréhension intégrée, et certitude assertive.")
    fig_triangle = plot_cognitive_triangle_3d(result["G"], result["N"], result["D"])
    st.pyplot(fig_triangle, use_container_width=True)

    st.subheader("Métriques cognitives")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Indice de mécroyance (M)", round(result["M"], 2))
    with col2:
        st.metric("Indice de mensonge (ME)", round(result["ME"], 2))

    delta_mm = round(result["M"] - result["ME"], 2)
    st.caption(f"Écart cognitif (M − ME) : {delta_mm}")

    if result["M"] > result["ME"] + 1:
        dominant_pattern = "Structure dominante : mécroyance"
    elif result["ME"] > result["M"] + 1:
        dominant_pattern = "Structure dominante : mensonge stratégique"
    else:
        dominant_pattern = "Structure dominante : mixte ou ambiguë"

    st.subheader("Structure cognitive dominante")
    st.write(dominant_pattern)

    if result["ME"] > result["M"] and result["ME"] > 0:
        cognitive_type = "Mensonge stratégique possible"
    elif result["M"] < 0:
        cognitive_type = "Forte mécroyance / clôture cognitive"
    else:
        cognitive_type = "Cognition probablement sincère mais désalignée"

    st.subheader("Interprétation cognitive")
    st.write(cognitive_type)

    if result["M"] - result["ME"] > 3:
        diagnosis = "Structure de mécroyance forte"
    elif result["M"] > result["ME"]:
        diagnosis = "Structure de mécroyance modérée"
    elif abs(result["M"] - result["ME"]) <= 1:
        diagnosis = "Structure cognitive ambiguë"
    else:
        diagnosis = "Tromperie stratégique possible"

    st.subheader("Diagnostic cognitif")
    st.write(diagnosis)

    lie_result = compute_lie_gauge(result["M"], result["ME"])

    gauge_value = lie_result["gauge"]
    gauge_label = lie_result["label"]
    gauge_color = lie_result["color"]
    ME_gauge = lie_result["ME"]
    gauge_intensity = lie_result["intensity"]

    st.write("Tension cognitive (mécroyance vs mensonge)")
    st.caption(
        "Cette jauge indique si le discours relève plutôt d’une erreur sincère "
        "(mécroyance) ou d’une possible manipulation. "
        "Plus la jauge progresse, plus la structure du texte se rapproche du mensonge."
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

    st.divider()
    st.subheader("Jauge de pression rhétorique")
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

    st.divider()
    st.subheader("Jauge propagandiste")
    st.caption(
        "Cette jauge combine la tension cognitive, la pression rhétorique, "
        "les motifs idéologiques détectés et le degré de fermeture cognitive. "
        "Elle aide à estimer si le texte relève d’un simple discours orienté "
        "ou d’une structure plus franchement propagandiste."
    )

    closure_for_discourse = (
        (result["D"] * (1 + len(result["red_flags"]) / 5)) / (result["G"] + result["N"])
        if (result["G"] + result["N"]) > 0 else 10
    )

    propaganda_value = compute_propaganda_gauge(
        lie_gauge=gauge_value,
        rhetorical_pressure=rp,
        political_pattern_score=result["political_pattern_score"],
        closure=closure_for_discourse
    )

    propaganda_label, propaganda_color, propaganda_text = interpret_propaganda_gauge(propaganda_value)

    render_custom_gauge(propaganda_value, propaganda_color)

    st.markdown(
        f"<b style='color:{propaganda_color}'>{propaganda_label}</b> — {round(propaganda_value*100, 1)}%",
        unsafe_allow_html=True
    )

    st.caption("Discours peu orienté ⟵⟶ Structure propagandiste")
    st.caption(propaganda_text)

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

    st.divider()
    st.subheader("Cartographie discursive complémentaire")
    st.caption(
        "Ces vingt-quatre jauges affinent l’analyse en distinguant les jugements de valeur, "
        "les prémisses implicites, la narration propagandiste, la cohérence discursive, "
        "les confusions logiques, la scientificité rhétorique, la fausse causalité, "
        "l’autorité vague, la charge émotionnelle, la généralisation abusive, "
        "l’ennemi abstrait, la certitude absolue, le faux consensus, l’opposition binaire, "
        "l’amplification de menace, le glissement sémantique, les prémisses idéologiques, "
        "la clôture cognitive, la fausse analogie, la surinterprétation factuelle, "
        "la dissonance interne, la saturation normative, la rigidité doxique "
        "et la surdétermination narrative."
    )

    row1_col1, row1_col2, row1_col3 = st.columns(3)
    row2_col1, row2_col2, row2_col3 = st.columns(3)
    row3_col1, row3_col2, row3_col3 = st.columns(3)
    row4_col1, row4_col2, row4_col3 = st.columns(3)
    row5_col1, row5_col2, row5_col3 = st.columns(3)
    row6_col1, row6_col2, row6_col3 = st.columns(3)
    row7_col1, row7_col2, row7_col3 = st.columns(3)
    row8_col1, row8_col2, row8_col3 = st.columns(3)
    

    # -----------------------------
    # 1) Qualifications normatives
    # -----------------------------
    with row1_col1:
        st.markdown("### Qualification normative")
        st.caption("Jugements de valeur présentés comme des faits.")

        normative_value = result["normative_score"]

        if normative_value < 0.20:
            normative_label, normative_color = "Faible", "#16a34a"
        elif normative_value < 0.40:
            normative_label, normative_color = "Modérée", "#ca8a04"
        elif normative_value < 0.70:
            normative_label, normative_color = "Élevée", "#f97316"
        else:
            normative_label, normative_color = "Très élevée", "#dc2626"

        render_custom_gauge(normative_value, normative_color)

        st.markdown(
            f"<b style='color:{normative_color}'>{normative_label}</b> — {round(normative_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["normative_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
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

    # -----------------------------
    # 2) Prémisses idéologiques implicites
    # -----------------------------
    with row1_col2:
        st.markdown("### Prémisses implicites")
        st.caption("Idées présentées comme évidentes sans démonstration.")

        premise_value = result["premise_score"]

        if premise_value < 0.20:
            premise_label, premise_color = "Faible", "#16a34a"
        elif premise_value < 0.40:
            premise_label, premise_color = "Modérée", "#ca8a04"
        elif premise_value < 0.70:
            premise_label, premise_color = "Élevée", "#f97316"
        else:
            premise_label, premise_color = "Très élevée", "#dc2626"

        render_custom_gauge(premise_value, premise_color)

        st.markdown(
            f"<b style='color:{premise_color}'>{premise_label}</b> — {round(premise_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["premise_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            premise_markers = result.get("premise_markers", [])

            if not premise_markers:
                st.info("Aucune prémisse implicite saillante détectée.")
            else:
                for marker in premise_markers:
                    st.warning(marker)

    # -----------------------------
    # 3) Propagande narrative
    # -----------------------------
    with row1_col3:
        st.markdown("### Narration propagandiste")
        st.caption("Urgence, ennemi abstrait, certitude et charge émotionnelle.")

        propaganda_value = result["propaganda_score"]

        if propaganda_value < 0.20:
            propaganda_label, propaganda_color = "Faible", "#16a34a"
        elif propaganda_value < 0.40:
            propaganda_label, propaganda_color = "Modérée", "#ca8a04"
        elif propaganda_value < 0.70:
            propaganda_label, propaganda_color = "Élevée", "#f97316"
        else:
            propaganda_label, propaganda_color = "Très élevée", "#dc2626"

        render_custom_gauge(propaganda_value, propaganda_color)

        st.markdown(
            f"<b style='color:{propaganda_color}'>{propaganda_label}</b> — {round(propaganda_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["propaganda_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
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

        # -----------------------------
    # 4) Cohérence discursive
    # -----------------------------
    with row2_col1:
        st.markdown("### Cohérence discursive")
        st.caption("Solidité interne du texte, indépendamment de sa vérifiabilité.")

        coherence_value = result["discursive_coherence_score"] / 20

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
            f"<b style='color:{coherence_color}'>{coherence_label}</b> — {result['discursive_coherence_score']}/20",
            unsafe_allow_html=True
        )
        st.caption(result["discursive_coherence_label"])

        with st.expander("Voir le détail", expanded=False):
            d = result["discursive_coherence_details"]
            st.write(f"**Logique discursive** : {d['logic_score']}/5")
            st.write(f"**Stabilité thématique** : {d['stability_score']}/4")
            st.write(f"**Longueur utile** : {d['length_score']}/5")
            st.write(f"**Cohérence entre paragraphes** : {d['paragraph_score']}/4")
            st.write(f"**Pénalité de contradiction** : -{d['contradiction_penalty']}")
            st.write(f"**Pénalité de rupture thématique** : -{d['topic_shift_penalty']}")
            if d["top_keywords"]:
                st.write("**Mots-clés dominants**")
                for word, count in d["top_keywords"]:
                    st.write(f"- {word} ({count})")

    # -----------------------------
    # 5) Confusion logique
    # -----------------------------
    with row2_col2:
        st.markdown("### Confusion logique")
        st.caption("Causalité abusive, extrapolation, prédiction absolue.")

        logic_value = result["logic_confusion_score"]

        if logic_value < 0.20:
            logic_label, logic_color = "Faible", "#16a34a"
        elif logic_value < 0.40:
            logic_label, logic_color = "Modérée", "#ca8a04"
        elif logic_value < 0.70:
            logic_label, logic_color = "Élevée", "#f97316"
        else:
            logic_label, logic_color = "Très élevée", "#dc2626"

        render_custom_gauge(logic_value, logic_color)

        st.markdown(
            f"<b style='color:{logic_color}'>{logic_label}</b> — {round(logic_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["logic_confusion_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("logic_confusion_markers", [])
            if not markers:
                st.info("Aucune confusion logique saillante détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 6) Scientificité rhétorique
    # -----------------------------
    with row2_col3:
        st.markdown("### Scientificité rhétorique")
        st.caption("Simulation d’objectivité scientifique sans base identifiable.")

        sim_value = result["scientific_simulation_score"]

        if sim_value < 0.20:
            sim_label, sim_color = "Faible", "#16a34a"
        elif sim_value < 0.40:
            sim_label, sim_color = "Modérée", "#ca8a04"
        elif sim_value < 0.70:
            sim_label, sim_color = "Élevée", "#f97316"
        else:
            sim_label, sim_color = "Très élevée", "#dc2626"

        render_custom_gauge(sim_value, sim_color)

        st.markdown(
            f"<b style='color:{sim_color}'>{sim_label}</b> — {round(sim_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["scientific_simulation_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("scientific_simulation_markers", [])
            if not markers:
                st.info("Aucun marqueur de scientificité rhétorique détecté.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 7) Fausse causalité
    # -----------------------------
    with row3_col1:
        st.markdown("### Fausse causalité")
        st.caption("Liens causaux affirmés plus vite qu'ils ne sont démontrés.")

        causal_value = result["causal_overreach_score"]

        if causal_value < 0.20:
            causal_label, causal_color = "Faible", "#16a34a"
        elif causal_value < 0.40:
            causal_label, causal_color = "Modérée", "#ca8a04"
        elif causal_value < 0.70:
            causal_label, causal_color = "Élevée", "#f97316"
        else:
            causal_label, causal_color = "Très élevée", "#dc2626"

        render_custom_gauge(causal_value, causal_color)

        st.markdown(
            f"<b style='color:{causal_color}'>{causal_label}</b> — {round(causal_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["causal_overreach_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("causal_overreach_markers", [])
            if not markers:
                st.info("Aucun marqueur de causalité abusive détecté.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 8) Autorité vague
    # -----------------------------
    with row3_col2:
        st.markdown("### Autorité vague")
        st.caption("Appels à des experts, études ou spécialistes sans source précise.")

        vague_auth_value = result["vague_authority_score"]

        if vague_auth_value < 0.20:
            vague_auth_label, vague_auth_color = "Faible", "#16a34a"
        elif vague_auth_value < 0.40:
            vague_auth_label, vague_auth_color = "Modérée", "#ca8a04"
        elif vague_auth_value < 0.70:
            vague_auth_label, vague_auth_color = "Élevée", "#f97316"
        else:
            vague_auth_label, vague_auth_color = "Très élevée", "#dc2626"

        render_custom_gauge(vague_auth_value, vague_auth_color)

        st.markdown(
            f"<b style='color:{vague_auth_color}'>{vague_auth_label}</b> — {round(vague_auth_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["vague_authority_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("vague_authority_markers", [])
            if not markers:
                st.info("Aucun marqueur d'autorité vague détecté.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 9) Charge émotionnelle
    # -----------------------------
    with row3_col3:
        st.markdown("### Charge émotionnelle")
        st.caption("Intensité affective du lexique utilisé pour orienter la lecture.")

        emotional_value = result["emotional_intensity_score"]

        if emotional_value < 0.15:
            emotional_label, emotional_color = "Faible", "#16a34a"
        elif emotional_value < 0.35:
            emotional_label, emotional_color = "Modérée", "#ca8a04"
        elif emotional_value < 0.60:
            emotional_label, emotional_color = "Élevée", "#f97316"
        else:
            emotional_label, emotional_color = "Très élevée", "#dc2626"

        render_custom_gauge(emotional_value, emotional_color)

        st.markdown(
            f"<b style='color:{emotional_color}'>{emotional_label}</b> — {round(emotional_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["emotional_intensity_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("emotional_intensity_markers", [])
            if not markers:
                st.info("Aucun marqueur émotionnel notable détecté.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 10) Généralisation abusive
    # -----------------------------
    with row4_col1:
        st.markdown("### Généralisation abusive")
        st.caption("Simplification du réel par catégories globales.")

        generalization_value = result["generalization_score"]

        if generalization_value < 0.20:
            generalization_label, generalization_color = "Faible", "#16a34a"
        elif generalization_value < 0.40:
            generalization_label, generalization_color = "Modérée", "#ca8a04"
        elif generalization_value < 0.70:
            generalization_label, generalization_color = "Élevée", "#f97316"
        else:
            generalization_label, generalization_color = "Très élevée", "#dc2626"

        render_custom_gauge(generalization_value, generalization_color)

        st.markdown(
            f"<b style='color:{generalization_color}'>{generalization_label}</b> — {round(generalization_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["generalization_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("generalization_markers", [])
            if not markers:
                st.info("Aucune généralisation abusive notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 11) Ennemi abstrait
    # -----------------------------
    with row4_col2:
        st.markdown("### Ennemi abstrait")
        st.caption("Construction d’un adversaire flou ou globalisant.")

        abstract_enemy_value = result["abstract_enemy_score"]

        if abstract_enemy_value < 0.20:
            abstract_enemy_label, abstract_enemy_color = "Faible", "#16a34a"
        elif abstract_enemy_value < 0.40:
            abstract_enemy_label, abstract_enemy_color = "Modérée", "#ca8a04"
        elif abstract_enemy_value < 0.70:
            abstract_enemy_label, abstract_enemy_color = "Élevée", "#f97316"
        else:
            abstract_enemy_label, abstract_enemy_color = "Très élevée", "#dc2626"

        render_custom_gauge(abstract_enemy_value, abstract_enemy_color)

        st.markdown(
            f"<b style='color:{abstract_enemy_color}'>{abstract_enemy_label}</b> — {round(abstract_enemy_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["abstract_enemy_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("abstract_enemy_markers", [])
            if not markers:
                st.info("Aucun ennemi abstrait notable détecté.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 12) Certitude absolue
    # -----------------------------
    with row4_col3:
        st.markdown("### Certitude absolue")
        st.caption("Rigidité rhétorique et fermeture interprétative.")

        certainty_value = result["certainty_score"]

        if certainty_value < 0.20:
            certainty_label, certainty_color = "Faible", "#16a34a"
        elif certainty_value < 0.40:
            certainty_label, certainty_color = "Modérée", "#ca8a04"
        elif certainty_value < 0.70:
            certainty_label, certainty_color = "Élevée", "#f97316"
        else:
            certainty_label, certainty_color = "Très élevée", "#dc2626"

        render_custom_gauge(certainty_value, certainty_color)

        st.markdown(
            f"<b style='color:{certainty_color}'>{certainty_label}</b> — {round(certainty_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["certainty_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("certainty_markers", [])
            if not markers:
                st.info("Aucun marqueur fort de certitude absolue détecté.")
            else:
                for marker in markers:
                    st.warning(marker)

        # -----------------------------
    # 13) Faux consensus
    # -----------------------------
    with row5_col1:
        st.markdown("### Faux consensus")
        st.caption("Simulation d’un accord collectif présenté comme évident.")

        false_consensus_value = result["false_consensus_score"]

        if false_consensus_value < 0.15:
            false_consensus_label, false_consensus_color = "Faible", "#16a34a"
        elif false_consensus_value < 0.35:
            false_consensus_label, false_consensus_color = "Modérée", "#ca8a04"
        elif false_consensus_value < 0.60:
            false_consensus_label, false_consensus_color = "Élevée", "#f97316"
        else:
            false_consensus_label, false_consensus_color = "Très élevée", "#dc2626"

        render_custom_gauge(false_consensus_value, false_consensus_color)

        st.markdown(
            f"<b style='color:{false_consensus_color}'>{false_consensus_label}</b> — {round(false_consensus_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["false_consensus_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("false_consensus_markers", [])
            if not markers:
                st.info("Aucun faux consensus notable détecté.")
            else:
                for marker in markers:
                    st.warning(marker)


    # -----------------------------
    # 14) Opposition binaire
    # -----------------------------
    with row5_col2:
        st.markdown("### Opposition binaire")
        st.caption("Découpage du discours en camps antagonistes.")

        binary_value = result["binary_opposition_score"]

        if binary_value < 0.15:
            binary_label, binary_color = "Faible", "#16a34a"
        elif binary_value < 0.35:
            binary_label, binary_color = "Modérée", "#ca8a04"
        elif binary_value < 0.60:
            binary_label, binary_color = "Élevée", "#f97316"
        else:
            binary_label, binary_color = "Très élevée", "#dc2626"

        render_custom_gauge(binary_value, binary_color)

        st.markdown(
            f"<b style='color:{binary_color}'>{binary_label}</b> — {round(binary_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["binary_opposition_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("binary_opposition_markers", [])
            if not markers:
                st.info("Aucune opposition binaire notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)


    # -----------------------------
    # 15) Amplification de menace
    # -----------------------------
    with row5_col3:
        st.markdown("### Amplification de menace")
        st.caption("Exagération dramatique du danger ou de la gravité.")

        threat_value = result["threat_amplification_score"]

        if threat_value < 0.15:
            threat_label, threat_color = "Faible", "#16a34a"
        elif threat_value < 0.35:
            threat_label, threat_color = "Modérée", "#ca8a04"
        elif threat_value < 0.60:
            threat_label, threat_color = "Élevée", "#f97316"
        else:
            threat_label, threat_color = "Très élevée", "#dc2626"

        render_custom_gauge(threat_value, threat_color)

        st.markdown(
            f"<b style='color:{threat_color}'>{threat_label}</b> — {round(threat_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["threat_amplification_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("threat_amplification_markers", [])
            if not markers:
                st.info("Aucune amplification de menace notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

        # -----------------------------
    # 19) Fausse analogie
    # -----------------------------
    with row7_col1:
        st.markdown("### Fausse analogie")
        st.caption("Comparaisons trompeuses qui court-circuitent l’analyse.")

        value = result["false_analogy_score"]

        if value < 0.15:
            label, color = "Faible", "#16a34a"
        elif value < 0.35:
            label, color = "Modérée", "#ca8a04"
        elif value < 0.60:
            label, color = "Élevée", "#f97316"
        else:
            label, color = "Très élevée", "#dc2626"

        render_custom_gauge(value, color)
        st.markdown(f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%", unsafe_allow_html=True)
        st.caption(result["false_analogy_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("false_analogy_markers", [])
            if not markers:
                st.info("Aucune fausse analogie notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 20) Surinterprétation factuelle
    # -----------------------------
    with row7_col2:
        st.markdown("### Surinterprétation factuelle")
        st.caption("Conclusions excessives tirées à partir d’indices partiels.")

        value = result["factual_overinterpretation_score"]

        if value < 0.15:
            label, color = "Faible", "#16a34a"
        elif value < 0.35:
            label, color = "Modérée", "#ca8a04"
        elif value < 0.60:
            label, color = "Élevée", "#f97316"
        else:
            label, color = "Très élevée", "#dc2626"

        render_custom_gauge(value, color)
        st.markdown(f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%", unsafe_allow_html=True)
        st.caption(result["factual_overinterpretation_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("factual_overinterpretation_markers", [])
            if not markers:
                st.info("Aucune surinterprétation factuelle notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 21) Dissonance interne
    # -----------------------------
    with row7_col3:
        st.markdown("### Dissonance interne")
        st.caption("Contradictions ou incompatibilités au sein du même discours.")

        value = result["internal_dissonance_score"]

        if value < 0.15:
            label, color = "Faible", "#16a34a"
        elif value < 0.35:
            label, color = "Modérée", "#ca8a04"
        elif value < 0.60:
            label, color = "Élevée", "#f97316"
        else:
            label, color = "Très élevée", "#dc2626"

        render_custom_gauge(value, color)
        st.markdown(f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%", unsafe_allow_html=True)
        st.caption(result["internal_dissonance_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("internal_dissonance_markers", [])
            if not markers:
                st.info("Aucune dissonance interne notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 22) Saturation normative
    # -----------------------------
    with row8_col1:
        st.markdown("### Saturation normative")
        st.caption("Accumulation de jugements moraux à la place de l’analyse.")

        value = result["normative_saturation_score"]

        if value < 0.15:
            label, color = "Faible", "#16a34a"
        elif value < 0.35:
            label, color = "Modérée", "#ca8a04"
        elif value < 0.60:
            label, color = "Élevée", "#f97316"
        else:
            label, color = "Très élevée", "#dc2626"

        render_custom_gauge(value, color)
        st.markdown(f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%", unsafe_allow_html=True)
        st.caption(result["normative_saturation_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("normative_saturation_markers", [])
            if not markers:
                st.info("Aucune saturation normative notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 23) Rigidité doxique
    # -----------------------------
    with row8_col2:
        st.markdown("### Rigidité doxique")
        st.caption("Degré de fermeture du texte par excès de certitude partagée.")

        value = result["doxic_rigidity_score"]

        if value < 0.15:
            label, color = "Faible", "#16a34a"
        elif value < 0.35:
            label, color = "Modérée", "#ca8a04"
        elif value < 0.60:
            label, color = "Élevée", "#f97316"
        else:
            label, color = "Très élevée", "#dc2626"

        render_custom_gauge(value, color)
        st.markdown(f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%", unsafe_allow_html=True)
        st.caption(result["doxic_rigidity_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("doxic_rigidity_markers", [])
            if not markers:
                st.info("Aucune rigidité doxique notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

    # -----------------------------
    # 24) Surdétermination narrative
    # -----------------------------
    with row8_col3:
        st.markdown("### Surdétermination narrative")
        st.caption("Réduction du réel à un récit unique supposé tout expliquer.")

        value = result["narrative_overdetermination_score"]

        if value < 0.15:
            label, color = "Faible", "#16a34a"
        elif value < 0.35:
            label, color = "Modérée", "#ca8a04"
        elif value < 0.60:
            label, color = "Élevée", "#f97316"
        else:
            label, color = "Très élevée", "#dc2626"

        render_custom_gauge(value, color)
        st.markdown(f"<b style='color:{color}'>{label}</b> — {round(value*100,1)}%", unsafe_allow_html=True)
        st.caption(result["narrative_overdetermination_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("narrative_overdetermination_markers", [])
            if not markers:
                st.info("Aucune surdétermination narrative notable détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

        # -----------------------------
    # 16) Glissement sémantique
    # -----------------------------
    with row6_col1:
        st.markdown("### Glissement sémantique")
        st.caption("Recadrage lexical stratégique du réel par des termes orientés.")

        semantic_value = result["semantic_shift_score"]

        if semantic_value < 0.20:
            semantic_label, semantic_color = "Faible", "#16a34a"
        elif semantic_value < 0.40:
            semantic_label, semantic_color = "Modérée", "#ca8a04"
        elif semantic_value < 0.70:
            semantic_label, semantic_color = "Élevée", "#f97316"
        else:
            semantic_label, semantic_color = "Très élevée", "#dc2626"

        render_custom_gauge(semantic_value, semantic_color)

        st.markdown(
            f"<b style='color:{semantic_color}'>{semantic_label}</b> — {round(semantic_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["semantic_shift_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("semantic_shift_markers", [])
            if not markers:
                st.info("Aucun glissement sémantique notable détecté.")
            else:
                for marker in markers:
                    st.warning(marker)

        # -----------------------------
    # 17) Prémisses idéologiques implicites
    # -----------------------------
    with row6_col2:
        st.markdown("### Prémisses idéologiques")
        st.caption("Présupposés idéologiques présentés comme allant de soi.")

        ideological_value = result["ideological_premise_score"]

        if ideological_value < 0.20:
            ideological_label, ideological_color = "Faible", "#16a34a"
        elif ideological_value < 0.40:
            ideological_label, ideological_color = "Modérée", "#ca8a04"
        elif ideological_value < 0.70:
            ideological_label, ideological_color = "Élevée", "#f97316"
        else:
            ideological_label, ideological_color = "Très élevée", "#dc2626"

        render_custom_gauge(ideological_value, ideological_color)

        st.markdown(
            f"<b style='color:{ideological_color}'>{ideological_label}</b> — {round(ideological_value * 100, 1)}%",
            unsafe_allow_html=True
        )
        st.caption(result["ideological_premise_interpretation"])

        with st.expander("Voir les marqueurs", expanded=False):
            markers = result.get("ideological_premise_markers", [])
            if not markers:
                st.info("Aucune prémisse idéologique saillante détectée.")
            else:
                for marker in markers:
                    st.warning(marker)

        # -----------------------------
    # 18) Clôture cognitive
    # -----------------------------
    with row6_col3:
        st.markdown("### Clôture cognitive")
        st.caption("Degré de verrouillage du discours par excès de certitude.")

        closure_local = (
            (result["D"] * (1 + len(result["red_flags"]) / 5)) / (result["G"] + result["N"])
            if (result["G"] + result["N"]) > 0 else 10
        )

        closure_value = min(closure_local / 1.5, 1.0)

        if closure_local < 0.40:
            closure_label, closure_color = "Ouverte", "#16a34a"
        elif closure_local < 0.75:
            closure_label, closure_color = "Modérée", "#ca8a04"
        elif closure_local < 1.10:
            closure_label, closure_color = "Élevée", "#f97316"
        else:
            closure_label, closure_color = "Critique", "#dc2626"

        render_custom_gauge(closure_value, closure_color)

        st.markdown(
            f"<b style='color:{closure_color}'>{closure_label}</b> — {round(closure_local, 2)}",
            unsafe_allow_html=True
        )
        st.caption("Plus la certitude domine G + N, plus le texte se ferme.")
                
    with st.expander("Voir les manœuvres discursives détectées", expanded=False):
        if result["political_pattern_score"] == 0:
            st.info("Aucun marqueur rhétorique politique saillant détecté.")
        else:
            st.metric("Score global de manœuvres discursives", result["political_pattern_score"])

            labels = {
                "certitude": "Certitude performative",
                "autorite": "Autorité vague institutionnelle",
                "autorite_academique": "Autorité académique vague",
                "dramatisation": "Dramatisation politique",
                "generalisation": "Généralisation abusive",
                "naturalisation": "Naturalisation idéologique",
                "ennemi": "Ennemi abstrait",
                "victimisation": "Victimisation discursive",
                "moralisation": "Moralisation politique",
                "moralisation_discours": "Moralisation du discours",
                "urgence": "Urgence injonctive",
                "promesse": "Promesse excessive",
                "populisme": "Populisme anti-élite",
                "progressisme_identitaire": "Progressisme identitaire",
                "socialisme_communisme": "Cadre socialiste / communiste",
                "delegitimation": "Délégitimation adverse",
                "dilution": "Dilution de responsabilité",
                "causalite": "Causalité implicite ou non démontrée",
            }

            for cat, count in result["political_results"].items():
                if count > 0:
                    st.markdown(f"**{labels.get(cat, cat)}** : {count}")
                    st.caption(", ".join(result["matched_terms"][cat]))

    with st.expander(T["strengths_detected"], expanded=True):
        if result["strengths"]:
            for item in result["strengths"]:
                st.success(item)
        else:
            st.info(T["few_strong_signals"])

    with st.expander(T["weaknesses_detected"], expanded=True):
        if result["weaknesses"]:
            for item in result["weaknesses"]:
                st.error(item)
        else:
            st.success(T["no_major_weakness"])

    st.divider()
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

    st.subheader(T["hard_fact_checking_by_claim"])
    claims_df = pd.DataFrame(
        [
            {
                T["claim"]: c.text,
                T["status"]: c.status,
                f"{T['verifiability']} /20": c.verifiability,
                f"{T['risk']} /20": c.risk,
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

    st.divider()
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
else:
    st.info(T["paste_text_or_load_url"])

# -----------------------------
# Méthode
# -----------------------------
if show_method:
    st.subheader(T["method"])
    st.markdown(
        f"### {T['original_formula']}\n"
        f"`M = (G + N) − D`\n"
        f"- {T['articulated_knowledge_density']}\n"
        f"- {T['integration']}\n"
        f"- {T['assertive_rigidity']}\n\n"
        f"### {T['llm_metrics']}\n"
        f"- **{T['overconfidence']}** : `D - (G + N)`\n"
        f"- **{T['calibration']}** : `D / (G + N)`\n"
        f"- **{T['revisability']}** : `(G + N + V) - D`\n"
        f"- **{T['cognitive_closure']}** : `(D * S) / (G + N)`\n\n"
        f"{T['disclaimer']}"
    )


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
        M = ({g_game:.1f} + {n_game:.1f}) − {d_game:.1f} =
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
