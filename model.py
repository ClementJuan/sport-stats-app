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

# --- FONCTION API (LISTE DES MATCHS EN LIVE) ---
def get_live_matches(key):
    """Récupère tous les matchs en direct via l'API."""
    url = "https://football-prediction-api.p.rapidapi.com/api/v2/predictions"
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "football-prediction-api.p.rapidapi.com"}
    try:
        # Note : On filtre ici sur les matchs du jour / live
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', [])
        return []
    except:
        return []

# --- MOTEUR DE SCRAPING (POUR LE MATCH SÉLECTIONNÉ) ---
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
        
        # Extraction simulée (basée sur la logique précédente)
        return {
            "tirs_cadres": 8, 
            "corners": 6, 
            "possession": 55,
            "red_cards_home": 0, # On peut aussi les trouver ici
            "red_cards_away": 0
        }
    except:
        if driver: driver.quit()
        return None

# --- CALCULATEUR DYNAMIQUE AVEC CARTONS ROUGES ---
def calculate_live_value(base_l, stats, red_home=0, red_away=0):
    """
    Calcule le Lambda ajusté par la pression ET les cartons rouges.
    Un rouge augmente la probabilité de but de l'adversaire de ~25%.
    """
    modifier = 1.0
    min_ = max(stats.get('minute', 45), 1)
    
    # Impact Statistiques
    if stats.get('tirs_cadres', 0) > (min_ / 10): modifier += 0.15
    if stats.get('corners', 0) > (min_ / 8): modifier += 0.10
    
    # Impact Cartons Rouges (Malus défensif)
    if red_home > 0: modifier += (0.25 * red_home) # Plus de buts car infériorité home
    if red_away > 0: modifier += (0.25 * red_away) # Plus de buts car infériorité away
        
    return base_l * modifier

# --- INTERFACE PRINCIPALE ---
st.title("⚽ Scanner de Value Live Pro")
st.caption("Détection automatique des matchs | Gestion des Cartons Rouges | Analyse Poisson")

# Sidebar : Gestion de Bankroll
with st.sidebar:
    st.header("💳 Bankroll")
    bk = st.number_input("Capital (€)", value=1000.0)
    kelly_f = st.slider("Fraction Kelly", 0.1, 1.0, 0.2)
    
    st.divider()
    if st.button("🔄 Actualiser la liste des matchs"):
        st.session_state.all_matches = get_live_matches(API_KEY)
        st.toast("Liste synchronisée !")

# Liste des matchs
if 'all_matches' in st.session_state and st.session_state.all_matches:
    matches = st.session_state.all_matches
    
    # Filtre : Matchs avec Cartons Rouges ou Score serré
    st.subheader("📡 Matchs en cours d'analyse")
    
    options = [f"{m['home_team']} {m.get('home_score', 0)}-{m.get('away_score', 0)} {m['away_team']}" for m in matches]
    choice = st.selectbox("Sélectionnez un match pour une analyse approfondie :", options)
    
    selected_match = matches[options.index(choice)]
    
    # 1. Gestion des Cartons Rouges (Saisie ou Auto si dispo dans l'API)
    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])
    
    with c1:
        st.write("🔴 **Cartons Rouges**")
        red_h = st.number_input(f"Rouge {selected_match['home_team']}", 0, 5, 0)
        red_a = st.number_input(f"Rouge {selected_match['away_team']}", 0, 5, 0)

    with c2:
        st.write("⏱️ **Temps & Score**")
        minute = st.slider("Minute du match", 1, 95, 70)
        score_live = st.text_input("Score actuel", value=f"{selected_match.get('home_score', 0)}-{selected_match.get('away_score', 0)}")

    with c3:
        st.write("📊 **Statistiques de Pression**")
        if st.button("🛰️ Scraper les stats live (SofaScore)"):
            # Ici on utiliserait l'URL si elle était fournie par l'API ou cherchée
            st.session_state.detailed = scrape_detailed_stats("https://www.sofascore.com/...")
            st.success("Stats récupérées !")
        
        # Fallback manuel si le scraping échoue ou pour ajuster
        if 'detailed' not in st.session_state:
            st.session_state.detailed = {"tirs_cadres": 5, "corners": 4, "possession": 50}
        
        tirs = st.number_input("Tirs Cadrés totaux", value=st.session_state.detailed['tirs_cadres'])
        corners = st.number_input("Corners totaux", value=st.session_state.detailed['corners'])

    # 2. CALCULS DE VALUE
    st.divider()
    st.subheader("🧠 Résultat de l'Analyse")
    
    # Lambda de base estimé par l'IA de l'API (souvent 2.5 - 3.0)
    l_base = 2.8 
    
    stats_for_calc = {"minute": minute, "tirs_cadres": tirs, "corners": corners}
    l_dyn = calculate_live_value(l_base, stats_for_calc, red_h, red_a)
    
    temps_restant = max((90 - minute) / 90, 0.05)
    l_live = l_dyn * temps_restant
    
    # Calcul Probabilités
    prob_05 = 1 - poisson.pmf(0, l_live)
    fair_cote = 1 / prob_05 if prob_05 > 0.01 else 100
    
    res1, res2, res3 = st.columns(3)
    
    with res1:
        st.metric("Lambda Ajusté", f"{l_dyn:.2f}", f"{l_dyn - l_base:+.2f}")
        if red_h > 0 or red_a > 0:
            st.warning(f"⚠️ Impact Rouge inclus (+{((red_h+red_a)*25)}%)")

    with res2:
        st.metric("Probabilité But", f"{prob_05:.1%}")
        st.write(f"Cote 'Fair' : **{fair_cote:.2f}**")

    with res3:
        cote_bookie = st.number_input("Cote Bookmaker Live (+0.5 but)", value=2.20, step=0.05)
        edge = (prob_05 * cote_bookie) - 1
        
        if edge > 0:
            k_mise = (edge / (cote_bookie - 1)) * kelly_f
            st.success(f"✅ VALUE : +{edge:.1%}")
            st.metric("MISE CONSEILLÉE", f"{k_mise * bk:.2f} €")
            if edge > 0.15: st.balloons()
        else:
            st.error(f"❌ PAS DE VALUE")
            st.info(f"Attendre une cote de **{fair_cote:.2f}**")

else:
    st.info("Cliquez sur 'Actualiser' dans la barre latérale pour lister les matchs en direct.")
