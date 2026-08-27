# Herbier médicinal intelligent

Application Streamlit qui utilise l'API Groq pour rechercher des plantes médicinales par pays et par maux, avec génération de fiches détaillées et images libres de droits.

## Déploiement local

1. Clonez ce dépôt.
2. Installez les dépendances : `pip install -r requirements.txt`
3. Créez un fichier `.streamlit/secrets.toml` avec votre clé API Groq :
   ```toml
   GROQ_API_KEY = "votre_clé"