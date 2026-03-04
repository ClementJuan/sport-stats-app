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
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            st.error(f"Erreur SofaScore : Code {response.status_code}")
            return None
            
        soup = BeautifulSoup(response.text, 'html.parser')
        page_title = soup.find('title').get_text() if soup.find('title') else ""
        
        teams = ["Domicile", "Extérieur"]
        if " - " in page_title:
            teams = page_title.split(" live")[0].split(" - ")
        
        h_score = 0
        a_score = 0
        score_match = re.search(r'(\d+)\s*-\s*(\d+)', page_title)
        if score_match:
            h_score = int(score_match.group(1))
            a_score = int(score_match.group(2))

        data = {
            "home_team": teams[0].strip(),
            "away_team": teams[1].strip() if len(teams) > 1 else "Extérieur",
            "home_score": h_score,
            "away_score": a_score,
            "h_shots": 0,
            "a_shots": 0,
            "h_target": 0,
            "a_target": 0,
            "h_poss": 50
        }
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

# --- CALCULATEUR AFFINÉ ---
def calculate_advanced_lambda(base_l, stats, minute):
    # Sécurisation des accès
    h_t = stats.get('h_target', 0)
    h_s = stats.get('h_shots', 0)
    a_t = stats.get('a_target', 0)
    a_s = stats.get('a_shots', 0)
    
    # 1. Normalisation de la pression par minute
    # On compare la cadence actuelle à une cadence "normale" (environ 1 tir toutes les 8 min)
    cadence_normale = minute / 8 if minute > 0 else 1
    
    danger_h = ((h_t * 1.5 + (h_s - h_t) * 0.5) / cadence_normale) - 1.0 if minute > 10 else 0
    danger_a = ((a_t * 1.5 + (a_s - a_t) * 0.5) / cadence_normale) - 1.0 if minute > 10 else 0
    
    # On bride l'impact de la pression (max +30% ou -20% par équipe)
    danger_h = max(-0.2, min(0.3, danger_h * 0.1))
    danger_a = max(-0.2, min(0.3, danger_a * 0.1))
    
    # 2. Facteur Talent (Cotes pré-match)
    c_h = stats.get('cote_pre_h', 1.8)
    c_a = stats.get('cote_pre_a', 3.5)
    c_n = stats.get('cote_pre_n', 3.2)
    
    # 3. Draw Bias (Biais du nul)
    draw_factor = 1.0 + (c_n - 3.20) * 0.05
    draw_factor = max(0.92, min(1.10, draw_factor)) 
    
    # 4. Calcul final du multiplicateur
    # On additionne les facteurs. Si neutre, multiplicateur = 1.0
    multiplier = 1.0 + danger_h + danger_a
    
    # Malus carton rouge
    red_penalty = (stats.get('h_red', 0) + stats.get('a_red', 0)) * 0.15
    multiplier -= red_penalty
    
    # Sécurité ultime : Le Lambda final ne peut pas être > 4.5 ou < 1.2
    final_l = base_l * multiplier * draw_factor
    return max(1.2, min(4.5, final_l))

# --- UI STREAMLIT ---
st.title("⚽ Poisson Live Pro Scanner")
st.caption("Version 2.0 : Algorithme de Pression Normalisé (Anti-Inflation)")

if 'live_data' not in st.session_state:
    st.session_state.live_data = None

with st.sidebar:
    st.header("💳 Bankroll")
    bk = st.number_input("Capital (€)", value=1000.0)
    kelly_f = st.slider("Fraction Kelly", 0.1, 1.0, 0.25)
    st.divider()
    source_mode = st.radio("Source :", ["API Live (Recommandé)", "URL SofaScore (Léger)"])

selected_match = None

if source_mode == "URL SofaScore (Léger)":
    url = st.text_input("Lien SofaScore du match :", placeholder="https://www.sofascore.com/fr/match-equipe...")
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
    h_name = selected_match.get('home_team', 'Dom')
    a_name = selected_match.get('away_team', 'Ext')
    h_score = selected_match.get('home_score', 0)
    a_score = selected_match.get('away_score', 0)
    total_score_actuel = h_score + a_score
    
    st.header(f"{h_name} {h_score} - {a_score} {a_name}")
    
    col_n1, col_n2, col_n3 = st.columns(3)
    with col_n2:
        c_pre_n = st.number_input("Cote NUL", 1.01, 20.0, 3.20)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🏠 Domicile")
        c_pre_h = st.number_input("Cote Dom.", 1.01, 50.0, 1.80)
        h_shots = st.number_input("Tirs D", 0, 50, int(selected_match.get('h_shots', 5)))
        h_target = st.number_input("Cadrés D", 0, 50, int(selected_match.get('h_target', 2)))
        h_red = st.number_input("Rouges D", 0, 5, 0)
    with col2:
        st.subheader("🚀 Extérieur")
        c_pre_a = st.number_input("Cote Ext.", 1.01, 50.0, 3.50)
        a_shots = st.number_input("Tirs E", 0, 50, int(selected_match.get('a_shots', 3)))
        a_target = st.number_input("Cadrés E", 0, 50, int(selected_match.get('a_target', 1)))
        a_red = st.number_input("Rouges E", 0, 5, 0)

    st.divider()
    c_left, c_right = st.columns([1, 2])
    with c_left:
        min_actuelle = st.slider("Minute", 1, 95, 45)
        l_base = st.number_input("Lambda pré-match", 0.1, 10.0, 3.35)
        st.caption("Rappel : Cote 1.50 sur +2.5 = Lambda 3.35")
    
    stats_map = {
        'h_shots': h_shots, 'h_target': h_target, 'h_red': h_red, 'cote_pre_h': c_pre_h, 
        'a_shots': a_shots, 'a_target': a_target, 'a_red': a_red, 'cote_pre_a': c_pre_a, 'cote_pre_n': c_pre_n
    }
    
    l_dyn = calculate_advanced_lambda(l_base, stats_map, min_actuelle)
    temps_restant_pct = max((90 - min_actuelle), 2) / 90
    l_live = l_dyn * temps_restant_pct

    with c_right:
        st.subheader("📊 Résultats")
        paliers = [0.5, 1.5, 2.5, 3.5, 4.5]
        for p in paliers:
            if p > total_score_actuel:
                n_requis = int(p - total_score_actuel + 0.5) 
                prob_over = 1 - poisson.cdf(n_requis - 1, l_live)
                fair_cote = 1/prob_over if prob_over > 0.0001 else 999.0
                
                with st.expander(f"Over {p}", expanded=(p == total_score_actuel + 1.5)):
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Prob", f"{prob_over:.1%}")
                    m2.metric("Fair", f"{fair_cote:.2f}")
                    with m3:
                        bk_c = st.number_input(f"Cote BK {p}", value=round(fair_cote * 1.1, 2), key=f"bk_{p}", step=0.01)
                        edge = (prob_over * bk_c) - 1
                        if edge > 0:
                            st.success(f"VALUE: {edge:+.1%}")
                            mise = (edge/(bk_c-1))*kelly_f*bk
                            st.write(f"**Mise: {max(0, mise):.2f}€**")
                        else: st.write("No Value")
            else: st.write(f"✅ Over {p} OK")

    st.divider()
    st.info(f"Lambda : {l_dyn:.2f} (Base {l_base}) | Lambda Live : {l_live:.2f}")
