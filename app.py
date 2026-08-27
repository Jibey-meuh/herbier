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
# Modèles Groq disponibles (selon ta liste)
# ------------------------------
# Pour les tâches simples (suggestions, listes)
MODELE_RAPIDE = "qwen/qwen3.6-27b"

# Pour les tâches complexes (recherche de plantes, fiches détaillées)
MODELE_PUISSANT = "openai/gpt-oss-120b"

# Modèle de secours
MODELE_SECOURS = "openai/gpt-oss-20b"

# Liste complète pour essai en cascade
MODELES = [
    MODELE_PUISSANT,
    MODELE_RAPIDE,
    MODELE_SECOURS,
    "qwen/qwen3.8-27b",
    "allam-2-7b"
]

# ------------------------------
# Fonctions utilitaires
# ------------------------------

def ask_groq(system_prompt, user_prompt, model=None, temperature=0.7, max_tokens=1500):
    """Envoie une requête à l'API Groq en essayant plusieurs modèles."""
    models_to_try = [model] if model else MODELES
    last_error = None
    
    for m in models_to_try:
        try:
            response = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            continue
    
    # Si tous échouent, afficher l'erreur
    if last_error:
        st.error(f"Erreur API Groq : {last_error}")
    return None

def extract_json(text):
    """Extrait le premier bloc JSON d'un texte, même avec du texte autour."""
    if not text:
        return None
    # Essaie de trouver un tableau JSON entre [ et ]
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Essaie de corriger les virgules manquantes ou guillemets simples
            try:
                json_str_clean = json_str.replace("'", '"')
                return json.loads(json_str_clean)
            except:
                pass
    return None

def search_plants(country, maux):
    """Recherche 5 plantes médicinales adaptées au pays, aux maux, en priorité de saison."""
    today = datetime.now().strftime("%d/%m/%Y")
    system = """Tu es un expert en phytothérapie et botanique.
    L'utilisateur indique un pays et une liste de maux.
    Tu dois proposer EXACTEMENT 5 plantes médicinales qui peuvent aider pour ces maux et qui sont disponibles ou courantes dans ce pays.
    - En priorité, choisis des plantes qui sont en saison de récolte ou de disponibilité à la date donnée.
    - Si tu ne trouves pas 5 plantes de saison, complète avec des plantes très courantes dans ce pays qui peuvent aider, même si elles ne sont pas actuellement en saison (par exemple plantes séchées, plantes vivaces, plantes cultivées, etc.).
    - Assure-toi d'avoir exactement 5 plantes. Si tu ne peux vraiment pas en trouver 5, renvoie au moins 3 plantes courantes, mais fais de ton mieux pour 5.
    Réponds UNIQUEMENT avec un tableau JSON d'objets, chaque objet ayant les clés :
    - "nom_commun" (string)
    - "nom_scientifique" (string)
    - "saison" (string : la saison de récolte ou "toute l'année")
    - "description_courte" (string : une phrase)
    Exemple de format :
    [
        {"nom_commun": "Camomille", "nom_scientifique": "Matricaria chamomilla", "saison": "printemps, été", "description_courte": "Apaisante et digestive."},
        ...
    ]
    Ne mets aucun texte avant ou après le JSON.
    """
    user = f"Date d'aujourd'hui : {today}\nPays : {country}\nMaux : {', '.join(maux)}"
    response = ask_groq(system, user, model=MODELE_PUISSANT, max_tokens=800)
    if response:
        plants = extract_json(response)
        if plants is not None and isinstance(plants, list):
            valid_plants = []
            for p in plants:
                if isinstance(p, dict) and all(k in p for k in ["nom_commun", "nom_scientifique", "saison", "description_courte"]):
                    valid_plants.append(p)
            # Limiter à 5
            return valid_plants[:5]
        else:
            # Afficher la réponse brute pour debug (à retirer en prod)
            st.write("Réponse brute de Groq :", response)
    return []

def get_plant_details(nom_commun, nom_scientifique):
    """Génère une fiche détaillée pour une plante donnée."""
    system = """Tu es un botaniste et phytothérapeute expérimenté.
Fournis une fiche complète sur la plante indiquée, structurée en Markdown.
**IMPORTANT** : La fiche doit commencer par une section intitulée **Liens utiles** contenant exactement deux liens vers des sites de phytothérapie réputés (par exemple Wikipédia, PasseportSanté, Doctissimo, etc.). Chaque lien doit être sur une ligne séparée, sous forme de liste à puces avec le nom du site et l'URL complète.
Ensuite, ajoute les sections suivantes dans cet ordre :
- **Description botanique** : 2-3 phrases.
- **Effets bénéfiques** : liste à puces des propriétés médicinales.
- **Meilleure façon d'extraire soi-même ses principes actifs** : instructions précises.
- **Saisons de récolte**.
- **Précautions d'emploi**.
Utilise un ton professionnel et accessible."""
    user = f"Nom commun : {nom_commun}\nNom scientifique : {nom_scientifique}"
    response = ask_groq(system, user, model=MODELE_PUISSANT, max_tokens=1500)
    return response if response else "Fiche non disponible."

def get_wikimedia_image(nom_scientifique, nom_commun=""):
    """Récupère une image libre de droits depuis Wikimedia Commons, avec repli sur le nom commun."""
    urls = []
    if nom_scientifique:
        urls.append(nom_scientifique)
    if nom_commun:
        urls.append(nom_commun)
        urls.append(nom_commun + " plante")
        urls.append(nom_commun + " herbe")

    for query in urls:
        try:
            search_url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
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
            continue

    # Image de remplacement générique
    return "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4a/Flower_icon.svg/512px-Flower_icon.svg.png"

# ------------------------------
# Listes de pays et symptômes
# ------------------------------
# Liste des pays du monde (ordre alphabétique)
PAYS = [
    "Afghanistan", "Afrique du Sud", "Albanie", "Algérie", "Allemagne", "Andorre", "Angola",
    "Antigua-et-Barbuda", "Arabie saoudite", "Argentine", "Arménie", "Australie", "Autriche",
    "Azerbaïdjan", "Bahamas", "Bahreïn", "Bangladesh", "Barbade", "Belgique", "Belize",
    "Bénin", "Bhoutan", "Biélorussie", "Birmanie", "Bolivie", "Bosnie-Herzégovine",
    "Botswana", "Brésil", "Brunei", "Bulgarie", "Burkina Faso", "Burundi", "Cambodge",
    "Cameroun", "Canada", "Cap-Vert", "Chili", "Chine", "Chypre", "Colombie", "Comores",
    "Congo", "Corée du Nord", "Corée du Sud", "Costa Rica", "Côte d'Ivoire", "Croatie",
    "Cuba", "Danemark", "Djibouti", "Dominique", "Égypte", "Émirats arabes unis",
    "Équateur", "Érythrée", "Espagne", "Estonie", "Eswatini", "États-Unis", "Éthiopie",
    "Fidji", "Finlande", "France", "Gabon", "Gambie", "Géorgie", "Ghana", "Grèce",
    "Grenade", "Guatemala", "Guinée", "Guinée-Bissau", "Guinée équatoriale", "Guyana",
    "Haïti", "Honduras", "Hongrie", "Inde", "Indonésie", "Irak", "Iran", "Irlande",
    "Islande", "Israël", "Italie", "Jamaïque", "Japon", "Jordanie", "Kazakhstan",
    "Kenya", "Kirghizistan", "Kiribati", "Koweït", "Laos", "Lesotho", "Lettonie",
    "Liban", "Liberia", "Libye", "Liechtenstein", "Lituanie", "Luxembourg",
    "Macédoine du Nord", "Madagascar", "Malaisie", "Malawi", "Maldives", "Mali",
    "Malte", "Maroc", "Marshall", "Maurice", "Mauritanie", "Mexique", "Micronésie",
    "Moldavie", "Monaco", "Mongolie", "Monténégro", "Mozambique", "Namibie", "Nauru",
    "Népal", "Nicaragua", "Niger", "Nigeria", "Norvège", "Nouvelle-Zélande", "Oman",
    "Ouganda", "Ouzbékistan", "Pakistan", "Palaos", "Panama", "Papouasie-Nouvelle-Guinée",
    "Paraguay", "Pays-Bas", "Pérou", "Philippines", "Pologne", "Portugal", "Qatar",
    "République centrafricaine", "République dominicaine", "République tchèque",
    "Roumanie", "Royaume-Uni", "Russie", "Rwanda", "Saint-Kitts-et-Nevis",
    "Saint-Marin", "Saint-Vincent-et-les-Grenadines", "Sainte-Lucie", "Salomon",
    "Salvador", "Samoa", "São Tomé-et-Principe", "Sénégal", "Serbie", "Seychelles",
    "Sierra Leone", "Singapour", "Slovaquie", "Slovénie", "Somalie", "Soudan",
    "Soudan du Sud", "Sri Lanka", "Suède", "Suisse", "Suriname", "Syrie",
    "Tadjikistan", "Tanzanie", "Tchad", "Thaïlande", "Timor oriental", "Togo",
    "Tonga", "Trinité-et-Tobago", "Tunisie", "Turkménistan", "Turquie", "Tuvalu",
    "Ukraine", "Uruguay", "Vanuatu", "Vatican", "Venezuela", "Viêt Nam", "Yémen",
    "Zambie", "Zimbabwe"
]

# Liste des symptômes courants traités par la phytothérapie
SYMPTOMES = [
    "Ballonnements", "Digestion difficile", "Constipation", "Diarrhée", "Nausées",
    "Reflux gastrique", "Syndrome de l'intestin irritable", "Stress", "Anxiété",
    "Dépression légère", "Insomnie", "Fatigue chronique", "Manque d'énergie",
    "Maux de tête", "Migraine", "Douleurs articulaires", "Arthrite", "Douleurs musculaires",
    "Règles douloureuses", "Syndrome prémenstruel (SPM)", "Ménopause", "Problèmes de prostate",
    "Problèmes de peau (acné, eczéma)", "Infections urinaires", "Problèmes respiratoires",
    "Toux", "Rhume", "Grippe", "Allergies", "Hypertension", "Cholestérol",
    "Diabète (soutien)", "Problèmes de foie", "Problèmes de vésicule biliaire",
    "Problèmes rénaux", "Défenses immunitaires faibles", "Inflammation",
    "Problèmes circulatoires", "Varices", "Hémorroïdes", "Perte de poids",
    "Troubles de la concentration", "Mémoire", "Nervosité", "Palpitations"
]

# ------------------------------
# Initialisation de l'état de session
# ------------------------------
if 'page' not in st.session_state:
    st.session_state.page = 'search'

if 'country' not in st.session_state:
    st.session_state.country = None

if 'maux_choisis' not in st.session_state:
    st.session_state.maux_choisis = []

if 'plants' not in st.session_state:
    st.session_state.plants = []

if 'selected_plant' not in st.session_state:
    st.session_state.selected_plant = None

# ------------------------------
# Navigation helpers
# ------------------------------
def go_to_page(page_name):
    st.session_state.page = page_name
    st.rerun()

# ------------------------------
# PAGE 1 : Sélection du pays
# ------------------------------
if st.session_state.page == 'search':
    st.title("🌿 Herbier médicinal intelligent")
    st.markdown("### Étape 1 : Dans quel pays vous trouvez-vous ?")
    
    country = st.selectbox("Sélectionnez un pays", PAYS, index=0)
    
    if st.button("Continuer ➜", type="primary"):
        st.session_state.country = country
        go_to_page('symptoms')

# ------------------------------
# PAGE 2 : Sélection des symptômes
# ------------------------------
elif st.session_state.page == 'symptoms':
    st.title("🌿 Herbier médicinal intelligent")
    st.markdown(f"### Étape 2 : Quels symptômes présentez-vous ?")
    st.write(f"Pays sélectionné : **{st.session_state.country}**")
    
    maux_choisis = st.multiselect("Sélectionnez un ou plusieurs symptômes", SYMPTOMES, default=st.session_state.maux_choisis)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Retour au pays"):
            go_to_page('search')
    with col2:
        if st.button("Rechercher les plantes 🔍", type="primary"):
            if not maux_choisis:
                st.warning("Veuillez sélectionner au moins un symptôme.")
            else:
                st.session_state.maux_choisis = maux_choisis
                with st.spinner("Recherche des plantes adaptées à la saison..."):
                    plants = search_plants(st.session_state.country, maux_choisis)
                    st.session_state.plants = plants
                    if plants:
                        go_to_page('plants')
                    else:
                        st.error("Aucune plante trouvée. Essayez d'autres symptômes ou un autre pays.")

# ------------------------------
# PAGE 3 : Liste des 5 plantes
# ------------------------------
elif st.session_state.page == 'plants':
    st.title("🌿 Herbier médicinal intelligent")
    st.markdown(f"### Étape 3 : Plantes adaptées à vos besoins")
    st.write(f"Pays : **{st.session_state.country}** | Symptômes : {', '.join(st.session_state.maux_choisis)}")
    
    if not st.session_state.plants:
        st.info("Aucune plante trouvée. Revenez en arrière pour modifier vos critères.")
        if st.button("← Retour aux symptômes"):
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
        
        if st.button("← Retour aux symptômes"):
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
        
        # Image (toujours affichée, avec repli automatique)
        image_url = get_wikimedia_image(plant.get('nom_scientifique', ''), plant.get('nom_commun', ''))
        st.image(image_url, width=400, caption=plant.get('nom_commun', ''))
        
        # Fiche détaillée
        with st.spinner("Génération de la fiche détaillée..."):
            fiche = get_plant_details(plant.get('nom_commun', ''), plant.get('nom_scientifique', ''))
            if fiche:
                st.markdown(fiche)
            else:
                st.error("Impossible de générer la fiche.")
        
        if st.button("← Retour à la liste des plantes"):
            go_to_page('plants')
