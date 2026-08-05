<p align="center">
  <h1 align="center">⚡ MudaRemote: automatisation de Mudae pour Discord</h1>
  <p align="center">
    <strong>Gérez les tirages, les captures, le Kakera et plusieurs profils depuis une seule application.</strong>
  </p>
  <p align="center">
    Gérez les tirages, les captures, la collecte de Kakera et plusieurs profils depuis une seule application.<br>
    Les options de temporisation ne garantissent ni l'absence de détection ni la sécurité du compte.
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Windows-Application_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows EXE"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.7.9-f97316?style=for-the-badge" alt="Version 4.7.9"></a>
  <a href="#"><img src="https://img.shields.io/badge/Status-Active_2026-10b981?style=for-the-badge" alt="Active 2026"></a>
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/Discord-Join_Server-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Server"></a>
</p>

<p align="center">
  <a href="README.md">English</a> •
  <a href="README.ja.md">日本語</a> •
  <a href="README.ko.md">한국어</a> •
  <a href="README.tr.md">Türkçe</a> •
  <a href="README.zh-CN.md">简体中文</a> •
  <a href="README.pt-BR.md">Português Brasileiro</a>
</p>

---

## 💖 Soutenir MudaRemote

MudaRemote est gratuit et open source. Si vous l'utilisez régulièrement et souhaitez soutenir le temps consacré à sa maintenance, vous pouvez faire un don. Cela reste facultatif.

Le serveur Discord compte **plus de 310 membres** qui utilisent l'application, signalent des problèmes et partagent leurs réglages.

### Objectif actuel

**Objectif financé à 40 % • 40 $ sur 100 $ grâce aux premiers soutiens • Mise à jour: août 2026**

Les dons soutiennent le temps consacré aux tâches suivantes :

- les correctifs de compatibilité et les tests de régression lorsque Discord ou Mudae change ;
- les versions Windows vérifiées, les sommes de contrôle et les mises à jour plus sûres ;
- la documentation, les traductions et l'aide directe à la communauté ;
- la résolution des fonctionnalités et bugs en attente.

Tous les montants sont appréciés. Pour vous donner un repère, vous pouvez choisir l'équivalent de **5 $**, **15 $** ou **30 $**. Il n'y a pas de minimum.

| Actif | Réseau | Adresse |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON (TRC20) | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> Vérifiez l'actif et le réseau avant l'envoi: une transaction crypto est irréversible. Pour recevoir le rôle **Donator** facultatif, envoyez au développeur un DM Discord avec l'identifiant de transaction ou une capture d'écran. Vous pouvez masquer les autres informations du portefeuille. **Ne partagez jamais une phrase de récupération ni une clé privée.** Tout montant confirmé donne droit au rôle.

Vous pouvez aussi aider en ajoutant une étoile au dépôt, en signalant un bug reproductible ou en répondant à une question sur Discord.

## ❓ À quoi sert MudaRemote ?

**MudaRemote** automatise les tâches répétitives du mini-jeu Mudae sur Discord.

Voici ce qu'il peut faire :

- 🎲 **Tirages automatiques**: envoie `$wa`, `$ha` ou une autre commande configurée.
- 💍 **Captures automatiques**: applique vos règles avant de tenter une capture.
- 💎 **Collecte de Kakera**: clique sur les types sélectionnés en tenant compte de l'énergie disponible.
- 🎯 **Suivi de wishlist**: Détecte les personnages configurés et tente immédiatement une capture lorsqu'elle est autorisée.
- 🤖 **Mudae slash commands bot**: Il peut utiliser `/wa` au lieu de `$wa` pour gagner 10% de kakera en plus.
- 👥 **Gestion de plusieurs comptes**: exécute plusieurs profils et coordonne leurs captures.
- 🕒 **Contrôles de temporisation**: Délais, périodes d'inactivité et attente d'un canal calme réduisent les séquences répétitives, sans garantie de sécurité.
- 🖥️ **Interface de réglages**: permet de gérer les options courantes et avancées.

> **⚠️ ATTENTION :** Ceci est un **self-bot**. Les self-bots sont **contre les règles de Discord**. Vous **pouvez être banni**. C'est pour **apprendre seulement**. Si vous l'utilisez, c'est **votre choix et votre risque**. Nous ne sommes pas responsables.

---

## 🏆 Pourquoi utiliser MudaRemote ?

| | Scripts simples | **MudaRemote** |
| :--- | :---: | :---: |
| Tirages | Souvent limités au texte | Texte et commandes slash prises en charge |
| Captures | Filtres simples | Wishlist, série, valeur, rang et propriétaire |
| Timing | Horaires fixes | Délais et périodes d'inactivité configurables |
| Comptes | Souvent un compte par processus | Plusieurs profils avec coordination |
| Réglages | Fichiers de configuration | Éditeur graphique de profils |
| Mises à jour | Remplacement manuel | Mises à jour vérifiées avec confirmation |

---

## ✨ Fonctionnalités

### 🎯 Correspondance et capture de personnages

Le bot surveille les tirages admissibles et applique vos règles avant de tenter une capture.

| Fonction | Ce qu'elle fait |
| :--- | :--- |
| **Capture de Wishlist** | Vous faites une liste de personnages. Le bot les capture dès qu'ils apparaissent. |
| **Capture par Série** | Tente de capturer les personnages des séries configurées. |
| **Capture par Valeur** | Tente les captures autorisées pour les personnages dépassant votre seuil de Kakera. |
| **Capture de Soi Instantanée** | Vérifie les correspondances pendant une série de tirages. |
| **Capture de Panique** | Peut choisir le personnage admissible le plus prioritaire en fin de période. |
| **Cartes d'Événements Gratuites** | Les personnages spéciaux de Noël ou du Nouvel An sont gratuits. Le bot les prend seul. |
| **Auto $rt** | `$rt` vous donne une capture en plus. Le bot l'utilise quand c'est nécessaire. |
| **Auto $rt après Capture** | Après avoir pris un personnage, le bot utilise `$rt` pour pouvoir en reprendre un autre. |
| **Liste Noire** | Ignore les personnages ajoutés à la liste. |
| **Vérif de Capture** | Après avoir essayé de capturer, le bot vérifie si ça a marché. |

---

### 💎 Kakera: Mudae Auto Kakera

Les kakeras sont les cristaux (boutons colorés) sur les tirages. Cliquer dessus donne de l'argent. Le bot le fait pour vous, mais intelligemment.

| Fonction | Ce qu'elle fait |
| :--- | :--- |
| **Clic Automatique** | Le bot clique sur les boutons de kakera pour vous. |
| **Ordre de Priorité** | Utilise l'ordre que vous avez défini lorsque plusieurs boutons sont disponibles. |
| **Gestion d'Énergie** | Cliquer coûte de l'énergie. Le bot surveille votre énergie pour ne pas cliquer si elle est trop basse. |
| **Auto $dk** | Plus d'énergie ? Le bot utilise `$dk` pour la remplir. |
| **Mode Chaos** | Les personnages avec 10+ clés ont des "kakera chaos": ça coûte 50% d'énergie en moins. |
| **Mode MK seulement** | Clique seulement sur les kakeras des tirages `$mk`. Économise beaucoup d'énergie. |
| **Détection de Sphères** | Détecte les sphères prises en charge, qui ne consomment pas d'énergie. |
| **Limites Perso** | Vous pouvez dire: "Clique sur kakeraY seulement si j'ai 80% d'énergie." |
| **Pas de Double Clic** | Le bot se souvient de ce qu'il a cliqué. Il ne gaspille pas d'énergie. |

---

### 🎲 Tirages: Auto Roll Mudae

Les tirages peuvent partir immédiatement, à une heure précise ou autour du prochain reset de capture.

| Fonction | Ce qu'elle fait |
| :--- | :--- |
| **Tirage Auto** | Envoie `$wa`, `$ha`, `$ma`, ou ce que vous voulez, automatiquement. |
| **Commandes Slash** | Utilise les commandes slash prises en charge et revient au texte si nécessaire. |
| **Timing Intelligent** | Peut organiser une série de tirages autour du prochain reset de capture. |
| **Heures Précises** | Vous pouvez dire "Fais les tirages à 14h00 et 18h30" et il le fera. |
| **Auto $us** | Vous avez des tirages en réserve ? Le bot les utilise. |
| **Auto $mk** | Utilise `$mk` pour avoir plus de kakera et clique sur le bouton qui sort. |
| **Auto $rolls** | Utilise la commande `$rolls` quand vous n'avez plus de tirages. |
| **Détection Bonus** | Si vous gagnez des tirages bonus en cliquant sur un kakera, le bot s'en sert. |
| **Mode Lurker** | Surveille les canaux configurés puis utilise vos propres tirages vers la fin de la fenêtre de capture. |
| **Farming de Clés** | Même sans pouvoir capturer, le bot tire pour vous donner des clés. |

---

### 🕒 Contrôles de temps et d'activité

Ces réglages varient les délais, mais ne rendent pas un self-bot invisible et ne garantissent pas la sécurité du compte.

| Fonction | Ce qu'elle fait |
| :--- | :--- |
| **Délais Aléatoires** | Attend une durée configurable entre 0 et 40 minutes. |
| **Surveillance du Chat** | Peut attendre lorsque le canal configuré a une conversation récente. |
| **Réactions Variées** | Pour capturer, il choisit un cœur au hasard: pas toujours le même. |
| **Délai Kakera** | Avant de cliquer sur un kakera, il attend un petit moment (0.3-1.0 sec). |
| **Mode Sommeil** | Suspend les actions automatiques pendant la plage horaire choisie. |
| **Détection Maintenance** | Mudae est en panne ? Le bot s'arrête et attend que tout revienne à la normale. |
| **Protection Limite Clés** | À la limite de 1 000 clés, le bot peut attendre une heure avant de reprendre. |
| **Slash seulement** | Lorsque ce mode est activé, aucune commande texte n'est envoyée si `/wa` échoue. |

---

### 👥 Multi-Comptes: Mudae Multi-Account Sync

Lancez le bot sur plusieurs comptes en même temps.

| Fonction | Ce qu'elle fait |
| :--- | :--- |
| **Synchro Principal** | Coordonne les réservations de capture entre les comptes configurés. |
| **Profils Séparés** | Chaque compte a son propre jeton (token) et ses propres réglages. |
| **Démarrage Décalé** | Décale le démarrage des profils pour éviter les commandes simultanées. |

---

### 🖥️ Interface de réglages facile (GUI)

Le programme `mudae_preset_editor.py` vous donne une fenêtre simple :
- ✅ Entrez votre jeton (token) et votre canal
- ✅ Cochez les cases pour activer les fonctions
- ✅ Ajoutez vos personnages préférés
- ✅ Enregistrez tout en un clic
- ✅ Démarrez le bot en un clic

---

## 🛠️ Comment installer (Étape par étape)

### Il vous faut :
- **[Python 3.8 ou plus récent](https://www.python.org/downloads/)**: Cochez la case ✅ **"Add to PATH"** à l'installation.
- Un jeton (token) Discord ([voir plus bas](#-comment-avoir-son-jeton-token-discord)).

### Étape 1: Télécharger le bot
```bash
git clone https://github.com/misutesu-desu/MudaRemote.git
cd MudaRemote
```
Ou cliquez sur **"Code" → "Download ZIP"** sur GitHub.

### Étape 2: Installer les outils
Ouvrez un terminal dans le dossier et tapez :
```bash
pip install -r requirements.txt
```

### Étape 3: Ouvrir les réglages
```bash
python mudae_preset_editor.py
```
Remplissez votre **token**, l'**ID du canal**, et cliquez sur **💾 Save Changes**.

### Étape 4: Lancer le bot
Cliquez sur le bouton **▶ Launch Bot** dans la fenêtre.

---

## 🔑 Comment avoir son jeton (token) Discord
1. Ouvrez **Discord dans votre navigateur** (pas l'application).
2. Appuyez sur **F12**.
3. Allez dans l'onglet **Console**.
4. Collez ceci et faites Entrée :
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
5. Copiez le jeton affiché dans MudaRemote. **Ne partagez ce jeton avec personne.**

---

## ⚠️ Avertissement (À lire !)
> **Ce programme est pour l'apprentissage uniquement.**
> Le self-botting est interdit par Discord. Vous risquez d'être banni à vie.
> Nous ne sommes pas responsables de votre compte. Utilisez-le sur des comptes sans importance.

---

<p align="center">
  <strong>⭐ Si le projet vous est utile, vous pouvez lui attribuer une étoile sur GitHub.</strong>
</p>
