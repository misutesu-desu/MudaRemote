# ✨ MudaRemote : Automatisation Mudae Avancée ✨

[![Violation des CGU de Discord - **UTILISER AVEC PRÉCAUTION**](https://img.shields.io/badge/Discord%20CGU-VIOLATION-red)](https://discord.com/terms) ⚠️ **RISQUE DE BANDE DE COMPTE !** ⚠️

**🛑🛑🛑 ATTENTION : SELF-BOT - VIOLATION POTENTIELLE DES CGU DE DISCORD ! RISQUE DE BANDE DE COMPTE ! 🛑🛑🛑**
**🔥 UTILISEZ À VOS PROPRES RISQUES ! 🔥 NOUS NE SOMMES PAS RESPONSABLES DES ACTIONS PRISES CONTRE VOTRE COMPTE. 😱**

---

Rejoignez notre [serveur Discord](https://discord.gg/4WHXkDzuZx)

## 🚀 MudaRemote : Améliorez Votre Expérience Mudae (Utilisez Responsablement !)

MudaRemote est un self-bot basé sur Python conçu pour automatiser diverses tâches pour le bot Discord Mudae. Il offre des fonctionnalités telles que le sniping en temps réel et le réclamement intelligent. **Cependant, l'utilisation de self-bots est contraire aux Conditions Générales d'Utilisation (CGU) de Discord et peut entraîner une suspension ou un bannissement de compte.** Veuillez l'utiliser avec une extrême prudence et comprendre les risques encourus.

### ✨ Fonctionnalités Principales :

*   **🎯 Sniping Externe (Liste de Souhaits, Série & Valeur Kakera) :** Réclame les personnages tirés par *d'autres*.
*   **🟡 Sniping de Réaction Kakera Externe :** Clique automatiquement sur les boutons de réaction kakera sur *tout* message Mudae.
*   **😴 Mode Snipe-Seulement :** Configurez les instances du bot pour *uniquement* écouter et exécuter les snipes externes, sans envoyer de commandes de tirage.
*   **⚡ Sniping Réactif sur les Auto-Tirages :** Réclame instantanément les personnages de *vos propres* tirages s'ils correspondent aux critères.
*   **🤖 Tirage Automatisé & Réclamement Général :** Gère les commandes de tirage et réclame en fonction du kakera minimum.
*   **🥇 Logique de Réclamement Intelligente :** Analyse `$tu` pour vérifier la disponibilité de `$rt` et l'utilise pour une potentielle deuxième réclamation sur les tirages de grande valeur.
*   **🔄 Détection de Réinitialisation Automatique :** Surveille et attend les minuteries de réinitialisation de réclamation et de tirage de Mudae.
*   **🚶‍♂️ Attente Humanisée (NOUVEAU !) :** Simule un comportement humain en attendant une période aléatoire et l'inactivité du canal avant de reprendre les actions après une réinitialisation, réduisant significativement la prévisibilité.
*   **💡 Gestion de Puissance DK (NOUVEAU !) :** Vérifie intelligemment votre puissance de réaction kakera via `$tu` et n'utilise `$dk` que lorsque la puissance est insuffisante pour une réaction, économisant les charges.
*   **🔑 Mode Clé :** Permet un tirage continu pour la collecte de kakera, même lorsque les réclamations de personnages sont en temps de recharge.
*   **⏩ Dispatch de Tirage par Slash (NOUVEAU !) :** Fonctionnalité optionnelle pour envoyer les commandes de tirage (`wa`, `h`, `m`, etc.) en utilisant l'infrastructure de commande Slash de Discord au lieu des commandes textuelles.
*   **👯 Support Multi-Comptes :** Exécutez plusieurs instances de bot simultanément.
*   **⏱️ Délais Personnalisables & Vitesse de Tirage :** Ajustez finement tous les délais d'action et la vitesse des commandes de tirage.
*   **🗂️ Configuration Facile des Préréglages :** Gérez tous les paramètres dans un seul fichier `presets.json`.
*   **📊 Journalisation de Console :** Sortie claire, codée par couleur et en temps réel.
*   **🌐 Support de Localisation :** Amélioration de l'analyse pour les réponses Mudae en anglais et en portugais (PT-BR).

---

## 🛠️ Guide de Configuration

1.  **🐍 Python :** Assurez-vous que Python 3.8+ est installé. ([Télécharger Python](https://www.python.org/downloads/))
2.  **📦 Dépendances :** Ouvrez votre terminal ou invite de commande et exécutez :
    ```bash
    pip install discord.py-self inquirer
    ```
    *Note : Si vous prévoyez d'utiliser `use_slash_rolls: true`, assurez-vous que votre version de `discord.py-self` inclut l'objet `Route` (les versions plus récentes le font généralement).*
3.  **📝 `presets.json` :** Créez un fichier `presets.json` dans le répertoire du script. Ajoutez vos configurations de bot ici. Consultez l'exemple ci-dessous pour toutes les options disponibles.
4.  **🚀 Exécuter :** Exécutez le script depuis votre terminal :
    ```bash
    python mudae_bot.py
    ```
5.  **🕹️ Sélectionner les Préréglages :** Choisissez quel(s) bot(s) configuré(s) exécuter à partir du menu interactif.

---

### Exemple de Configuration `presets.json` :

*(Le contenu de l'exemple JSON reste identique à l'original pour la configuration technique.)*

```json
{
  "YourBotAccountName": {
    // --- REQUIRED SETTINGS ---
    "token": "YOUR_DISCORD_ACCOUNT_TOKEN", 
    "channel_id": 123456789012345678,     
    "roll_command": "wa",                  
    "delay_seconds": 1,                    
    "mudae_prefix": "$",                   
    "min_kakera": 50,                      

    // --- CORE OPERATIONAL MODE ---
    "rolling": true,                       

    // --- ADVANCED ROLLING / CLAIMING ---
    "roll_speed": 0.4,                     
    "key_mode": false,                     
    "skip_initial_commands": false,        
    "use_slash_rolls": false,              
    "dk_power_management": true,           

    // --- HUMANIZATION (Recommended for high-risk accounts) ---
    "humanization_enabled": true,          
    "humanization_window_minutes": 40,     
    "humanization_inactivity_seconds": 5,  

    // --- EXTERNAL SNIPING (For characters rolled by OTHERS) ---
    "snipe_mode": true,                    
    "wishlist": ["Character Name 1", "Character Name 2"],
    "snipe_delay": 2,                      

    "series_snipe_mode": true,             
    "series_wishlist": ["Series Name 1"],
    "series_snipe_delay": 3,               

    "kakera_reaction_snipe_mode": false,   
    "kakera_reaction_snipe_delay": 0.75,   

    // --- KAKERA THRESHOLD (Used for both External and Reactive Sniping) ---
    "kakera_snipe_mode": true,             
    "kakera_snipe_threshold": 100,         

    // --- REACTIVE SNIPING (For characters from YOUR OWN rolls) ---
    "reactive_snipe_on_own_rolls": true,   

    // --- OTHER ---
    "start_delay": 0,                      
    "snipe_ignore_min_kakera_reset": false 
  }
}
```

---

## 🎮 Obtenir Votre Jeton Discord 🔑

Les self-bots nécessitent le jeton de votre compte Discord. **Ce jeton donne un accès complet à votre compte – gardez-le extrêmement privé ! Le partager revient à donner votre mot de passe.** Il est recommandé d'utiliser ce bot sur un compte alternatif.

1.  **Ouvrez Discord dans votre navigateur web** (ex. Chrome, Firefox). *Pas l'application de bureau.*
2.  Appuyez sur **F12** pour ouvrir les Outils de Développement.
3.  Naviguez jusqu'à l'onglet **`Console`**.
4.  Collez l'extrait de code suivant dans la console et appuyez sur Entrée :

    ```javascript
    // [Le même extrait de code Javascript est inséré ici]
    window.webpackChunkdiscord_app.push([
    	[Symbol()],
    	{},
    	req => {
    		if (!req.c) return;
    		for (let m of Object.values(req.c)) {
    			try {
    				if (!m.exports || m.exports === window) continue;
    				if (m.exports?.getToken) return copy(m.exports.getToken());
    				for (let ex in m.exports) {
    					if (m.exports?.[ex]?.getToken && m.exports[ex][Symbol.toStringTag] !== 'IntlMessagesProxy') return copy(m.exports[ex].getToken());
    				}
    			} catch {}
    		}
    	},
    ]);

    window.webpackChunkdiscord_app.pop();
    console.log('%cWorked!', 'font-size: 50px');
    console.log(`%cYou now have your token in the clipboard!`, 'font-size: 16px');
    ```
5.  Votre jeton sera copié dans votre presse-papiers. Collez-le soigneusement dans le champ `"token"` de votre fichier `presets.json`.

---

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à signaler des problèmes, suggérer des fonctionnalités ou soumettre des requêtes de tirage (pull requests) au dépôt du projet.

**🙏 Veuillez utiliser cet outil de manière responsable et éthique, en étant pleinement conscient des risques potentiels pour votre compte Discord. 🙏**

**Bon (et Prudent !) Mudae-ing !** 😉

---
**Licence :** [Licence MIT](LICENSE)
