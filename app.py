import streamlit as st
import sqlalchemy
from google.cloud.sql.connector import Connector
import pandas as pd
import json
import os

# --- CONFIGURATION ---
INSTANCE_NAME = "magazines-492101:us-central1:archives-magazines-2026"
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")  # Loaded from environment variables to protect credentials
DB_NAME = "archives_gaming"

# Configuration de l'esthétique "Musée"
st.set_page_config(page_title="Famitsu Digital Archive", layout="wide", page_icon="📜")

st.markdown("""
    <style>
    .main { background-color: #f5f5f5; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #ff4b4b; color: white; }
    .score-high { color: #28a745; font-weight: bold; }
    .score-med { color: #ffc107; font-weight: bold; }
    .score-low { color: #dc3545; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- CONNEXION SQL ---
@st.cache_resource
def init_connection():
    connector = Connector()
    def getconn():
        return connector.connect(INSTANCE_NAME, "pg8000", user=DB_USER, password=DB_PASS, db=DB_NAME)
    return sqlalchemy.create_engine("postgresql+pg8000://", creator=getconn)

engine = init_connection()

# --- CHARGEMENT DES DONNÉES ---
@st.cache_data(ttl=600)
def load_all_data():
    query = "SELECT id, filename, content, created_at FROM extractions ORDER BY created_at DESC"
    df = pd.read_sql(query, engine)
    df['data'] = df['content'].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    return df

try:
    df = load_all_data()
except Exception as e:
    st.error(f"Erreur de connexion à Cloud SQL : {e}")
    st.stop()

# --- SIDEBAR & FILTRES ---
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/Famitsu_logo.svg/512px-Famitsu_logo.svg.png", width=150)
st.sidebar.title("Archives Expert")
search_term = st.sidebar.text_input("🔍 Rechercher un jeu, un studio ou un nom...")
view_mode = st.sidebar.selectbox("Mode d'affichage", ["Galerie", "Tableau de données", "Analyse Chronologique"])

# --- FILTRAGE ---
filtered_df = df[df['content'].str.contains(search_term, case=False)] if search_term else df

# --- AFFICHAGE PRINCIPAL ---
st.title("📜 Famitsu Interactive Museum")
st.write(f"Affichage de **{len(filtered_df)}** numéros indexés.")

if view_mode == "Galerie":
    cols = st.columns(3)
    for i, (_, row) in enumerate(filtered_df.iterrows()):
        data = row['data']
        mag = data.get('magazine', {})
        
        with cols[i % 3]:
            with st.container(border=True):
                st.subheader(f"Issue {mag.get('issue', '??')}")
                st.write(f"📅 **Date :** {mag.get('date', 'Inconnu')}")
                
                # Aperçu des jeux
                reviews = data.get('cross_review', [])
                if reviews:
                    st.write("**Tests majeurs :**")
                    for game in reviews[:3]:
                        score = game.get('total_score', 0)
                        color_class = "score-high" if score >= 30 else "score-med" if score >= 20 else "score-low"
                        st.markdown(f"- {game.get('game', 'N/A')} : <span class='{color_class}'>{score}/40</span>", unsafe_allow_html=True)
                
                if st.button("Explorer le contenu", key=f"btn_{row['id']}"):
                    st.session_state['detail_id'] = row['id']

# --- FENÊTRE DE DÉTAILS (L'expérience Historien) ---
if 'detail_id' in st.session_state:
    detail_row = df[df['id'] == st.session_state['detail_id']].iloc[0]
    data = detail_row['data']
    
    st.divider()
    st.header(f"Exploration détaillée : {detail_row['filename']}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🎮 Cross Reviews", "👥 Staff & Journalistes", "📺 Publicités d'époque", "📝 Articles"])
    
    with tab1:
        st.write("### Notes de la rédaction")
        rev_df = pd.DataFrame(data.get('cross_review', []))
        if not rev_df.empty:
            st.table(rev_df)
            
    with tab2:
        st.write("### Équipe de rédaction")
        staff = data.get('staff', [])
        if staff:
            for member in staff:
                st.write(f"👤 **{member.get('name')}** - {member.get('role')}")
        else:
            st.write("Aucune donnée de staff extraite.")

    with tab3:
        st.write("### Archives Publicitaires")
        ads = data.get('ads', [])
        for ad in ads:
            st.info(f"**{ad.get('brand')}** : {ad.get('product')}\n\n*Note historien : {ad.get('description_fr')}*")

    with tab4:
        st.write("### Résumés des articles")
        articles = data.get('articles', [])
        for art in articles:
            with st.expander(art.get('title_original', 'Article sans titre')):
                st.write(art.get('summary_fr'))

elif view_mode == "Analyse Chronologique":
    st.write("### Évolution des scores au fil du temps")
    # On pourrait ici faire un graphique Altair ou Plotly avec les dates
    st.info("Ici, nous afficherons bientôt un graphique de tendance pour les studios sélectionnés.")