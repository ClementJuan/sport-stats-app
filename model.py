import streamlit as st
from scipy.stats import poisson

# Configuration de la page
st.set_page_config(page_title="Poisson Live Predictor", layout="centered")

st.title("⚽ Poisson Live Predictor")
st.write("Ajustez les curseurs pour voir la probabilité d'un but en direct.")

# --- BARRE LATÉRALE (INPUTS) ---
st.sidebar.header("Paramètres du match")
lambda_initial = st.sidebar.slider("Espérance de buts pré-match", 0.5, 5.0, 2.8)
minute = st.sidebar.slider("Minute actuelle", 1, 90, 75)
tirs_actuels = st.sidebar.number_input("Tirs cadrés cumulés (Live)", value=6)
tirs_attendus = st.sidebar.number_input("Tirs cadrés attendus à cette minute", value=5)

# --- LOGIQUE MATHÉMATIQUE ---
# Calcul de la pression
pression = tirs_actuels / tirs_attendus if tirs_attendus > 0 else 1

# Ajustement Lambda
temps_restant_pct = (90 - minute) / 90
lambda_ajuste = (lambda_initial * temps_restant_pct) * pression

# Calcul Poisson
prob_zero_but = poisson.pmf(0, lambda_ajuste)
prob_au_moins_un = 1 - prob_zero_but
cote_juste = 1 / prob_au_moins_un if prob_au_moins_un > 0 else 100

# --- AFFICHAGE DES RÉSULTATS ---
st.divider()
col1, col2 = st.columns(2)

with col1:
    st.metric("Probabilité d'un but", f"{prob_au_moins_un:.2%}")

with col2:
    st.metric("Cote minimale (Value)", f"{cote_juste:.2f}")

st.info(f"Indice de pression actuel : {pression:.2f}")
if pression > 1.2:
    st.success("🔥 Forte pression détectée !")
