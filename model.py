import streamlit as st
import requests
from scipy.stats import poisson
from bs4 import BeautifulSoup
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Clé 'api_key' manquante dans les Secrets Streamlit.")
    st.stop()

st.set_page_config(page_title="Poisson Live Scanner Pro+", layout="wide")

# --- CONFIGURATION SELENIUM (V5 - ROBUSTESSE ACCRUE) ---
@st.cache_resource
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # Éviter la détection de bot
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # User Agent récent pour paraître humain
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    potential_driver_paths = [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium-browser/chromedriver"
    ]
    
    driver_path = None
    for path in potential_driver_paths:
        if os.path.exists(path):
            driver_path = path
            break

    try:
        service = Service(driver_path) if driver_path else Service()
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        # Timeout de chargement de page
        driver.set_page_load_timeout(30)
        return driver
    except Exception as e:
        st.error(f"Erreur d'initialisation du Driver : {e}")
        return None

# --- FONCTION API ---
def get_live_matches(key):
    url = "https://football-prediction-api.p.rapidapi.com/api/v2/predictions"
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "football-prediction-api.p.rapidapi.com"}
    params = {"market": "classic", "federation": "UEFA"} 
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        return response.json().get('data', []) if response.status_code == 200 else []
    except: return []

# --- SCRAPING AVANCÉ ---
def scrape_sofascore_live(url):
    driver = get_driver()
    if not driver: return None
    
    try:
        driver.get(url)
        # Attente progressive
        time.sleep(5) 
        
        wait = WebDriverWait(driver, 30)
        # On attend spécifiquement l'un des conteneurs de noms d'équipes ou de stats
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h2[class*='TeamName'], div[class*='ScoreValue']"))) 

        # Tentative de défilement pour déclencher le lazy loading des stats
        driver.execute_script("window.scrollTo(0, 400);")
        time.sleep(2)

        # Récupération du HTML rendu
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Extraction des noms d'équipes
        team_elements = soup.find_all('h2', class_=re.compile("TeamName", re.I))
        home_name = team_elements[0].get_text(strip=True) if len(team_elements) > 0 else "Domicile"
        away_name = team_elements[1].get_text(strip=True) if len(team_elements) > 1 else "Extérieur"

        # Extraction du score
        score_elements = soup.find_all('span', class_=re.compile("ScoreValue", re.I))
        h_score = int(score_elements[0].get_text(strip=True)) if score_elements else 0
        a_score = int(score_elements[1].get_text(strip=True)) if len(score_elements) > 1 else 0

        def find_stat(label):
            # Recherche textuelle flexible dans le HTML rendu
            row = soup.find(string=re.compile(label, re.I))
            if row:
                # Navigation vers le parent qui contient les chiffres
                container = row.find_parent(class_=re.compile("Stat", re.I)) or row.find_parent().find_parent()
                nums = re.findall(r'\d+', container.get_text())
                if len(nums) >= 2:
                    return int(nums[0]), int(nums[-1])
            return 0, 0

        pos_h, pos_a = find_stat("Possession")
        shots_h, shots_a = find_stat("Total de tirs")
        target_h, target_a = find_stat("Tirs cadrés")

        return {
            "home_team": home_name, "away_team": away_name,
            "home_score": h_score, "away_score": a_score,
            "h_shots": shots_h, "a_shots": shots_a,
            "h_target": target_h, "a_target": target_a,
            "h_poss": pos_h if pos_h > 0 else 50
        }
    except Exception as e:
        st.warning(f"Erreur de scraping : {str(e)[:150]}...")
        # Fallback : Si Selenium échoue, on peut essayer d'extraire au moins le titre de la page
        try:
            return {"home_team": driver.title.split("-")[0].strip(), "away_team": "Equipe B", "home_score":0, "away_score":0, "h_shots":0, "a_shots":0, "h_target":0, "a_target":0, "h_poss":50}
        except: return None

# --- CALCULATEUR ---
def calculate_advanced_lambda(base_l, stats):
    danger_h = (stats['h_target'] * 0.35) + ((stats['h_shots'] - stats['h_target']) * 0.12)
    danger_a = (stats['a_target'] * 0.35) + ((stats['a_shots'] - stats['a_target']) * 0.12)
    
    talent_h = max(0.5, 2.0 / stats['cote_pre_h']) 
    talent_a = max(0.5, 2.0 / stats['cote_pre_a'])
    
    poss_bonus_h = 0.08 if stats['h_poss'] > 57 else 0
    poss_bonus_a = 0.08 if (100 - stats['h_poss']) > 57 else 0
    
    mod_h = (danger_h * talent_h) + poss_bonus_h - (stats['h_red'] * 0.3)
    mod_a = (danger_a * talent_a) + poss_bonus_a - (stats['a_red'] * 0.3)
    
    return base_l * (1.0 + mod_h + mod_a)

# --- UI STREAMLIT ---
st.title("⚽ Poisson Live Pro Scanner")
st.caption("Mode Expert - Analyse en temps réel via SofaScore")

if 'live_data' not in st.session_state:
    st.session_state.live_data = None

with st.sidebar:
    st.header("💳 Bankroll")
    bk = st.number_input("Capital (€)", value=1000.0)
    kelly_f = st.slider("Fraction Kelly", 0.1, 1.0, 0.2)
    st.divider()
    source_mode = st.radio("Source :", ["API Live", "URL SofaScore"])

selected_match = None

if source_mode == "URL SofaScore":
    url = st.text_input("Lien SofaScore du match :")
    if url and st.button("🔥 Lancer le Scraping Selenium"):
        with st.spinner("Analyse approfondie (Attente du rendu JavaScript)..."):
            data = scrape_sofascore_live(url)
            if data:
                st.session_state.live_data = data
                st.success("Données synchronisées !")
            else:
                st.error("Échec du scraping. SofaScore bloque peut-être la requête ou l'URL est invalide.")
    
    selected_match = st.session_state.live_data
else:
    if st.button("🔄 Actualiser API"):
        st.session_state.all_matches = get_live_matches(API_KEY)
    if 'all_matches' in st.session_state:
        m_list = st.session_state.all_matches
        choice = st.selectbox("Match :", [f"{m['home_team']} vs {m['away_team']}" for m in m_list])
        selected_match = m_list[[f"{m['home_team']} vs {m['away_team']}" for m in m_list].index(choice)]

if selected_match:
    st.header(f"{selected_match['home_team']} {selected_match['home_score']} - {selected_match['away_score']} {selected_match['away_team']}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏠 Domicile")
        c_pre_h = st.number_input("Cote pré-match Dom.", 1.01, 50.0, 1.80)
        h_shots = st.number_input("Tirs Dom.", 0, 50, selected_match.get('h_shots', 5))
        h_target = st.number_input("Tirs Cadrés Dom.", 0, 50, selected_match.get('h_target', 2))
        h_poss = st.slider("% Possession Dom.", 0, 100, selected_match.get('h_poss', 50))
        h_red = st.number_input("Rouges Dom.", 0, 5, 0)
    with col2:
        st.subheader("🚀 Extérieur")
        c_pre_a = st.number_input("Cote pré-match Ext.", 1.01, 50.0, 3.50)
        a_shots = st.number_input("Tirs Ext.", 0, 50, selected_match.get('a_shots', 3))
        a_target = st.number_input("Tirs Cadrés Ext.", 0, 50, selected_match.get('a_target', 1))
        st.info(f"Possession Ext. : {100-h_poss}%")
        a_red = st.number_input("Rouges Ext.", 0, 5, 0)

    st.divider()
    min_actuelle = st.slider("Minute", 1, 95, 75)
    l_base = st.number_input("Lambda Pré-match", 0.1, 10.0, 2.6)

    stats_map = {
        'h_shots': h_shots, 'h_target': h_target, 'h_poss': h_poss, 'h_red': h_red, 'cote_pre_h': c_pre_h,
        'a_shots': a_shots, 'a_target': a_target, 'a_red': a_red, 'cote_pre_a': c_pre_a
    }
    
    l_dyn = calculate_advanced_lambda(l_base, stats_map)
    l_live = l_dyn * (max((90 - min_actuelle), 5) / 90)
    prob_05 = 1 - poisson.pmf(0, l_live)
    fair_cote = 1/prob_05 if prob_05 > 0.01 else 100.0
    
    r1, r2, r3 = st.columns(3)
    r1.metric("Lambda Dynamique", f"{l_dyn:.2f}")
    r2.metric("Probabilité +0.5", f"{prob_05:.1%}", f"Fair: {fair_cote:.2f}")
    with r3:
        bk_cote = st.number_input("Cote Bookmaker", value=fair_cote + 0.1)
        edge = (prob_05 * bk_cote) - 1
        if edge > 0:
            st.success(f"VALUE : +{edge:.1%}")
            st.metric("MISE KELLY", f"{(edge/(bk_cote-1))*kelly_f*bk:.2f} €")
        else: st.error("AUCUNE VALUE")
