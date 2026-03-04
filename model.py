import streamlit as st
import requests
from scipy.stats import poisson

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Clé manquante dans les Secrets.")
    st.stop()

HOST = "football-prediction-api.p.rapidapi.com"
URL = f"https://{HOST}/api/v2/predictions"

st.set_page_config(page_title="Poisson Live Expert", layout="wide")

def get_data():
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": HOST}
    params = {"federation": "UEFA"}
    try:
        response = requests.get(URL, headers=headers, params=params)
        return response.json().get('data', []) if response.status_code == 200 else []
    except:
        return []

# --- INTERFACE ---
st.title("⚽ Poisson Expert : Stratégie & Bankroll")

# Sidebar pour la gestion de la Bankroll
st.sidebar.header("💰 Gestion de Bankroll")
total_bk = st.sidebar.number_input("Capital Total (€)", value=1000.0, step=50.0)
risk_factor = st.sidebar.slider("Prudence (Kelly Fractionnel)", 0.1, 1.0, 0.2, help="0.1 = très prudent, 1.0 = agressif")

if 'matchs' not in st.session_state:
    st.session_state.matchs = []

if st.button("🔄 Actualiser les matchs"):
    st.session_state.matchs = get_data()

if st.session_state.matchs:
    options = [f"{m['home_team']} vs {m['away_team']} ({m['competition_name']})" for m in st.session_state.matchs]
    selection = st.selectbox("Sélectionnez un match :", options)
    
    idx = options.index(selection)
    match = st.session_state.matchs[idx]
    cotes = match.get('odds', {})
    
    # --- CALCULATEUR ---
    col_in, col_out = st.columns(2)
    
    with col_in:
        st.subheader("🔧 Paramètres Live")
        val_x = float(cotes.get('X', 3.3)) if cotes.get('X') else 3.3
        lambda_auto = round((val_x * 0.5) + 0.5, 1) 
        
        l_base = st.number_input("Espérance de buts initiale", value=lambda_auto, step=0.1)
        minute = st.slider("Minute actuelle", 1, 90, 75)
        pression = st.slider("Coefficient de Pression", 0.5, 2.5, 1.0)
        
        st.info("ℹ️ Regardez la cote 'Plus de 0.5 but' sur votre bookmaker.")
        cote_bookmaker = st.number_input("Cote actuelle du Bookmaker", value=2.0, step=0.1)
        
    with col_out:
        st.subheader("🎯 Décision Automatique")
        temps_restant = (90 - minute) / 90
        l_live = (l_base * temps_restant) * pression
        prob_poisson = 1 - poisson.pmf(0, l_live)
        
        # Calcul de la Value
        cote_theorique = 1 / prob_poisson if prob_poisson > 0.01 else 100
        edge = (prob_poisson * cote_bookmaker) - 1
        
        if edge > 0:
            # Formule de Kelly : (Prob * Cote - 1) / (Cote - 1)
            kelly_brut = edge / (cote_bookmaker - 1)
            mise_suggeree = kelly_brut * risk_factor * 100 # En pourcentage
            montant_euros = (mise_suggeree / 100) * total_bk
            
            st.success(f"✅ VALUE DÉTECTÉE : {edge:.1%}")
            st.metric("MISE CONSEILLÉE", f"{mise_suggeree:.1f}%", f"{montant_euros:.2f} €")
            st.warning(f"🔔 Notification : Prenez le pari si la cote est ≥ {cote_theorique:.2f}")
        else:
            st.error("❌ PAS DE VALUE : La cote du bookmaker est trop basse.")
            st.write(f"Probabilité Poisson : {prob_poisson:.1%}")
            st.write(f"Cote minimale requise : {cote_theorique:.2f}")

else:
    st.info("Chargez les matchs pour commencer.")
