import streamlit as st
import requests
from scipy.stats import poisson

# --- CONFIGURATION ---
API_KEY = st.secrets["api_key"]
HOST = "football-prediction-api.p.rapidapi.com"
URL = f"https://{HOST}/api/v2/predictions"

st.set_page_config(page_title="Poisson Live Predictor", layout="wide")

def get_data():
    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": HOST
    }
    params = {"federation": "UEFA"}
    try:
        response = requests.get(URL, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get('data', [])
        return []
    except:
        return []

# --- INTERFACE ---
st.title("⚽ Poisson Live Predictor")

if 'matchs' not in st.session_state:
    st.session_state.matchs = []

if st.button("🔄 Charger les matchs UEFA"):
    st.session_state.matchs = get_data()

if st.session_state.matchs:
    # Création de la liste de sélection
    options = [f"{m['home_team']} vs {m['away_team']} ({m['competition_name']})" for m in st.session_state.matchs]
    selection = st.selectbox("Sélectionnez votre match :", options)
    
    idx = options.index(selection)
    match = st.session_state.matchs[idx]
    
    # Extraction des cotes pour affichage
    cotes = match.get('odds', {})
    
    st.subheader(f"📊 Analyse de départ : {selection}")
    col_c1, col_c2, col_c3 = st.columns(3)
    col_c1.metric("Cote Dom (1)", cotes.get('1', 'N/A'))
    col_c2.metric("Cote Nul (X)", cotes.get('X', 'N/A'))
    col_c3.metric("Cote Ext (2)", cotes.get('2', 'N/A'))

    st.divider()

    # --- CALCULATEUR ---
    col_in, col_out = st.columns(2)
    
    with col_in:
        st.write("🔧 **Ajustement du modèle**")
        # On estime un lambda de base selon la cote du nul
        # Si cote X = 3.0 -> Lambda ~ 2.2 | Si cote X = 4.0 -> Lambda ~ 3.0
        val_x = float(cotes.get('X', 3.3))
        lambda_auto = round((val_x * 0.5) + 0.5, 1) 
        
        l_base = st.number_input("Espérance de buts initiale", value=lambda_auto, step=0.1)
        minute = st.slider("Minute actuelle", 1, 90, 75)
        pression = st.slider("Coefficient de Pression (Live)", 0.5, 2.5, 1.0)
        
    with col_out:
        st.write("🎯 **Résultat Poisson**")
        temps_restant = (90 - minute) / 90
        l_live = (l_base * temps_restant) * pression
        
        prob_but = 1 - poisson.pmf(0, l_live)
        cote_value = 1 / prob_but if prob_but > 0.01 else 100
        
        st.metric("Probabilité d'un but", f"{prob_but:.1%}")
        st.success(f"Cote 'Value' conseillée : {cote_value:.2f}")
        
        st.write(f"Estimation du Lambda live : **{l_live:.2f}**")
else:
    st.info("Utilisez le bouton charger pour voir les matchs.")
