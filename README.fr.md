# ⚡ MudaRemote: L'Outil Ultime d'Automatisation Mudae ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-2.8.0-orange.svg)]()
[![Status](https://img.shields.io/badge/Status-Actif-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Rejoindre-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

> **⚠️ AVERTISSEMENT CRITIQUE ⚠️**
> 
> **MudaRemote est un SELF-BOT.** L'automatisation des comptes utilisateurs est une violation des [Conditions d'Utilisation de Discord](https://discord.com/terms). 
> L'utilisation de cet outil comporte un risque de suspension ou de bannissement de compte. **Utilisez à vos propres risques.** Les développeurs déclinent toute responsabilité quant aux conséquences.

---

## 🚀 Vue d'ensemble

**MudaRemote** est un moteur d'automatisation haute performance et riche en fonctionnalités conçu spécifiquement pour le bot Discord Mudae. Il va bien au-delà de la simple macro de "roll" automatique, offrant une gestion intelligente de l'état, des capacités de snipe chirurgicales et une humanisation avancée pour garder votre compte en sécurité tout en maximisant l'efficacité de votre harem.

Contrairement aux macros basiques, MudaRemote analyse les réponses de Mudae en temps réel ($tu, messages, embeds) pour prendre des décisions intelligentes sur quand lancer des rolls, quand dormir et quoi claim.

---

## ✨ Fonctionnalités Clés

### 🎯 Écosystème de Snipe Avancé
*   **Snipe de Wishlist**: Claim instantanément les personnages de votre `wishlist` qui sont rollés par *d'autres utilisateurs*.
*   **Snipe de Série**: Ciblez une série entière ! Si quelqu'un roll un personnage d'une série suivie, il est à vous.
*   **Snipe de Valeur Kakera**: Snipe automatiquement *n'importe quel* personnage (même hors wishlist) si sa valeur kakera dépasse votre seuil.
*   **Farming Global de Kakera**: Le bot surveille **chaque** message pour les boutons de réaction kakera.
    *   *Nouveau:* **Filtrage Intelligent**: Configurez-le pour voler uniquement les kakera d'utilisateurs spécifiques (ex: vos comptes secondaires) pour éviter les drames sur le serveur.
    *   *Nouveau:* **Mode Chaos**: Gestion intelligente des Clés du Chaos vs Kakera Normal.

### 🤖 Automatisation Intelligente
*   **Rolling Intelligent**: Gère automatiquement les rolls horaires ($wa, $hg, $ma, etc.) et suit votre reset $daily.
*   **Moteur de Commandes Slash**: Utilise optionnellement les `/commandes` Discord modernes pour les rolls, ce qui est plus rapide et souvent moins limité en taux que les commandes textuelles classiques.
*   **Configuration d'Emoji Personnalisée**: 
    *   *Nouveau:* Personnalisez votre bot! Des listes personnalisées pour les cœurs de claim, les cristaux de kakera et les clés de chaos peuvent désormais être définies par preset.
*   **Optimisation du Reset Timer ($rt)**: 
    *   Détection intelligente et exécution automatique du `$rt` pour sécuriser plusieurs cibles de haute valeur.
*   **Système de Mise à Jour Automatique**: 
    *   Détecte automatiquement les nouvelles versions sur le dépôt distant et met à jour le script localement.

### 🛡️ Discrétion & Sécurité
*   **Intervalles Humanisés**: Finis les minuteurs robotiques de 60 minutes. Le bot ajoute un "jitter" aléatoire à chaque période d'attente.
*   **Observateur d'Inactivité**: Détecte quand un canal est occupé et attend une accalmie dans la conversation avant de spammer les rolls, simulant un utilisateur humain poli.
*   **Détection de Limite de Clés**: Met automatiquement les rolls en pause si vous atteignez la limite de clés Mudae.

---

## 🛠️ Installation

1.  **Prérequis**:
    *   Installez [Python 3.8](https://www.python.org/downloads/) ou supérieur.
2.  **Installer les Dépendances**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **Configuration**:
    *   Téléchargez ce dépôt.
    *   Créez un fichier `presets.json` (voir configuration ci-dessous).

---

## ⚙️ Configuration (`presets.json`)

Tous les paramètres sont gérés dans `presets.json`. Vous pouvez définir plusieurs profils de bot (ex: "ComptePrincipal", "CompteSecondaire") et les exécuter simultanément.

```json
{
  "MonSuperBotMuda": {
    "token": "VOTRE_TOKEN_DISCORD_ICI",
    "channel_id": 123456789012345678,
    "prefix": "!", 
    "mudae_prefix": "$",
    "roll_command": "wa",

    "// --- PARAMÈTRES DE BASE ---": "",
    "rolling": true,                       // Mettre à false pour le mode "Snipe Seul" (pas de roll, juste surveillance)
    "min_kakera": 200,                     // Valeur minimale pour claim un personnage durant vos propres rolls
    "delay_seconds": 2,                    // Délai de traitement de base
    "roll_speed": 1.5,                     // Secondes entre les commandes de roll

    "// --- CONFIGURATION SNIPE ---": "",
    "snipe_mode": true,                    // Interrupteur principal pour le snipe Wishlist
    "wishlist": ["Makima", "Rem"],         // Liste des noms exacts de personnages à sniper
    "snipe_delay": 0.5,                    // Vitesse de snipe (secondes)
    
    "series_snipe_mode": true,
    "series_wishlist": ["Chainsaw Man"],   // Liste des noms de séries à sniper
    "series_snipe_delay": 1.0,

    "// --- FARMING KAKERA ---": "",
    "kakera_reaction_snipe_mode": true,    // Cliquer sur les boutons kakera de N'IMPORTE QUEL message ?
    "kakera_reaction_snipe_delay": 0.8,
    "kakera_reaction_snipe_targets": [     // OPTIONNEL: Voler uniquement ces utilisateurs (ex: vos alts)
        "nom_utilisateur_mon_alt"
    ],
    "only_chaos": false,                   // Si true, réagit uniquement aux cristaux Clé du Chaos (violets).

    "// --- LOGIQUE AVANCÉE ---": "",
    "use_slash_rolls": true,               // Utiliser /wa au lieu de $wa (Fortement Recommandé)
    "dk_power_management": true,           // Économiser les charges $dk pour quand vous en avez vraiment besoin
    "snipe_ignore_min_kakera_reset": true, // Claim N'IMPORTE QUEL perso si le reset est dans < 1 heure.
    "key_mode": false,                     // Continuer à roll pour les clés même sans claim disponible ?
    "time_rolls_to_claim_reset": true,    // Synchroniser les rolls avec le reset du claim (Efficacité Max)
    "rt_ignore_min_kakera_for_wishlist": false, // Utiliser $rt pour la wishlist même si kakera < min_kakera ?

    "// --- EMOJIS PERSONNALISÉS (Optionnel) ---": "",
    "claim_emojis": ["💖", "💗"],          // Cœurs personnalisés à cliquer
    "kakera_emojis": ["kakeraY", "kakeraO"], // Cristaux personnalisés
    "chaos_emojis": ["kakeraP"]            // Clés de chaos personnalisées (persos 10+ clés)

    "// --- HUMANISATION ---": "",
    "humanization_enabled": true,
    "humanization_window_minutes": 30,     // Attendre aléatoirement 0-30 min de plus après le reset
    "humanization_inactivity_seconds": 10  // Attendre 10s de silence dans le canal avant de roll
  }
}
```

---

## 🎮 Utilisation

1.  Ouvrez votre terminal dans le dossier du bot.
2.  Lancez le script:
    ```bash
    python mudae_bot.py
    ```
3.  Sélectionnez votre preset dans le menu.
4.  Détendez-vous et regardez le harem grandir. 📈

---

## 🔒 Obtenir Votre Token

1.  Connectez-vous à Discord dans votre navigateur (Chrome/Firefox).
2.  Appuyez sur **F12** (Outils de développement) -> onglet **Console**.
3.  Collez ce code pour révéler votre token:
    ```javascript
    window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
    ```
    *(Note: Ne partagez jamais ce token avec quiconque. Il donne un accès total à votre compte.)*

---

**Bonne Chasse !** 💖
