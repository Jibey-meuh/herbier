import streamlit as st
from groq import Groq
import requests
import json
import re
from datetime import datetime

# Configuration de la page
st.set_page_config(page_title="Herbier médicinal intelligent", layout="wide")

# Initialisation du client Groq
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ------------------------------
# Fonctions utilitaires
# ------------------------------

def ask_groq(system_prompt, user_prompt, model="llama-3.3-70b-versatile", temperature=0.7, max_tokens=1500):
    """Envoie une requête à l'API Groq et retourne la réponse texte."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content
    except Exception as e:
        # Fallback si le modèle principal échoue
        try:
            response = client.chat.completions.create(
                model="llama-3.2-3b-preview",  # Modèle de secours
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )

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

def get_location_suggestions(partial_name):
    """Retourne une liste de suggestions de pays ou villes basée sur la saisie partielle."""
    system = """Tu es un assistant géographique. L'utilisateur tape un début de nom de lieu (pays ou ville).
    Réponds UNIQUEMENT avec un tableau JSON de 5 suggestions de noms de lieux (pays ou ville) qui commencent par cette saisie ou y ressemblent.
    Exemple : ["France", "Finlande", "Fidji"].
    Si peu de correspondances, renvoie moins de 5."""
    user = f"Saisie partielle : {partial_name}"
    response = ask_groq(system, user, model="llama-3.3-70b-versatile", max_tokens=200)
    if response:
        suggestions = extract_json(response)
        if suggestions and isinstance(suggestions, list):
            return [s for s in suggestions if isinstance(s, str)]
    return []

def search_plants(location, maux):
    """Recherche 5 plantes médicinales adaptées au lieu, aux maux et à la saison actuelle."""
    today = datetime.now().strftime("%d/%m/%Y")
    system = """Tu es un expert en phytothérapie et botanique.
    L'utilisateur indique un lieu (pays ou ville) et une liste de maux.
    Tu dois déterminer la saison actuelle dans ce lieu à la date donnée, puis identifier exactement 5 plantes médicinales qui :
    - poussent ou sont récoltées dans cette région pendant cette saison,
    - sont traditionnellement utilisées pour les maux indiqués.
    Réponds UNIQUEMENT avec un tableau JSON d'objets, chaque objet ayant les clés :
    - "nom_commun" (string)
    - "nom_scientifique" (string)
    - "saison" (string : la saison de récolte ou de disponibilité)
    - "description_courte" (string : une phrase)
    Si tu ne trouves pas 5 plantes, renvoie celles que tu as, mais essaie d'en trouver 5.
    Si aucune, renvoie [].
    """
    user = f"Date d'aujourd'hui : {today}\nLieu : {location}\nMaux : {', '.join(maux)}"
    response = ask_groq(system, user, model="llama-3.3-70b-versatile", max_tokens=800)
    if response:
        plants = extract_json(response)
        if plants is not None and isinstance(plants, list):
            valid_plants = []
            for p in plants:
                if isinstance(p, dict) and all(k in p for k in ["nom_commun", "nom_scientifique", "saison", "description_courte"]):
                    valid_plants.append(p)
            return valid_plants[:5]  # limite à 5
    return []

def get_plant_details(nom_commun, nom_scientifique):
    """Génère une fiche détaillée pour une plante donnée."""
    system = """Tu es un botaniste et phytothérapeute expérimenté.
    Fournis une fiche complète sur la plante indiquée, structurée en Markdown, contenant :
    - **Description botanique** : 2-3 phrases.
    - **Effets bénéfiques** : liste à puces des propriétés médicinales.
    - **Meilleure façon d'extraire soi-même ses principes actifs** : instructions précises (infusion, décoction, teinture, cataplasme, etc.).
    - **Saisons de récolte** : quand récolter la plante.
    - **Précautions d'emploi** : contre-indications éventuelles.
    - **Liens utiles** : deux liens vers des sites de référence en phytothérapie (par exemple Wikipédia, PasseportSanté). Fournis des URLs complètes et fonctionnelles.
    Utilise un ton professionnel et accessible."""
    user = f"Nom commun : {nom_commun}\nNom scientifique : {nom_scientifique}"
    response = ask_groq(system, user, model="llama-3.3-70b-versatile", max_tokens=1500)
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
if 'page' not in st.session_state:
    st.session_state.page = 'search'  # search, symptoms, plants, plant_detail

if 'location' not in st.session_state:
    st.session_state.location = ""

if 'maux_choisis' not in st.session_state:
    st.session_state.maux_choisis = []

if 'plants' not in st.session_state:
    st.session_state.plants = []

if 'selected_plant' not in st.session_state:
    st.session_state.selected_plant = None

if 'suggestions' not in st.session_state:
    st.session_state.suggestions = []

# ------------------------------
# Navigation helpers
# ------------------------------
def go_to_page(page_name):
    st.session_state.page = page_name
    st.rerun()

# ------------------------------
# PAGE 1 : Recherche du lieu
# ------------------------------
if st.session_state.page == 'search':
    st.title("🌿 Herbier médicinal intelligent")
    st.markdown("### Étape 1 : Où vous trouvez-vous ?")
    st.write("Commencez à taper un pays ou une ville, puis choisissez dans les suggestions.")

    # Champ de saisie
    location_input = st.text_input("Lieu (pays ou ville)", value=st.session_state.location)

    # Autocomplétion : si au moins 2 caractères, on propose des suggestions
    if len(location_input) >= 2:
        # On ne déclenche la recherche que si l'utilisateur n'a pas encore validé ou si la saisie a changé
        if st.session_state.get('last_input') != location_input:
            st.session_state.last_input = location_input
            with st.spinner("Recherche de suggestions..."):
                suggestions = get_location_suggestions(location_input)
                st.session_state.suggestions = suggestions
    else:
        st.session_state.suggestions = []

    # Affichage des suggestions sous forme de boutons
    if st.session_state.suggestions:
        st.write("Suggestions :")
        cols = st.columns(min(len(st.session_state.suggestions), 5))
        for idx, sugg in enumerate(st.session_state.suggestions):
            col = cols[idx % len(cols)]
            if col.button(sugg, key=f"sugg_{idx}"):
                st.session_state.location = sugg
                st.session_state.suggestions = []
                go_to_page('symptoms')

    # Bouton pour valider manuellement
    if st.button("Valider ce lieu", type="primary"):
        if location_input.strip():
            st.session_state.location = location_input.strip()
            st.session_state.suggestions = []
            go_to_page('symptoms')
        else:
            st.warning("Veuillez saisir un lieu.")

# ------------------------------
# PAGE 2 : Sélection des maux
# ------------------------------
elif st.session_state.page == 'symptoms':
    st.title("🌿 Herbier médicinal intelligent")
    st.markdown(f"### Étape 2 : Quels maux présentez-vous ?")
    st.write(f"Lieu sélectionné : **{st.session_state.location}**")

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
    maux_choisis = st.multiselect("Sélectionnez un ou plusieurs maux", maux_options, default=st.session_state.maux_choisis)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Retour au lieu"):
            go_to_page('search')
    with col2:
        if st.button("Rechercher les plantes 🔍", type="primary"):
            if not maux_choisis:
                st.warning("Veuillez sélectionner au moins un mal.")
            else:
                st.session_state.maux_choisis = maux_choisis
                with st.spinner("Recherche des plantes adaptées à la saison..."):
                    plants = search_plants(st.session_state.location, maux_choisis)
                    st.session_state.plants = plants
                    if plants:
                        go_to_page('plants')
                    else:
                        st.error("Aucune plante trouvée. Essayez d'autres maux ou un autre lieu.")

# ------------------------------
# PAGE 3 : Liste des 5 plantes
# ------------------------------
elif st.session_state.page == 'plants':
    st.title("🌿 Herbier médicinal intelligent")
    st.markdown(f"### Étape 3 : Plantes adaptées à vos besoins")
    st.write(f"Lieu : **{st.session_state.location}** | Maux : {', '.join(st.session_state.maux_choisis)}")

    if not st.session_state.plants:
        st.info("Aucune plante trouvée. Revenez en arrière pour modifier vos critères.")
        if st.button("← Retour aux maux"):
            go_to_page('symptoms')
    else:
        st.write("Voici 5 plantes qui pourraient vous aider :")
        for i, plant in enumerate(st.session_state.plants):
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("Voir fiche", key=f"btn_{i}"):
                    st.session_state.selected_plant = plant
                    go_to_page('plant_detail')
            with col2:
                st.write(f"**{plant.get('nom_commun', 'N/A')}** (*{plant.get('nom_scientifique', '')}*)")
                st.caption(f"Saison : {plant.get('saison', 'N/A')}")
                st.write(plant.get('description_courte', ''))

        if st.button("← Retour aux maux"):
            go_to_page('symptoms')

# ------------------------------
# PAGE 4 : Fiche détaillée
# ------------------------------
elif st.session_state.page == 'plant_detail':
    plant = st.session_state.selected_plant
    if not plant:
        st.warning("Aucune plante sélectionnée.")
        if st.button("← Retour à la liste"):
            go_to_page('plants')
    else:
        st.title(f"🌱 {plant.get('nom_commun', 'Plante')}")
        st.subheader(f"*{plant.get('nom_scientifique', '')}*")

        # Image
        image_url = get_wikimedia_image(plant.get('nom_scientifique', ''))
        if image_url:
            st.image(image_url, width=400, caption=plant.get('nom_commun', ''))
        else:
            st.write("Image non disponible pour cette plante.")

        # Fiche détaillée
        with st.spinner("Génération de la fiche détaillée..."):
            fiche = get_plant_details(plant.get('nom_commun', ''), plant.get('nom_scientifique', ''))
            if fiche:
                st.markdown(fiche)
            else:
                st.error("Impossible de générer la fiche.")

        if st.button("← Retour à la liste des plantes"):
            go_to_page('plants')
