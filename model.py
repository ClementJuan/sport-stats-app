import streamlit as st
import requests
from scipy.stats import poisson

# --- CONFIGURATION ---
# Lecture de la clé depuis les Secrets Streamlit
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ La clé 'api_key' est manquante dans les Secrets. Allez dans Settings > Secrets.")
    st.stop()

HOST = "football-prediction-api.p.rapidapi.com"
URL = f"https://{HOST}/api/v2/predictions"

st.set_page_config(page_title="Poisson Live Predictor", layout="wide")

def get_data():
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": HOST
    }
    # On filtre sur l'UEFA pour avoir les matchs européens
    params = {"federation": "UEFA"}
    try:
        response = requests.get(URL, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            st.error(f"Erreur API : {response.status_code}")
            return []
    except Exception as e:
        st.error(f"Erreur de connexion : {e}")
        return []

# --- INTERFACE ---
st.title("⚽ Poisson Live Predictor")
st.write("Analyse en temps réel basée sur les données RapidAPI.")

# Utilisation du cache session pour ne pas vider ton quota (100/mois)
if 'matchs' not in st.session_state:
    st.session_state.matchs = []

if st.button("🔄 Charger les matchs du jour"):
    with st.spinner("Récupération des données..."):
        st.session_state.matchs = get_data()

if st.session_state.matchs:
    # On prépare la liste des matchs pour le menu
    options = [f"{m['home_team']} vs {m['away_team']} ({m['competition_name']})" for m in st.session_state.matchs]
    selection = st.selectbox("Sélectionnez un match :", options)
    
    idx = options.index(selection)
    match = st.session_state.matchs[idx]
    cotes = match.get('odds', {})
    
    st.subheader(f"📊 Cotes initiales (1X2)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Domicile (1)", cotes.get('1', 'N/A'))
    c2.metric("Nul (X)", cotes.get('X', 'N/A'))
    c3.metric("Extérieur (2)", cotes.get('2', 'N/A'))

    st.divider()

    # --- CALCULATEUR ---
    col_in, col_out = st.columns(2)
    
    with col_in:
        st.write("🔧 **Paramètres Live**")
        # Estimation automatique du Lambda basée sur la cote du nul
        val_x = float(cotes.get('X', 3.3)) if cotes.get('X') else 3.3
        lambda_auto = round((val_x * 0.5) + 0.5, 1) 
        
        l_base = st.number_input("Espérance de buts (Match complet)", value=lambda_auto, step=0.1)
        minute = st.slider("Minute actuelle", 1, 90, 75)
        pression = st.slider("Coefficient de Pression (Live)", 0.5, 2.5, 1.0, help="Augmentez si une équipe domine fort")
        
    with col_out:
        st.write("🎯 **Estimation Poisson**")
        temps_restant = (90 - minute) / 90
        l_live = (l_base * temps_restant) * pression
        
        # Formule de Poisson : Probabilité d'avoir au moins 1 but (1 - Prob(0 but))
        prob_but = 1 - poisson.pmf(0, l_live)
        cote_value = 1 / prob_but if prob_but > 0.01 else 100
        
        st.metric("Probabilité d'un BUT", f"{prob_but:.1%}")
        st.success(f"Cote 'Value' conseillée : {cote_value:.2f}")
        st.caption(f"Le modèle prévoit encore {l_live:.2f} buts potentiels.")

else:
    st.info("Cliquez sur le bouton pour charger les données de l'API.")
