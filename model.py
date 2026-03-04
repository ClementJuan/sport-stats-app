import streamlit as st
from scipy.stats import poisson
import time

st.set_page_config(page_title="Poisson Live Dashboard", layout="wide")

st.title("⚽ Poisson Live Predictor - Mode Simulation")

# --- PARAMÈTRES DE BASE ---
col_cfg1, col_cfg2 = st.columns(2)
with col_cfg1:
    lambda_init = st.number_input("Espérance de buts initiale (Match entier)", value=2.5)
with col_cfg2:
    vitesse = st.select_slider("Vitesse de simulation", options=[1, 2, 5, 10], value=1)

# --- INITIALISATION DE LA SIMULATION ---
if 'minute_sim' not in st.session_state:
    st.session_state.minute_sim = 1
if 'tirs_sim' not in st.session_state:
    st.session_state.tirs_sim = 0

btn_play = st.button("▶️ Lancer / Reprendre le match")

# --- BOUCLE DE SIMULATION ---
if btn_play:
    # On crée un espace vide pour mettre à jour les données sans recharger toute la page
    placeholder = st.empty()
    
    for m in range(st.session_state.minute_sim, 91):
        st.session_state.minute_sim = m
        # On simule un tir cadré de temps en temps (aléatoire pour le test)
        if m % 12 == 0: 
            st.session_state.tirs_sim += 1
            
        # --- CALCULS MATHÉMATIQUES ---
        tirs_attendus = (m / 90) * 8 # On estime qu'on attend 8 tirs par match
        pression = st.session_state.tirs_sim / tirs_attendus if tirs_attendus > 0 else 1
        
        temps_restant_pct = (90 - m) / 90
        lambda_ajuste = (lambda_init * temps_restant_pct) * pression
        
        prob_but = 1 - poisson.pmf(0, lambda_ajuste)
        cote_juste = 1 / prob_but if prob_but > 0.01 else 100

        # --- AFFICHAGE DYNAMIQUE ---
        with placeholder.container():
            st.subheader(f"⏱️ Chronomètre : {m}'")
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Tirs Cadrés", st.session_state.tirs_sim)
            c2.metric("Probabilité prochain but", f"{prob_but:.1%}")
            c3.metric("Cote Value", f"{cote_juste:.2f}")
            
            # Barre de progression du match
            st.progress(m / 90)
            
            if pression > 1.3:
                st.warning(f"⚠️ Alerte Pression : {pression:.2f} (Le match s'emballe !)")
        
        time.sleep(1 / vitesse) # On attend avant la minute suivante
