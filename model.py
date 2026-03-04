import streamlit as st
import requests
from scipy.stats import poisson
from bs4 import BeautifulSoup
import re
import os
import time
import gc

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Clé 'api_key' manquante dans les Secrets Streamlit.")
    st.stop()

st.set_page_config(page_title="Poisson Live Scanner Pro+", layout="wide")

# --- SCRAPER ROBUSTE (SANS SELENIUM) ---
def scrape_sofascore_fast(url):
    """Extraction rapide utilisant requests avec des headers de navigateur."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/"
    }
    
    data = None
    try:
        # On tente de récupérer le HTML brut
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            st.error(f"Erreur SofaScore : Code {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extraction des noms (SofaScore stocke souvent les données dans un JSON initial dans le HTML)
        # On cherche d'abord dans les balises meta ou les titres pour un fallback rapide
        page_title = soup.find('title').get_text() if soup.find('title') else ""
        
        # Tentative d'extraction par regex dans le HTML (plus robuste que les classes CSS changeantes)
        # On cherche le score et les équipes dans le titre ou les meta tags
        teams = ["Domicile", "Extérieur"]
        if " - " in page_title:
            teams = page_title.split(" live")[0].split(" - ")
        
        # Simulation de statistiques (Fallback si le JS n'est pas rendu côté serveur)
        # Note : Sans Selenium, on accède au HTML "statique". 
        # Si SofaScore masque tout derrière du JS, on utilise une approche par l'API interne si possible.
        
        h_score = 0
        a_score = 0
        score_match = re.search(r'(\d+)\s*-\s*(\d+)', page_title)
        if score_match:
            h_score = int(score_match.group(1))
            a_score = int(score_match.group(2))

        # Pour les stats détaillées sans Selenium, SofaScore nécessite souvent l'ID du match
        # On essaie d'extraire l'ID du match de l'URL pour une future extension API directe
        match_id = re.search(r'/([^/]+)$', url.strip('/')).group(1) if "/" in url else None

        data = {
            "home_team": teams[0].strip(),
            "away_team": teams[1].strip() if len(teams) > 1 else "Extérieur",
            "home_score": h_score,
            "away_score": a_score,
            "h_shots": 0, # Les stats avancées nécessitent souvent le rendu JS
            "a_shots": 0,
            "h_target": 0,
            "a_target": 0,
            "h_poss": 50
        }
        
        st.info("💡 Mode Rapide : Les noms et scores sont synchronisés. Ajustez les tirs manuellement pour le calcul.")
        
    except Exception as e:
        st.warning(f"Erreur de lecture : {str(e)[:100]}")
    finally:
        gc.collect()
    
    return data

# --- FONCTION API RAPIDAPI ---
def get_live_matches(key):
    url = "https://football-prediction-api.p.rapidapi.com/api/v2/predictions"
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "football-prediction-api.p.rapidapi.com"}
    params = {"market": "classic", "federation": "UEFA"} 
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        return response.json().get('data', []) if response.status_code == 200 else []
    except: return []

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
st.caption("Mode Ultra-Léger - Performance et Stabilité garanties")

if 'live_data' not in st.session_state:
    st.session_state.live_data = None

with st.sidebar:
    st.header("💳 Bankroll")
    bk = st.number_input("Capital (€)", value=1000.0)
    kelly_f = st.slider("Fraction Kelly", 0.1, 1.0, 0.2)
    st.divider()
    source_mode = st.radio("Source :", ["API Live (Recommandé)", "URL SofaScore (Léger)"])

selected_match = None

if source_mode == "URL SofaScore (Léger)":
    url = st.text_input("Lien SofaScore du match :", placeholder="https://www.sofascore.com/fr/match-equipe...")
    if url and st.button("🚀 Synchroniser le Match"):
        with st.spinner("Récupération des données stables..."):
            data = scrape_sofascore_fast(url)
            if data:
                st.session_state.live_data = data
                st.success("Match chargé !")
    
    selected_match = st.session_state.live_data
else:
    if st.button("🔄 Actualiser la liste des matchs"):
        st.session_state.all_matches = get_live_matches(API_KEY)
    if 'all_matches' in st.session_state:
        m_list = st.session_state.all_matches
        if m_list:
            choice = st.selectbox("Sélectionnez un match :", [f"{m['home_team']} vs {m['away_team']}" for m in m_list])
            selected_match = m_list[[f"{m['home_team']} vs {m['away_team']}" for m in m_list].index(choice)]
        else:
            st.warning("Aucun match trouvé via l'API. Essayez le mode URL.")

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
    min_actuelle = st.slider("Minute du match", 1, 95, 75)
    l_base = st.number_input("Lambda (Espérance de buts totale)", 0.1, 10.0, 2.6)

    stats_map = {
        'h_shots': h_shots, 'h_target': h_target, 'h_poss': h_poss, 'h_red': h_red, 'cote_pre_h': c_pre_h,
        'a_shots': a_shots, 'a_target': a_target, 'a_red': a_red, 'cote_pre_a': c_pre_a
    }
    
    l_dyn = calculate_advanced_lambda(l_base, stats_map)
    l_live = l_dyn * (max((90 - min_actuelle), 5) / 90)
    prob_05 = 1 - poisson.pmf(0, l_live)
    fair_cote = 1/prob_05 if prob_05 > 0.01 else 100.0
    
    r1, r2, r3 = st.columns(3)
    r1.metric("Lambda Actuel", f"{l_dyn:.2f}")
    r2.metric("Probabilité +0.5", f"{prob_05:.1%}", f"Fair: {fair_cote:.2f}")
    with r3:
        bk_cote = st.number_input("Cote Bookmaker Actuelle", value=fair_cote + 0.1)
        edge = (prob_05 * bk_cote) - 1
        if edge > 0:
            st.success(f"VALUE DÉTECTÉE : +{edge:.1%}")
            st.metric("MISE CONSEILLÉE (KELLY)", f"{(edge/(bk_cote-1))*kelly_f*bk:.2f} €")
        else: st.error("PAS DE VALUE")
