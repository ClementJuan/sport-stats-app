import streamlit as st
import requests
from scipy.stats import poisson

# --- CONFIGURATION SÉCURISÉE ---
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Erreur : Clé API manquante dans les Secrets Streamlit.")
    st.stop()

HOST = "football-prediction-api.p.rapidapi.com"
URL = f"https://{HOST}/api/v2/predictions"

st.set_page_config(page_title="Poisson Live Expert", layout="wide", initial_sidebar_state="expanded")

# --- STYLE CSS PERSONNALISÉ ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; padding: 15px; border-radius: 10px; border: 1px solid #30363d; }
    </style>
    """, unsafe_allow_html=True)

def get_data():
    headers = {"X-RapidAPI-Key": API_KEY, "X-RapidAPI-Host": HOST}
    params = {"federation": "UEFA"}
    try:
        response = requests.get(URL, headers=headers, params=params)
        return response.json().get('data', []) if response.status_code == 200 else []
    except: return []

# --- SIDEBAR : GESTION DE BANKROLL ---
st.sidebar.title("💰 Ma Bankroll")
bk_totale = st.sidebar.number_input("Capital (€)", value=1000.0, step=50.0)
fraction_kelly = st.sidebar.slider("Prudence (Fraction de Kelly)", 0.1, 1.0, 0.25, help="0.25 est conseillé pour une gestion saine.")

# --- CORPS DE L'APPLI ---
st.title("⚽ Poisson Live Expert")
st.caption("Système d'aide à la décision en temps réel")

if 'matchs' not in st.session_state: st.session_state.matchs = []
if st.button("🔄 Actualiser les matchs UEFA"):
    with st.spinner("Chargement..."): st.session_state.matchs = get_data()

if st.session_state.matchs:
    options = [f"{m['home_team']} vs {m['away_team']} ({m['competition_name']})" for m in st.session_state.matchs]
    selection = st.selectbox("Match à analyser :", options)
    match = st.session_state.matchs[options.index(selection)]
    cotes = match.get('odds', {})

    col1, col2 = st.columns([1, 1.2])

    with col1:
        st.subheader("🛠️ Paramètres Live")
        val_x = float(cotes.get('X', 3.3)) if cotes.get('X') else 3.3
        l_base = st.number_input("Espérance de buts initiale", value=round((val_x*0.5)+0.5, 1), step=0.1)
        minute = st.slider("Minute du match", 1, 90, 75)
        pression = st.slider("Coefficient de Pression", 0.5, 3.0, 1.0)
        
        st.divider()
        st.write("🏦 **Données Bookmaker**")
        cote_bk = st.number_input("Cote 'Plus de 0,5 but' actuelle", value=2.0, step=0.05)

    with col2:
        st.subheader("🎯 Analyse & Décision")
        t_restant = (90 - minute) / 90
        l_live = (l_base * t_restant) * pression
        prob_poisson = 1 - poisson.pmf(0, l_live)
        cote_fair = 1 / prob_poisson if prob_poisson > 0.01 else 100
        
        # Calcul de la Value (Edge)
        edge = (prob_poisson * cote_bk) - 1
        
        st.metric("Probabilité Poisson", f"{prob_poisson:.1%}")
        
        if edge > 0:
            # Kelly = (bp - q) / b  où b = cote-1
            kelly_full = edge / (cote_bk - 1)
            pct_mise = kelly_full * fraction_kelly * 100
            montant = (pct_mise / 100) * bk_totale
            
            st.success(f"✅ VALUE DÉTECTÉE : +{edge:.1%}")
            st.metric("MISE RECOMMANDÉE", f"{pct_mise:.1f}%", f"{montant:.2f} €")
            st.info(f"🔔 Notification : Prenez le pari ! Votre cote ({cote_bk}) est supérieure à la cote fair ({cote_fair:.2f})")
        else:
            st.error(f"❌ AUCUNE VALUE (Edge : {edge:.1%})")
            st.write(f"Attendez que la cote monte à au moins **{cote_fair:.2f}**")
else:
    st.info("Cliquez sur le bouton pour charger les matchs.")
