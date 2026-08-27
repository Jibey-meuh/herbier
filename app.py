import streamlit as st
from groq import Groq
import requests
import json
import re

# Configuration de la page
st.set_page_config(page_title="Herbier médicinal intelligent", layout="wide")

# Initialisation du client Groq
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ------------------------------
# Fonctions utilitaires
# ------------------------------

def ask_groq(system_prompt, user_prompt, model="llama-3.3-70b-versatile"):
    """Envoie une requête à l'API Groq et retourne la réponse texte."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Erreur API Groq : {e}")
        return None

def extract_json(text):
    """Extrait le premier bloc JSON d'un texte."""
    if not text:
        return None
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        json_str = text[start:end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None
    return None

def get_country_suggestions(partial_name):
    """Retourne une liste de suggestions de pays basée sur la saisie partielle."""
    system = """Tu es un assistant géographique. L'utilisateur tape un début de nom de pays.
    Tu dois répondre uniquement par un tableau JSON de 5 noms de pays qui commencent par cette saisie (ou qui y ressemblent).
    Exemple de format : ["France", "Finlande", "Fidji"].
    Si peu de pays correspondent, mets-en moins."""
    user = f"Saisie partielle : {partial_name}"
    response = ask_groq(system, user)
    if response:
        suggestions = extract_json(response)
        if suggestions and isinstance(suggestions, list):
            return [s for s in suggestions if isinstance(s, str)]
    return []

def search_plants(country, maux):
    """Recherche des plantes médicinales pour un pays et des maux donnés."""
    system = """Tu es un expert en phytothérapie et botanique.
    L'utilisateur donne un pays et une liste de maux.
    Tu dois identifier des plantes médicinales qui poussent dans ce pays et qui sont traditionnellement utilisées pour ces maux.
    Réponds UNIQUEMENT avec un tableau JSON d'objets, chaque objet ayant les clés :
    - "nom_commun" (string)
    - "nom_scientifique" (string)
    - "saison" (string : printemps, été, automne, hiver, toute l'année, ou combinaison)
    - "description_courte" (string : une phrase)
    Si aucune plante ne correspond, renvoie [].
    Limite-toi à 10 plantes maximum."""
    user = f"Pays : {country}\nMaux : {', '.join(maux)}"
    response = ask_groq(system, user)
    if response:
        plants = extract_json(response)
        if plants is not None and isinstance(plants, list):
            valid_plants = []
            for p in plants:
                if isinstance(p, dict) and all(k in p for k in ["nom_commun", "nom_scientifique", "saison", "description_courte"]):
                    valid_plants.append(p)
            return valid_plants
    return []

def get_plant_details(nom_commun, nom_scientifique):
    """Génère une fiche détaillée pour une plante donnée."""
    system = """Tu es un botaniste et phytothérapeute expérimenté.
    Tu dois fournir une fiche complète sur la plante indiquée.
    La fiche doit être structurée en Markdown et contenir :
    - **Description botanique** : 2-3 phrases.
    - **Propriétés médicinales principales** : liste à puces.
    - **Modes d'utilisation pour extraire les principes actifs** : expliquer comment préparer (infusion, décoction, teinture, cataplasme, etc.) avec instructions précises.
    - **Saisons de récolte** : quand récolter la plante.
    - **Précautions d'emploi** : contre-indications éventuelles.
    - **Liens utiles** : deux liens vers des sites de référence (Wikipédia, PasseportSanté). URLs complètes et fonctionnelles.
    Utilise un ton professionnel et accessible."""
    user = f"Nom commun : {nom_commun}\nNom scientifique : {nom_scientifique}"
    response = ask_groq(system, user)
    return response if response else "Fiche non disponible."

def get_wikimedia_image(nom_scientifique):
    """Récupère une image libre de droits depuis Wikimedia Commons."""
    try:
        search_url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": nom_scientifique,
            "srnamespace": 6,
            "format": "json",
            "srlimit": 1
        }
        resp = requests.get(search_url, params=params, timeout=10).json()
        if 'query' in resp and resp['query']['search']:
            title = resp['query']['search'][0]['title']
            image_params = {
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json"
            }
            image_resp = requests.get("https://commons.wikimedia.org/w/api.php", params=image_params, timeout=10).json()
            pages = image_resp['query']['pages']
            for page in pages.values():
                if 'imageinfo' in page:
                    return page['imageinfo'][0]['url']
    except:
        pass
    return None

# ------------------------------
# Initialisation de l'état de session
# ------------------------------
if 'plants' not in st.session_state:
    st.session_state.plants = []
if 'selected_plant' not in st.session_state:
    st.session_state.selected_plant = None
if 'suggestions' not in st.session_state:
    st.session_state.suggestions = []
if 'country' not in st.session_state:
    st.session_state.country = ""
if 'maux_choisis' not in st.session_state:
    st.session_state.maux_choisis = []

# ------------------------------
# Interface utilisateur
# ------------------------------
st.title("🌿 Herbier médicinal mondial")
st.markdown("Recherchez des plantes médicinales par pays et par maux, puis obtenez une fiche détaillée.")

# --- Section pays avec autocomplétion ---
st.subheader("1. Choisissez un pays")
country_input = st.text_input("Pays (tapez au moins 2 caractères puis cliquez sur 'Suggestions')", 
                              value=st.session_state.country)

if len(country_input) >= 2 and st.button("Suggestions de pays"):
    with st.spinner("Recherche de suggestions..."):
        suggestions = get_country_suggestions(country_input)
        st.session_state.suggestions = suggestions

if st.session_state.suggestions:
    st.write("Suggestions :")
    cols = st.columns(min(len(st.session_state.suggestions), 5))
    for idx, sugg in enumerate(st.session_state.suggestions):
        col = cols[idx % len(cols)]
        if col.button(sugg, key=f"sugg_{idx}"):
            st.session_state.country = sugg
            st.session_state.suggestions = []
            st.rerun()

if st.session_state.country:
    country_input = st.session_state.country

# --- Section maux ---
st.subheader("2. Sélectionnez les maux à traiter")
maux_options = [
    "Ballonnement", 
    "Régulation hormonale SPM", 
    "Sommeil", 
    "Stress", 
    "Digestion difficile", 
    "Fatigue", 
    "Anxiété", 
    "Douleurs articulaires",
    "Maux de tête",
    "Problèmes de peau"
]
maux_choisis = st.multiselect("Maux (plusieurs choix possibles)", maux_options, default=st.session_state.maux_choisis)

# --- Bouton de recherche ---
if st.button("🔍 Rechercher les plantes", type="primary"):
    if not country_input:
        st.warning("Veuillez choisir un pays.")
    elif not maux_choisis:
        st.warning("Veuillez sélectionner au moins un mal.")
    else:
        with st.spinner("Recherche des plantes en cours..."):
            plants = search_plants(country_input, maux_choisis)
            st.session_state.plants = plants
            st.session_state.selected_plant = None
            st.session_state.maux_choisis = maux_choisis
            if plants:
                st.success(f"{len(plants)} plante(s) trouvée(s)")
            else:
                st.info("Aucune plante trouvée pour ces critères.")

# --- Affichage des plantes et tri par saison ---
if st.session_state.plants:
    st.markdown("---")
    st.subheader("3. Plantes trouvées")
    
    saison_filter = st.selectbox("Filtrer par saison", 
                                 ["Toutes saisons", "Printemps", "Été", "Automne", "Hiver", "Toute l'année"])
    filtered_plants = st.session_state.plants
    if saison_filter != "Toutes saisons":
        filtered_plants = [p for p in filtered_plants if saison_filter.lower() in p.get('saison', '').lower()]
    
    if not filtered_plants:
        st.info("Aucune plante ne correspond à cette saison.")
    else:
        for i, plant in enumerate(filtered_plants):
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("Voir fiche", key=f"btn_{i}"):
                    st.session_state.selected_plant = plant
                    st.rerun()
            with col2:
                st.write(f"**{plant.get('nom_commun', 'N/A')}** (*{plant.get('nom_scientifique', '')}*)")
                st.caption(f"Saison : {plant.get('saison', 'N/A')}")
                st.write(plant.get('description_courte', ''))

# --- Fiche détaillée ---
if st.session_state.selected_plant:
    plant = st.session_state.selected_plant
    st.markdown("---")
    st.header(f"🌱 {plant.get('nom_commun', 'Plante')}")
    st.subheader(f"*{plant.get('nom_scientifique', '')}*")
    
    image_url = get_wikimedia_image(plant.get('nom_scientifique', ''))
    if image_url:
        st.image(image_url, width=400, caption=plant.get('nom_commun', ''))
    else:
        st.write("Image non disponible pour cette plante.")
    
    with st.spinner("Génération de la fiche détaillée..."):
        fiche = get_plant_details(plant.get('nom_commun', ''), plant.get('nom_scientifique', ''))
        if fiche:
            st.markdown(fiche)
        else:
            st.error("Impossible de générer la fiche.")