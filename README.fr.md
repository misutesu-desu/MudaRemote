[English](README.md) | [Français](README.fr.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

# ✨ MudaRemote: Automatisation Avancée de Mudae ✨

[![Violation des CGU de Discord - **UTILISER AVEC PRUDENCE**](https://img.shields.io/badge/Discord%20TOS-VIOLATION-red)](https://discord.com/terms) ⚠️ **RISQUE DE BAN DE COMPTE !** ⚠️

**🛑🛑🛑 AVERTISSEMENT: SELF-BOT - VIOLATION POTENTIELLE DES CGU DE DISCORD ! RISQUE DE BAN DE COMPTE ! 🛑🛑🛑**
**🔥 UTILISEZ À VOS PROPRES RISQUES ! 🔥 NOUS NE SOMMES PAS RESPONSABLES DES ACTIONS PRISES CONTRE VOTRE COMPTE. 😱**

---

## 🚀 MudaRemote: Améliorez Votre Expérience Mudae (Utilisez Responsablement !)

MudaRemote est un self-bot basé sur Python conçu pour automatiser diverses tâches pour le bot Discord Mudae. Il offre des fonctionnalités telles que le sniping en temps réel et la revendication intelligente. **Cependant, l'utilisation de self-bots est contraire aux Conditions Générales d'Utilisation de Discord et peut entraîner la suspension ou le bannissement de votre compte.** Veuillez l'utiliser avec une extrême prudence et comprendre les risques encourus.

### ✨ Fonctionnalités Principales:

*   **🎯 Sniping Externe (Liste de Souhaits, Série & Valeur Kakera):**
    *   **Sniping de Liste de Souhaits:** Revendique les personnages de votre liste de souhaits lorsqu'ils sont tirés par *d'autres* (délai configurable).
    *   **Sniping de Série:** Revendique les personnages de votre liste de souhaits de série lorsqu'ils sont tirés par *d'autres* (délai configurable).
    *   **Sniping de Valeur Kakera:** Revendique les personnages uniquement en fonction de leur valeur kakera (si supérieure au seuil) lorsqu'ils sont tirés par *d'autres*.
*   **🟡 Sniping de Réaction Kakera Externe (Nouveau !):** Clique automatiquement sur les boutons de réaction kakera sur *n'importe quel* message Mudae.
*   **😴 Mode Sniping Uniquement:** Configurez les instances du bot pour qu'elles *n'écoutent et n'exécutent que* les snipes externes, sans envoyer de commandes de tirage.
*   **⚡ Sniping Réactif sur Vos Propres Tirages:** Revendique instantanément les personnages de *vos propres* tirages s'ils correspondent aux critères (liste de souhaits, série, valeur kakera). Interrompt le lot de tirage actuel.
*   **👯 Prise en Charge Multi-Comptes:** Exécutez plusieurs instances du bot simultanément, chacune avec sa propre configuration.
*   **🤖 Tirage Automatisé & Revendication Générale:** Gère vos commandes de tirage et effectue des revendications générales basées sur le kakera minimum après les tirages.
*   **🥇 Logique de Revendication Intelligente:** Utilise `$rt` pour une potentielle deuxième revendication.
*   **🔄 Détection Automatique de Réinitialisation de Tirage & Revendication:** Surveille et attend les minuteries de réinitialisation de Mudae pour optimiser les actions.
*   **🔑 Mode Clé:** Permet un tirage continu spécifiquement pour la collecte de kakera, même lorsque vos droits de revendication de personnage principal sont en attente.
*   **⏱️ Délais Personnalisables & Vitesse de Tirage:** Ajustez les délais d'action généraux et la vitesse des commandes de tirage.
*   **🗂️ Configuration Facile des Préréglages:** Gérez tous les paramètres pour différents comptes/scénarios via un fichier `presets.json`.
*   **📊 Journalisation Console:** Sortie en temps réel claire et colorée des actions et du statut du bot.

---

## 🛠️ Guide de Configuration

1.  **🐍 Python:** Assurez-vous que Python 3.8+ est installé. ([Télécharger Python](https://www.python.org/downloads/))
2.  **📦 Dépendances:** Ouvrez votre terminal ou invite de commande et exécutez:
    ```bash
    pip install discord.py-self inquirer
    ```
3.  **📝 `presets.json`:** Créez un fichier nommé `presets.json` dans le même répertoire que le script. Ajoutez vos configurations de bot ici. Voir l'exemple ci-dessous pour toutes les options disponibles.
4.  **🚀 Exécuter:** Exécutez le script depuis votre terminal:
    ```bash
    python mudae_bot.py
    ```
    (Remplacez `mudae_bot.py` par le nom de fichier réel de votre script si différent).
5.  **🕹️ Sélectionner les Préréglages:** Choisissez le(s) bot(s) configuré(s) à exécuter dans le menu interactif qui apparaît.

---

### Exemple de Configuration `presets.json`:

```json
{
  "YourBotAccountName": {
    // --- PARAMÈTRES REQUIS ---
    "token": "YOUR_DISCORD_ACCOUNT_TOKEN", // Votre jeton de compte Discord. GARDEZ-LE EXTRÊMEMENT SECRET !
    "channel_id": 123456789012345678,     // ID du canal Discord pour les commandes Mudae.
    "roll_command": "wa",                  // Votre commande de tirage Mudae préférée (ex: wa, hg, w, ma). Utilisé uniquement si "rolling" est vrai.
    "delay_seconds": 1,                    // Délai général (secondes) entre certaines actions du bot (ex: après $tu avant l'analyse). Utilisé uniquement si "rolling" est vrai.
    "mudae_prefix": "$",                   // Le préfixe que Mudae utilise sur votre serveur (généralement "$").
    "min_kakera": 50,                      // Valeur kakera minimale pour les revendications de personnage générales (après le lot de tirage). Utilisé uniquement si "rolling" est vrai.

    // --- MODE OPÉRATIONNEL PRINCIPAL ---
    "rolling": true,                       // (Par défaut: true) Si vrai, le bot effectue les tirages, les revendications, les vérifications $tu, etc.
                                           // Si faux, le bot passe en mode SNIPING UNIQUEMENT: pas de tirage, pas de vérifications $tu, écoute uniquement les snipes externes.

    // --- PARAMÈTRES OPTIONNELS (Certains dépendent de "rolling: true") ---
    "key_mode": false,                     // (Par défaut: false) Si vrai ET "rolling" est vrai, tire pour le kakera même si aucun droit de revendication de personnage n'est disponible.
    "start_delay": 0,                      // (Par défaut: 0) Délai (secondes) avant le démarrage du bot après avoir été sélectionné dans le menu.
    "roll_speed": 0.4,                     // (Par défaut: 0.4) Délai (secondes) entre les commandes de tirage individuelles. Utilisé uniquement si "rolling" est vrai.

    // Paramètres de Sniping Externe (pour les personnages/kakera tirés par D'AUTRES - Toujours actif si configuré, quelle que soit l'état de "rolling")
    "snipe_mode": true,                    // (Par défaut: false) Active le sniping externe de liste de souhaits (revendications de cœur).
    "wishlist": ["Character Name 1", "Character Name 2"], // Liste des noms de personnages pour le sniping de cœur.
    "snipe_delay": 2,                      // (Par défaut: 2) Délai (secondes) avant de revendiquer un snipe externe de liste de souhaits ET un snipe externe de valeur kakera.

    "series_snipe_mode": true,             // (Par défaut: false) Active le sniping externe de série (revendications de cœur).
    "series_wishlist": ["Series Name 1"],  // Liste des noms de série pour le sniping de cœur.
    "series_snipe_delay": 3,               // (Par défaut: 3) Délai (secondes) avant de revendiquer un snipe externe de série.

    "kakera_reaction_snipe_mode": false,   // (Par défaut: false) Active le sniping de RÉACTION kakera externe (clique sur les boutons kakera).
    "kakera_reaction_snipe_delay": 0.75,   // (Par défaut: 0.75) Délai (secondes) avant de cliquer sur une réaction kakera externe.

    // Paramètres de Sniping Réactif (pour les personnages/kakera de VOS PROPRES tirages - Actif uniquement si "rolling: true")
    "reactive_snipe_on_own_rolls": true,   // (Par défaut: true) Active/désactive les revendications de cœur RÉACTIVES INSTANTANÉES ET les clics kakera pendant VOS PROPRES tirages.
                                           // Si vrai, utilise la liste de souhaits, la liste de souhaits de série et le seuil kakera_snipe (si kakera_snipe_mode est vrai) comme critères pour les revendications de cœur.
                                           // Le kakera sur ces personnages revendiqués réactivement sera également cliqué.
                                           // Si faux, toutes les revendications/clics kakera pour vos propres tirages se produisent après la fin du lot de tirage.

    // Paramètres de Seuil Kakera (utilisés pour les revendications de CŒUR réactives sur vos propres tirages ET les snipes de CŒUR de valeur kakera externes)
    "kakera_snipe_mode": true,             // (Par défaut: false) Si vrai, active `kakera_snipe_threshold` comme critère pour les revendications de CŒUR pour:
                                           //    1. Les revendications de cœur réactives INSTANTANÉES pendant vos propres tirages (si "rolling" ET reactive_snipe_on_own_rolls sont vrais).
                                           //    2. Les snipes de cœur de valeur kakera externes DÉCALÉS (utilise `snipe_delay`).
    "kakera_snipe_threshold": 100,         // (Par défaut: 0) Valeur kakera minimale pour déclencher les revendications de CŒUR mentionnées ci-dessus si `kakera_snipe_mode` est vrai.

    // Autre (Actif uniquement si "rolling: true")
    "snipe_ignore_min_kakera_reset": false // (Par défaut: false) Si vrai, pour les revendications générales après le tirage, min_kakera est effectivement 0 si votre réinitialisation de revendication est à moins d'une heure.
                                           // Cela n'affecte PAS le sniping réactif ni les seuils de sniping de valeur kakera externe.
  }
  // Ajoutez d'autres préréglages pour d'autres comptes ici, séparés par des virgules.
}
```

---

## 🎮 Obtenir Votre Jeton Discord 🔑

Les self-bots nécessitent le jeton de votre compte Discord. **Ce jeton donne un accès complet à votre compte – gardez-le extrêmement privé ! Le partager, c'est comme donner votre mot de passe.** Il est recommandé d'utiliser ce bot sur un compte alternatif.

1.  **Ouvrez Discord dans votre navigateur web** (ex: Chrome, Firefox). *Pas l'application de bureau.*
2.  Appuyez sur **F12** pour ouvrir les Outils de développement.
3.  Accédez à l'onglet **`Console`**.
4.  Collez l'extrait de code suivant dans la console et appuyez sur Entrée:
    ```javascript
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

## 🤝 Contribuer

Les contributions sont les bienvenues ! N'hésitez pas à signaler les problèmes, à suggérer des fonctionnalités ou à soumettre des requêtes de tirage au dépôt du projet.

**🙏 Veuillez utiliser cet outil de manière responsable et éthique, en étant pleinement conscient des risques potentiels pour votre compte Discord. 🙏**

**Bon Mudae (et Prudent) !** 😉

---
**Licence:** [Licence MIT](LICENSE)
