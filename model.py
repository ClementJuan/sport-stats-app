import streamlit as st
import requests
from scipy.stats import poisson
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time

# --- CONFIGURATION ---
try:
    API_KEY = st.secrets["api_key"]
except KeyError:
    st.error("⚠️ Clé 'api_key' manquante dans les Secrets Streamlit.")
    st.stop()

st.set_page_config(page_title="Poisson Live - Sofa Edition", layout="wide")

# --- MOTEUR DE SCRAPING OPTIMISÉ SOFASCORE ---
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # User-agent récent pour éviter la détection robot
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def scrape_sofascore(url):
    """
    Extrait les données réelles de la page SofaScore.
    """
    driver = get_driver()
    try:
        driver.get(url)
        # Attente pour le chargement des éléments statistiques
        wait = WebDriverWait(driver, 15)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[class*="Box"]')))
        
        # Faire défiler un peu pour forcer le chargement de certains composants si nécessaire
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(2)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # --- EXTRACTION DES DONNÉES ---
        data = {
            "minute": 0,
            "tirs_cadres": 0,
            "corners": 0,
            "possession": 50,
            "score": "0-0",
            "source": "SofaScore Live"
        }

        # 1. Extraction du Score et de la Minute
        # Note: SofaScore change souvent ses classes, on cherche des motifs textuels ou des balises sémantiques
        try:
            # Recherche de la minute (souvent dans un span avec une classe contenant 'Time')
            time_elem = soup.find("span", text=re.compile(r"^\d+'$"))
            if time_elem:
                data["minute"] = int(time_elem.text.replace("'", ""))
            else:
                # Fallback si minute non trouvée (ex: 75:00)
                time_elem = soup.select_one('span[class*="Time"]')
                if time_elem:
                    data["minute"] = int(re.search(r"\d+", time_elem.text).group())
        except: pass

        # 2. Extraction du Score
        try:
            score_elems = soup.select('span[class*="Score"]') # Souvent deux éléments
            if len(score_elems) >= 2:
                data["score"] = f"{score_elems[0].text}-{score_elems[1].text}"
        except: pass

        # 3. Extraction des Statistiques (Tirs cadrés, Corners, Possession)
        # SofaScore affiche les stats dans des lignes de tableau ou des divs flexibles
        stat_rows = soup.select('div[class*="StatRow"]') # Classe générique probable
        for row in stat_rows:
            label = row.text.lower()
            values = row.select('span') # Valeurs gauche et droite
            
            if "shots on target" in label or "tirs cadrés" in label:
                v1 = int(values[0].text) if values[0].text.isdigit() else 0
                v2 = int(values[-1].text) if values[-1].text.isdigit() else 0
                data["tirs_cadres"] = v1 + v2
            
            elif "corner" in label:
                v1 = int(values[0].text) if values[0].text.isdigit() else 0
                v2 = int(values[-1].text) if values[-1].text.isdigit() else 0
                data["corners"] = v1 + v2
                
            elif "possession" in label:
                # On prend la possession de l'équipe à domicile par défaut pour le calcul
                p_text = values[0].text.replace("%", "")
                data["possession"] = int(p_text) if p_text.isdigit() else 50

        driver.quit()
        return data
    except Exception as e:
        st.error(f"Erreur d'extraction : {e}")
        if driver: driver.quit()
        return None

# --- CALCULATEUR DYNAMIQUE ---
def get_dynamic_lambda(base_l, stats):
    modifier = 1.0
    # On s'assure que minute n'est pas 0 pour éviter la division par zero
    min_ = max(stats['minute'], 1)
    tirs = stats['tirs_cadres']
    corners = stats['corners']
    
    # Algorithme de pression : Intensité par rapport au temps écoulé
    # Seuil pro : 1 tir cadré / 10 min = Danger imminent
    if tirs > (min_ / 10): 
        modifier += (tirs - (min_/10)) * 0.15
    
    # Seuil pro : 1 corner / 8 min = Pression constante
    if corners > (min_ / 8):
        modifier += 0.10
        
    # Domination territoriale (Possession > 60% ou < 40% pour les contres)
    if stats['possession'] > 60 or stats['possession'] < 40:
        modifier += 0.10
        
    return base_l * modifier

# --- INTERFACE ---
st.title("🚀 Poisson Live : SofaScore Edition")
st.caption("Synchronisation automatique des statistiques via Scraping | Précision Mathématique")

with st.sidebar:
    st.header("💰 Gestion Capital")
    bk_totale = st.number_input("Capital (€)", value=1000.0)
    fraction_kelly = st.slider("Prudence (Kelly)", 0.1, 1.0, 0.25)
    
    st.divider()
    st.subheader("🔗 Lien du Match")
    url_input = st.text_input("URL SofaScore du match en direct :", 
                             placeholder="https://www.sofascore.com/team-a-team-b/...")
    
    if st.button("🛰️ Lancer l'Analyse Automatique"):
        if "sofascore.com" in url_input:
            with st.spinner("Récupération des données en temps réel..."):
                st.session_state.current_stats = scrape_sofascore(url_input)
        else:
            st.error("Veuillez entrer une URL SofaScore valide.")

# --- AFFICHAGE ET CALCULS ---
if 'current_stats' in st.session_state and st.session_state.current_stats:
    s = st.session_state.current_stats
    
    # Alertes de sécurité si les données sont vides
    if s['minute'] == 0 and s['tirs_cadres'] == 0:
        st.warning("⚠️ Les données semblent vides. Vérifiez que le match a bien commencé ou que l'URL est correcte.")

    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader(f"🏟️ Live : {s['score']}")
        st.write(f"⏱️ **Minute :** {s['minute']}'")
        st.write(f"🎯 **Tirs Cadrés :** {s['tirs_cadres']}")
        st.write(f"⛳ **Corners :** {s['corners']}")
        st.write(f"🔄 **Possession :** {s['possession']}%")
        
    with col2:
        st.subheader("🧠 Analyse Poisson")
        l_base = st.number_input("Lambda pré-match (Moyenne buts)", value=2.8, step=0.1)
        l_dyn = get_dynamic_lambda(l_base, s)
        
        rem_time = max((90 - s['minute']) / 90, 0.05)
        l_live = l_dyn * rem_time
        
        prob_but = 1 - poisson.pmf(0, l_live)
        fair_cote = 1 / prob_but if prob_but > 0.01 else 100
        
        st.metric("Lambda Dynamique", f"{l_dyn:.2f}", f"{l_dyn - l_base:+.2f}")
        st.metric("Probabilité d'un but", f"{prob_but:.1%}")
        st.write(f"Cote 'Fair' : **{fair_cote:.2f}**")

    with col3:
        st.subheader("💸 Stratégie Value")
        cote_in = st.number_input("Cote Bookmaker (+0.5, +1.5...)", value=2.20, step=0.05)
        
        edge = (prob_but * cote_in) - 1
        
        if edge > 0:
            kelly = (edge / (cote_in - 1)) * fraction_kelly
            mise = kelly * bk_totale
            st.success(f"✅ VALUE DÉTECTÉE : +{edge:.1%}")
            st.metric("MISE CONSEILLÉE", f"{mise:.2f} €", f"{kelly*100:.1f}% BK")
            if edge > 0.15: st.balloons()
        else:
            st.error(f"❌ PAS DE VALUE")
            st.info(f"Pari rentable si la cote monte à **{fair_cote:.2f}**")

else:
    st.info("Collez l'URL d'un match en direct de SofaScore pour lancer le calcul automatique.")
