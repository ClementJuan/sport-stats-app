import streamlit as st
import requests
from scipy.stats import poisson

# --- CONFIGURATION ---
try:
    # On utilise ta clé RapidAPI actuelle (plan gratuit)
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Clé 'api_key' manquante dans les Secrets Streamlit.")
    st.stop()

HOST = "football-prediction-api.p.rapidapi.com"
URL = f"https://{HOST}/api/v2/predictions"

st.set_page_config(page_title="Poisson Live Zero-Budget", layout="wide")

# --- FONCTION API (LISTE DES MATCHS) ---
@st.cache_data(ttl=300)
def get_matches(key):
    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": HOST
    }
    try:
        # On filtre sur l'UEFA pour limiter la consommation du quota
        response = requests.get(URL, headers=headers, params={"federation": "UEFA"}, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', [])
        return []
    except:
        return []

# --- CALCULATEUR DE DYNAMIQUE ---
def get_dynamic_lambda(base_l, tirs, corners, possession, minute):
    """
    Ajuste le Lambda (espérance de buts) en fonction des stats saisies.
    Logique : 1 tir cadré toutes les 15 min est la norme.
    """
    modifier = 1.0
    
    # Bonus Tirs Cadrés (Pression offensive directe)
    seuil_tirs = minute / 15
    if tirs > seuil_tirs:
        modifier += (tirs - seuil_tirs) * 0.12
    
    # Bonus Corners (Domination territoriale)
    seuil_corners = minute / 12
    if corners > seuil_corners:
        modifier += 0.08
        
    # Bonus Possession
    if possession > 62:
        modifier += 0.1
    elif possession < 38:
        modifier += 0.05 # Contre-attaques dangereuses
        
    return base_l * modifier

# --- INTERFACE ---
st.title("⚽ Poisson Live : Stratégie Indépendante")
st.caption("Version optimisée : Stats manuelles pour éviter les abonnements payants.")

# Sidebar : Gestion de Bankroll
with st.sidebar:
    st.header("💰 Bankroll Management")
    bk_totale = st.number_input("Capital (€)", value=1000.0, step=50.0)
    fraction_kelly = st.slider("Prudence (Kelly Fractionnel)", 0.1, 1.0, 0.25, help="0.25 = Très recommandé")
    st.divider()
    st.info("💡 Conseil : Ouvrez Flashscore à côté pour reporter les tirs et corners en 2 secondes.")

# Chargement des matchs
if st.button("🔄 Charger les matchs du jour"):
    st.session_state.matchs = get_matches(API_KEY)

if 'matchs' in st.session_state and st.session_state.matchs:
    options = [f"{m['home_team']} vs {m['away_team']} ({m['competition_name']})" for m in st.session_state.matchs]
    selection = st.selectbox("Sélectionnez le match à analyser :", options)
    
    idx = options.index(selection)
    match = st.session_state.matchs[idx]
    
    # Calcul du Lambda de base selon l'IA de l'API (Score prévu)
    try:
        score_pref = match.get('prediction_score', '1-1')
        l_base_ia = sum([int(x) for x in score_pref.split('-')])
    except:
        l_base_ia = 2.8

    st.divider()

    col1, col2, col3 = st.columns(3)

    # 1. ENTREE DES STATS LIVE (Manuel = Gratuit & Ultra-Précis)
    with col1:
        st.subheader("📊 Stats en Direct")
        minute = st.slider("Minute du match", 1, 90, 75)
        tirs_cadres = st.number_input("Tirs cadrés totaux (2 éq.)", value=5, min_value=0)
        corners = st.number_input("Corners totaux (2 éq.)", value=4, min_value=0)
        possession = st.slider("Possession de l'équipe dominante (%)", 50, 85, 55)

    # 2. ANALYSE POISSON
    with col2:
        st.subheader("🧠 Modèle Poisson")
        l_dynamique = get_dynamic_lambda(l_base_ia, tirs_cadres, corners, possession, minute)
        
        # Temps restant effectif
        temps_restant = max((90 - minute) / 90, 0.05)
        l_live = l_dynamique * temps_restant
        
        prob_but = 1 - poisson.pmf(0, l_live)
        cote_fair = 1 / prob_but if prob_but > 0.01 else 100
        
        st.metric("Lambda Ajusté", f"{l_dynamique:.2f}", f"{l_dynamique - l_base_ia:+.2f}")
        st.metric("Probabilité d'un BUT", f"{prob_but:.1%}")
        st.info(f"Cote 'Fair' (Rentable à) : **{cote_fair:.2f}**")

    # 3. DECISION & MISE
    with col3:
        st.subheader("💸 Stratégie de Mise")
        cote_bookie = st.number_input("Cote actuelle du Bookmaker", value=2.20, step=0.05)
        
        edge = (prob_but * cote_bookie) - 1
        
        if edge > 0:
            kelly = (edge / (cote_bookie - 1)) * fraction_kelly
            montant_mise = kelly * bk_totale
            
            st.success(f"✅ SIGNAL : VALUE DÉTECTÉE (+{edge:.1%})")
            st.metric("MISE RECOMMANDÉE", f"{montant_mise:.2f} €", f"{kelly*100:.1f}% BK")
            if edge > 0.2:
                st.balloons()
        else:
            st.error(f"❌ AUCUNE VALUE (Edge : {edge:.1%})")
            st.warning(f"Attendez que la cote monte au-dessus de **{cote_fair:.2f}**")

else:
    st.info("Cliquez sur le bouton pour récupérer les matchs via votre quota RapidAPI gratuit.")
