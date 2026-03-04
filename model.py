import streamlit as st
import requests
from scipy.stats import poisson
from bs4 import BeautifulSoup
import time
import re

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Clé 'api_key' manquante dans les Secrets Streamlit.")
    st.stop()

st.set_page_config(page_title="Poisson Live Scanner Pro", layout="wide")

# --- FONCTION API OPTIMISÉE POUR LE LIVE ---
def get_live_matches(key):
    """Récupère les matchs via l'API de prédiction."""
    url = "https://football-prediction-api.p.rapidapi.com/api/v2/predictions"
    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": "football-prediction-api.p.rapidapi.com"
    }
    params = {"market": "classic", "federation": "UEFA"} 
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            return response.json().get('data', [])
        return []
    except Exception as e:
        st.error(f"Erreur API : {e}")
        return []

# --- MOTEUR DE RÉCUPÉRATION LÉGER (SANS SELENIUM) ---
def scrape_full_match_data(url):
    """
    Récupère les données SofaScore via requêtes HTTP directes.
    Utilise un User-Agent pour éviter les blocages simples.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            st.error(f"Impossible d'accéder à la page (Erreur {response.status_code})")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extraction intelligente via les balises Meta (plus stable sur SofaScore)
        title = soup.find('title').get_text() if soup.find('title') else ""
        
        # Format SofaScore : "TeamA - TeamB live score, H2H and lineups | SofaScore"
        home_team, away_team = "Domicile", "Extérieur"
        if " - " in title:
            teams_part = title.split(" live score")[0]
            if " - " in teams_part:
                home_team, away_team = teams_part.split(" - ", 1)

        return {
            "home_team": home_team.strip(),
            "away_team": away_team.strip(),
            "tirs_cadres": 5, # Valeur de base à ajuster manuellement
            "corners": 4,     # Valeur de base à ajuster manuellement
            "home_score": 0,
            "away_score": 0
        }
    except Exception as e:
        st.error(f"Erreur lors de l'analyse : {str(e)}")
        return None

# --- CALCULATEUR DYNAMIQUE ---
def calculate_live_value(base_l, stats, red_home=0, red_away=0):
    modifier = 1.0
    min_ = max(stats.get('minute', 45), 1)
    if stats.get('tirs_cadres', 0) > (min_ / 10): modifier += 0.15
    if stats.get('corners', 0) > (min_ / 8): modifier += 0.10
    if red_home > 0: modifier += (0.25 * red_home)
    if red_away > 0: modifier += (0.25 * red_away)
    return base_l * modifier

# --- INTERFACE PRINCIPALE ---
st.title("⚽ Scanner de Value Live Pro")
st.caption("Filtrage par Pays/Ligue ou Analyse via URL SofaScore | Poisson Expert")

# Sidebar : Gestion de Bankroll et Mode
with st.sidebar:
    st.header("💳 Bankroll")
    bk = st.number_input("Capital (€)", value=1000.0)
    kelly_f = st.slider("Fraction Kelly", 0.1, 1.0, 0.2)
    
    st.divider()
    st.header("🛠️ Source de données")
    source_mode = st.radio("Choisir la source :", ["Liste API Live", "Lien SofaScore Direct"])
    
    if source_mode == "Liste API Live":
        if st.button("🔄 Actualiser les matchs"):
            with st.spinner("Recherche des matchs..."):
                st.session_state.all_matches = get_live_matches(API_KEY)
            if st.session_state.all_matches:
                st.toast(f"{len(st.session_state.all_matches)} matchs trouvés !")

# --- LOGIQUE DE SÉLECTION DU MATCH ---
selected_match_data = None

if source_mode == "Lien SofaScore Direct":
    st.subheader("🔗 Analyse via URL (Match non répertorié)")
    url_input = st.text_input("Collez l'URL SofaScore du match ici :", placeholder="https://www.sofascore.com/team-a-team-b/...")
    
    if url_input:
        if st.button("🔍 Charger les données du match"):
            with st.spinner("Analyse du lien..."):
                scraped_data = scrape_full_match_data(url_input)
                if scraped_data:
                    st.session_state.manual_data = scraped_data
                    st.success("Match détecté !")
    
    if 'manual_data' in st.session_state:
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            h_team = st.text_input("Équipe Domicile", value=st.session_state.manual_data['home_team'])
            h_score = st.number_input("Score Dom.", value=st.session_state.manual_data['home_score'])
        with col_m2:
            a_team = st.text_input("Équipe Extérieur", value=st.session_state.manual_data['away_team'])
            a_score = st.number_input("Score Ext.", value=st.session_state.manual_data['away_score'])
        
        selected_match_data = {
            "home_team": h_team, "away_team": a_team,
            "home_score": h_score, "away_score": a_score
        }
else:
    # Mode API avec filtrage hiérarchique
    if 'all_matches' in st.session_state and st.session_state.all_matches:
        matches = st.session_state.all_matches
        
        # 1. Grouper par Pays et Ligue
        hierarchy = {}
        for m in matches:
            country = m.get('competition_cluster', 'International')
            league = m.get('competition_name', 'Autre')
            if country not in hierarchy: hierarchy[country] = {}
            if league not in hierarchy[country]: hierarchy[country][league] = []
            hierarchy[country][league].append(m)
            
        st.subheader("📡 Sélection du Match API")
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            countries = sorted(list(hierarchy.keys()))
            selected_country = st.selectbox("🌍 Sélectionner un pays :", countries)
            
        with col_f2:
            leagues = sorted(list(hierarchy[selected_country].keys()))
            selected_league = st.selectbox("🏆 Compétition :", leagues)
            
        current_league_matches = hierarchy[selected_country][selected_league]
        match_options = [f"{m['home_team']} {m.get('home_score', 0)}-{m.get('away_score', 0)} {m['away_team']}" for m in current_league_matches]
        choice = st.selectbox("🎯 Choisir le match :", match_options)
        selected_match_data = current_league_matches[match_options.index(choice)]
    else:
        st.info("Utilisez le bouton 'Actualiser' dans la barre latérale pour charger les matchs API.")

# --- ANALYSE DU MATCH ---
if selected_match_data:
    st.divider()
    st.subheader(f"📊 {selected_match_data['home_team']} vs {selected_match_data['away_team']}")
    
    c1, c2, c3 = st.columns([1, 1, 2])
    
    with c1:
        st.write("🔴 **Cartons Rouges**")
        red_h = st.number_input(f"Rouge {selected_match_data['home_team']}", 0, 5, 0)
        red_a = st.number_input(f"Rouge {selected_match_data['away_team']}", 0, 5, 0)

    with c2:
        st.write("⏱️ **Temps du match**")
        minute = st.slider("Minute actuelle", 1, 95, 75)
        st.write(f"Score : **{selected_match_data.get('home_score', 0)} - {selected_match_data.get('away_score', 0)}**")

    with c3:
        st.write("📈 **Statistiques Live**")
        tirs = st.number_input("Tirs Cadrés totaux", value=5)
        corners = st.number_input("Corners totaux", value=4)

    # --- CALCULS DE VALUE ---
    st.divider()
    l_base = st.number_input("Lambda pré-match (Espérance de buts)", value=2.8, step=0.1)
    l_dyn = calculate_live_value(l_base, {"minute": minute, "tirs_cadres": tirs, "corners": corners}, red_h, red_a)
    
    t_restant = max((90 - minute) / 90, 0.05)
    l_live = l_dyn * t_restant
    prob_05 = 1 - poisson.pmf(0, l_live)
    fair_cote = 1 / prob_05 if prob_05 > 0.01 else 100
    
    res1, res2, res3 = st.columns(3)
    with res1:
        st.metric("Lambda Live", f"{l_dyn:.2f}", f"{l_dyn - l_base:+.2f}")
        if red_h > 0 or red_a > 0:
            st.warning(f"Malus numérique (+{(red_h+red_a)*25}%)")
            
    with res2:
        st.metric("Probabilité +0.5 but", f"{prob_05:.1%}")
        st.write(f"Cote 'Fair' : **{fair_cote:.2f}**")
        
    with res3:
        cote_b = st.number_input("Cote Bookmaker (+0.5 but)", value=2.00, step=0.05)
        edge = (prob_05 * cote_b) - 1
        if edge > 0:
            k_mise = (edge / (cote_b - 1)) * kelly_f
            st.success(f"✅ VALUE : +{edge:.1%}")
            st.metric("MISE CONSEILLÉE", f"{k_mise * bk:.2f} €")
            if edge > 0.15: st.balloons()
        else:
            st.error("❌ AUCUNE VALUE")
            st.info(f"Attendre une cote de {fair_cote:.2f}")
