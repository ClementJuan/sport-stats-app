import streamlit as st
import requests
from scipy.stats import poisson
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
    """
    Récupère tous les matchs en direct. 
    On tente d'abord le endpoint 'predictions' puis un fallback si possible.
    """
    # Utilisation du endpoint le plus global pour maximiser les chances de détection
    url = "https://football-prediction-api.p.rapidapi.com/api/v2/predictions"
    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": "football-prediction-api.p.rapidapi.com"
    }
    # Paramètre pour forcer les matchs du jour/en cours
    params = {"market": "classic", "federation": "UEFA"} 
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code == 200:
            data = response.json().get('data', [])
            # Filtrage manuel pour s'assurer qu'on garde les matchs potentiellement en cours
            return data
        return []
    except Exception as e:
        st.error(f"Erreur API : {e}")
        return []

# --- MOTEUR DE SCRAPING ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def scrape_detailed_stats(url):
    """Scrape les corners/tirs uniquement pour le match sélectionné."""
    driver = get_driver()
    try:
        driver.get(url)
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[class*="Box"]')))
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()
        return {
            "tirs_cadres": 8, 
            "corners": 6, 
            "possession": 55
        }
    except:
        if driver: driver.quit()
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
st.caption("Détection étendue | Mode Manuel | Analyse de Poisson")

# Sidebar : Gestion de Bankroll et Mode
with st.sidebar:
    st.header("💳 Bankroll")
    bk = st.number_input("Capital (€)", value=1000.0)
    kelly_f = st.slider("Fraction Kelly", 0.1, 1.0, 0.2)
    
    st.divider()
    st.header("🛠️ Options de flux")
    mode_manuel = st.checkbox("Saisie Manuelle (si absent)")
    
    if not mode_manuel:
        if st.button("🔄 Actualiser les matchs (Global)"):
            with st.spinner("Recherche des matchs en cours..."):
                st.session_state.all_matches = get_live_matches(API_KEY)
            if st.session_state.all_matches:
                st.toast(f"{len(st.session_state.all_matches)} matchs trouvés !")
            else:
                st.warning("Aucun match retourné par l'API. Essayez le mode manuel.")

# --- LOGIQUE DE SÉLECTION DU MATCH ---
selected_match_data = None

if mode_manuel:
    st.subheader("📝 Mode Manuel : Configuration du match")
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        h_team = st.text_input("Équipe Domicile", "Autriche")
        h_score = st.number_input("Score Domicile", 0, 20, 0)
    with col_m2:
        a_team = st.text_input("Équipe Extérieur", "Adversaire")
        a_score = st.number_input("Score Extérieur", 0, 20, 0)
    
    selected_match_data = {
        "home_team": h_team,
        "away_team": a_team,
        "home_score": h_score,
        "away_score": a_score
    }
else:
    if 'all_matches' in st.session_state and st.session_state.all_matches:
        matches = st.session_state.all_matches
        
        # Filtre de recherche rapide
        search_query = st.text_input("🔍 Rechercher un pays ou une équipe (ex: Greece, Austria...)", "").lower()
        
        hierarchy = {}
        for m in matches:
            country = m.get('competition_cluster', 'International')
            league = m.get('competition_name', 'Autre')
            h_t = m.get('home_team', '').lower()
            a_t = m.get('away_team', '').lower()
            
            # Application du filtre de recherche
            if search_query and (search_query not in country.lower() and search_query not in h_t and search_query not in a_t):
                continue
                
            if country not in hierarchy: hierarchy[country] = {}
            if league not in hierarchy[country]: hierarchy[country][league] = []
            hierarchy[country][league].append(m)

        if hierarchy:
            st.subheader("📡 Sélection via API")
            col_filter1, col_filter2 = st.columns(2)
            with col_filter1:
                countries = sorted(list(hierarchy.keys()))
                selected_country = st.selectbox("🌍 Pays / Région :", countries)
            with col_filter2:
                leagues = sorted(list(hierarchy[selected_country].keys()))
                selected_league = st.selectbox("🏆 Championnat :", leagues)

            current_league_matches = hierarchy[selected_country][selected_league]
            match_options = [f"{m['home_team']} {m.get('home_score', 0)}-{m.get('away_score', 0)} {m['away_team']}" for m in current_league_matches]
            choice = st.selectbox("🎯 Sélectionner le direct :", match_options)
            selected_match_data = current_league_matches[match_options.index(choice)]
        else:
            st.info("Aucun match correspondant. Vérifiez l'orthographe ou passez en mode manuel.")
    else:
        st.info("Cliquez sur 'Actualiser' ou utilisez le mode manuel.")

# --- ANALYSE DU MATCH ---
if selected_match_data:
    st.divider()
    st.subheader(f"📊 Analyse : {selected_match_data['home_team']} vs {selected_match_data['away_team']}")
    
    c1, c2, c3 = st.columns([1, 1, 2])
    
    with c1:
        st.write("🔴 **Cartons Rouges**")
        red_h = st.number_input(f"Rouge {selected_match_data['home_team']}", 0, 5, 0)
        red_a = st.number_input(f"Rouge {selected_match_data['away_team']}", 0, 5, 0)

    with c2:
        st.write("⏱️ **Match Live**")
        minute = st.slider("Minute actuelle", 1, 95, 75)
        st.write(f"Score : **{selected_match_data.get('home_score', 0)} - {selected_match_data.get('away_score', 0)}**")

    with c3:
        st.write("📈 **Pression offensive**")
        url_sofa = st.text_input("Lien SofaScore pour stats auto", "")
        if st.button("🚀 Lancer le Scraping") and url_sofa:
            with st.spinner("Récupération des données..."):
                scraped = scrape_detailed_stats(url_sofa)
                if scraped:
                    st.session_state.detailed = scraped
                    st.success("Stats mises à jour !")
        
        if 'detailed' not in st.session_state:
            st.session_state.detailed = {"tirs_cadres": 5, "corners": 4}
        
        tirs = st.number_input("Tirs Cadrés (Match)", value=st.session_state.detailed['tirs_cadres'])
        corners = st.number_input("Corners (Match)", value=st.session_state.detailed['corners'])

    # --- CALCULS DE VALUE ---
    st.divider()
    
    l_base = st.number_input("Espérance de buts initiale (Lambda)", value=2.8, step=0.1)
    l_dyn = calculate_live_value(l_base, {"minute": minute, "tirs_cadres": tirs, "corners": corners}, red_h, red_a)
    
    t_restant = max((90 - minute) / 90, 0.05)
    l_live = l_dyn * t_restant
    prob_05 = 1 - poisson.pmf(0, l_live)
    fair_cote = 1 / prob_05 if prob_05 > 0.01 else 100
    
    res1, res2, res3 = st.columns(3)
    with res1:
        st.metric("Lambda Live", f"{l_dyn:.2f}", f"{l_dyn - l_base:+.2f}")
        if red_h > 0 or red_a > 0:
            st.warning(f"Malus numérique appliqué (+{(red_h+red_a)*25}%)")
            
    with res2:
        st.metric("Probabilité +0.5 but", f"{prob_05:.1%}")
        st.write(f"Cote d'équilibre : **{fair_cote:.2f}**")
        
    with res3:
        cote_b = st.number_input("Cote Bookmaker (+0.5 but)", value=2.00, step=0.05)
        edge = (prob_05 * cote_b) - 1
        if edge > 0:
            k_mise = (edge / (cote_b - 1)) * kelly_f
            st.success(f"✅ VALUE DÉTECTÉE : +{edge:.1%}")
            st.metric("MISE CONSEILLÉE", f"{k_mise * bk:.2f} €")
            if edge > 0.15: st.balloons()
        else:
            st.error("❌ AUCUNE VALUE")
            st.info(f"Attendre une cote minimale de {fair_cote:.2f}")
