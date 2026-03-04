import streamlit as st
import requests
from scipy.stats import poisson
from bs4 import BeautifulSoup
import re
import os
import time
import gc
from scipy.optimize import fsolve

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Clé 'api_key' manquante dans les Secrets Streamlit.")
    st.stop()

st.set_page_config(page_title="Poisson Live Scanner Pro+", layout="wide")

# --- FONCTIONS MATHÉMATIQUES ---
def find_lambda_from_over25(cote_over25):
    """
    Calcule le lambda pré-match à partir de la cote Over 2.5.
    P(Over 2.5) = 1 - (P(0) + P(1) + P(2))
    """
    if cote_over25 <= 1.0: return 3.0
    prob_target = 1 / cote_over25
    
    # Fonction : f(L) = 1 - CDF_poisson(2, L) - prob_cible = 0
    func = lambda L: (1 - (poisson.pmf(0, L) + poisson.pmf(1, L) + poisson.pmf(2, L))) - prob_target
    
    # Estimation initiale basée sur des paliers communs
    initial_guess = 2.5 if cote_over25 > 2.0 else 3.5
    try:
        l_found = fsolve(func, initial_guess)[0]
        return max(0.5, min(6.0, l_found)) # Limites de sécurité
    except:
        return 2.5

def calculate_advanced_lambda(base_l, stats, minute):
    h_t = stats.get('h_target', 0)
    h_s = stats.get('h_shots', 0)
    a_t = stats.get('a_target', 0)
    a_s = stats.get('a_shots', 0)
    
    # Normalisation de la pression par minute
    cadence_normale = minute / 8 if minute > 0 else 1
    
    danger_h = ((h_t * 1.5 + (h_s - h_t) * 0.5) / cadence_normale) - 1.0 if minute > 10 else 0
    danger_a = ((a_t * 1.5 + (a_s - a_t) * 0.5) / cadence_normale) - 1.0 if minute > 10 else 0
    
    danger_h = max(-0.2, min(0.3, danger_h * 0.1))
    danger_a = max(-0.2, min(0.3, danger_a * 0.1))
    
    c_n = stats.get('cote_pre_n', 3.2)
    draw_factor = 1.0 + (c_n - 3.20) * 0.05
    draw_factor = max(0.92, min(1.10, draw_factor)) 
    
    multiplier = 1.0 + danger_h + danger_a
    red_penalty = (stats.get('h_red', 0) + stats.get('a_red', 0)) * 0.15
    multiplier -= red_penalty
    
    final_l = base_l * multiplier * draw_factor
    return max(0.8, min(5.0, final_l))

# --- SCRAPER ---
def scrape_sofascore_fast(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200: return None
        soup = BeautifulSoup(response.text, 'html.parser')
        page_title = soup.find('title').get_text() if soup.find('title') else ""
        teams = ["Domicile", "Extérieur"]
        if " - " in page_title: teams = page_title.split(" live")[0].split(" - ")
        h_score, a_score = 0, 0
        score_match = re.search(r'(\d+)\s*-\s*(\d+)', page_title)
        if score_match:
            h_score, a_score = int(score_match.group(1)), int(score_match.group(2))
        return {
            "home_team": teams[0].strip(), "away_team": teams[1].strip() if len(teams) > 1 else "Ext",
            "home_score": h_score, "away_score": a_score, "h_shots": 0, "a_shots": 0, "h_target": 0, "a_target": 0, "h_poss": 50
        }
    except: return None
    finally: gc.collect()

def get_live_matches(key):
    url = "https://football-prediction-api.p.rapidapi.com/api/v2/predictions"
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "football-prediction-api.p.rapidapi.com"}
    params = {"market": "classic", "federation": "UEFA"} 
    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        return response.json().get('data', []) if response.status_code == 200 else []
    except: return []

# --- UI STREAMLIT ---
st.title("⚽ Poisson Live Pro Scanner")
st.caption("Version 2.5 : Calcul automatique du Lambda via les cotes pré-match")

if 'live_data' not in st.session_state:
    st.session_state.live_data = None

with st.sidebar:
    st.header("💳 Bankroll")
    bk = st.number_input("Capital (€)", value=1000.0)
    kelly_f = st.slider("Fraction Kelly", 0.05, 1.0, 0.20)
    st.divider()
    source_mode = st.radio("Source :", ["API Live (Recommandé)", "URL SofaScore (Léger)"])

selected_match = None
if source_mode == "URL SofaScore (Léger)":
    url = st.text_input("Lien SofaScore :", placeholder="https://www.sofascore.com/...")
    if url and st.button("🚀 Synchroniser"):
        data = scrape_sofascore_fast(url)
        if data: st.session_state.live_data = data
    selected_match = st.session_state.live_data
else:
    if st.button("🔄 Actualiser les matchs"):
        st.session_state.all_matches = get_live_matches(API_KEY)
    if 'all_matches' in st.session_state:
        m_list = st.session_state.all_matches
        if m_list:
            choice = st.selectbox("Sélectionnez :", [f"{m.get('home_team', '??')} vs {m.get('away_team', '??')}" for m in m_list])
            selected_match = m_list[[f"{m.get('home_team', '??')} vs {m.get('away_team', '??')}" for m in m_list].index(choice)]

if selected_match:
    h_score = selected_match.get('home_score', 0)
    a_score = selected_match.get('away_score', 0)
    total_score_actuel = h_score + a_score
    
    st.header(f"{selected_match.get('home_team')} {h_score} - {a_score} {selected_match.get('away_team')}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏠 Domicile")
        h_shots = st.number_input("Tirs D", 0, 50, int(selected_match.get('h_shots', 5)))
        h_target = st.number_input("Cadrés D", 0, 50, int(selected_match.get('h_target', 2)))
        h_red = st.number_input("Rouges D", 0, 5, 0)
    with col2:
        st.subheader("🚀 Extérieur")
        a_shots = st.number_input("Tirs E", 0, 50, int(selected_match.get('a_shots', 3)))
        a_target = st.number_input("Cadrés E", 0, 50, int(selected_match.get('a_target', 1)))
        a_red = st.number_input("Rouges E", 0, 5, 0)

    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        min_actuelle = st.slider("Minute du match", 1, 95, 45)
    with c2:
        cote_pre_over25 = st.number_input("Cote Pré-Match Over 2.5", 1.10, 10.0, 1.80, help="Le système va calculer le Lambda automatiquement.")
    with c3:
        c_pre_n = st.number_input("Cote NUL Pré-Match", 1.10, 20.0, 3.20)

    # Calcul automatique du lambda de base
    l_base = find_lambda_from_over25(cote_pre_over25)
    
    stats_map = {
        'h_shots': h_shots, 'h_target': h_target, 'h_red': h_red, 
        'a_shots': a_shots, 'a_target': a_target, 'a_red': a_red, 'cote_pre_n': c_pre_n
    }
    
    l_dyn = calculate_advanced_lambda(l_base, stats_map, min_actuelle)
    temps_restant_pct = max((90 - min_actuelle), 2) / 90
    l_live = l_dyn * temps_restant_pct

    st.subheader("📊 Marchés Live")
    res_cols = st.columns(len([p for p in [0.5, 1.5, 2.5, 3.5, 4.5] if p > total_score_actuel]))
    
    idx = 0
    for p in [0.5, 1.5, 2.5, 3.5, 4.5]:
        if p > total_score_actuel:
            n_requis = int(p - total_score_actuel + 0.5) 
            prob_over = 1 - poisson.cdf(n_requis - 1, l_live)
            fair_cote = 1/prob_over if prob_over > 0.0001 else 999.0
            
            with res_cols[idx]:
                st.write(f"**Over {p}**")
                st.metric("Fair", f"{fair_cote:.2f}")
                bk_c = st.number_input(f"Bookie", value=round(fair_cote, 2), key=f"bk_{p}", step=0.01)
                edge = (prob_over * bk_c) - 1
                if edge > 0:
                    mise = (edge/(bk_c-1))*kelly_f*bk
                    st.success(f"Value: {edge:+.1%}\nMise: {max(0, mise):.0f}€")
                else: st.info("No Value")
            idx += 1

    st.divider()
    st.write(f"📈 **Configuration :** Lambda Initial (basé sur cote {cote_pre_over25}) = `{l_base:.2f}` | Lambda Live actuel = `{l_live:.2f}`")
