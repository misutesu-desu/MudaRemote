# ⚡ MudaRemote : L'outil d'automatisation ultime pour le bot Mudae

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.3.3-orange.svg)](https://github.com/misutesu-desu/MudaRemote/releases)
[![Status](https://img.shields.io/badge/Status-Actif_2026-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Rejoindre%20le%20serveur-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[English](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md) | [Português Brasileiro](README.pt-BR.md)

**MudaRemote** est le moteur d'automatisation le plus sophistiqué et le plus riche en fonctionnalités conçu spécifiquement pour le **bot Discord Mudae**. Il va bien au-delà des simples macros en analysant les données en temps réel ($tu, embeds, composants) pour simuler un comportement humain tout en maximisant l'efficacité de votre harem.

> **⚠️ AVERTISSEMENT CRITIQUE :** MudaRemote est un **SELF-BOT**. L'utilisation de self-bots enfreint les conditions d'utilisation de Discord et comporte un risque de bannissement permanent. **À utiliser à vos propres risques.**

---

## 🏆 Pourquoi MudaRemote ? (Comparaison)

Ne vous contentez pas de scripts datant de 2021. Passez au standard de 2025.

| Fonctionnalité | Bots Mudae ordinaires | **MudaRemote v3.3.3** |
| :--- | :--- | :--- |
| **Timing des Rolls** | Timers constants/aléatoires | **Synchronisation stratégique (Claim parfait)** |
| **Moteur de commandes** | Texte uniquement | **Commandes Slash (Support API moderne)** |
| **Gestion $rt** | Aucune / Manuelle | **Intelligence entièrement automatisée** |
| **Mises à jour** | Téléchargement manuel | **Système de mise à jour automatique intégré** |
| **Furtivité** | Délais statiques | **Jitter humain et observateur d'inactivité** |
| **Localisation** | Anglais uniquement | **4 langues entièrement supportées** |

---

## ✨ Fonctionnalités clés à fort impact

### 🎨 Nouveau : Éditeur de Préréglages Graphique
*   **Configuration Visuelle :** Fini l'édition manuelle du JSON ! Utilisez `mudae_preset_editor.py` pour gérer tous vos préréglages via une interface graphique élégante en mode sombre.
*   **Personnalisation Facile :** Activez ou désactivez les emojis de claim et de kakera avec une logique de repli intelligente.
*   **Démarrage en un Clic :** Lancez le bot directement depuis l'éditeur.

### 🎯 Écosystème de Snipe Avancé
*   **Snipe de Wishlist & Séries :** Réclame instantanément les personnages ou des séries entières d'anime rollés par d'autres.
*   **Sniper de Kakera Intelligent :** Définissez un seuil (ex: 200+) et laissez le bot sécuriser la valeur automatiquement (Supporte désormais **Kakera D & C**).
*   **Spécialiste de Sphères :** Détecte et sécurise les **Sphères** (SpU, SpD, etc.) via un mécanisme de bypass sans énergie — garantissant de ne jamais rater ces drops rares.
*   **Farming de Kakera Global :** Scanne tous les messages pour les cristaux. Inclut un **filtrage intelligent** pour ne prendre que chez des utilisateurs spécifiques (comme vos alts) afin de rester discret.
*   **Mode Chaos :** Logique spécialisée pour les Chaos Keys (personnages à 10+ clés).

### 🤖 Automatisation Intelligente (Le "Cerveau")
*   **Timing de Roll Stratégique :** Le bot retient les rolls juste avant la réinitialisation de votre claim, garantissant que vous ne gaspillez jamais un roll pendant que votre claim est en recharge.
*   **Moteur de Commandes Slash :** Utilise optionnellement `/wa`, `/ha`, etc., qui sont plus rapides et nettement plus sûrs contre la détection de Discord.
*   **Utilisation Intelligente du $rt :** Détecte automatiquement si le `$rt` est disponible et ne l'utilise que pour les cibles prioritaires de la wishlist.
*   **Gestion de l'Énergie DK :** Optimise votre utilisation de l'énergie Kakera pour vous assurer d'en avoir toujours assez pour les réactions de haute valeur.

### 🛡️ Technologie Furtive & Anti-Ban
*   **Intervalles Humanisés :** Implémente un "jitter" (variation) aléatoire pour que votre activité ne ressemble jamais à une boucle de 60 minutes.
*   **Observateur d'Inactivité :** Détecte quand un salon est occupé et attend une accalmie dans la conversation avant de roller — agissant comme un utilisateur poli.
*   **Protection Limite de Clés :** S'arrête automatiquement si vous atteignez la limite quotidienne de 1 000 clés pour éviter d'être signalé.

---

## 🛠️ Démarrage Rapide

1.  **Prérequis** : [Python 3.8+](https://www.python.org/downloads/)
2.  **Installation** :
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **Exécution** :
    ```bash
    python mudae_preset_editor.py
    ```
    *Utilisez la nouvelle interface graphique élégante pour gérer les préréglages, puis cliquez sur **Run Bot** !*

    *(Alternativement, lancez `python mudae_bot.py` pour le menu console classique)*

---

## ⚙️ Configuration (`presets.json`)

Définissez plusieurs profils pour différents comptes ou serveurs.

```json
{
  "ComptePrincipal": {
    "token": "VOTRE_TOKEN",
    "channel_id": 123456789,
    "rolling": true,
    "use_slash_rolls": true,            // Recommandé
    "time_rolls_to_claim_reset": true, // Fonctionnalité unique
    "min_kakera": 200,
    "humanization_enabled": true,
    "wishlist": ["Makima", "Rem"]
  }
}
```
📖 **Besoin d'aide avec les paramètres ?** Consultez notre [Guide de Configuration détaillé (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)
---

## 🔒 Obtenir votre Token
1. Ouvrez Discord dans votre navigateur.
2. Appuyez sur `F12` -> `Console`.
3. Collez ceci :
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. **Ne partagez jamais ce token !**

---

**⭐ Si cet outil vous a aidé à agrandir votre harem, n'hésitez pas à lui donner une Étoile (Star) ! Cela aide le projet à grandir et à rester à jour.**
