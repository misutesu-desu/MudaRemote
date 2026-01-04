# ⚡ MudaRemote: A Ferramenta Definitiva de Automação para o Mudae Bot

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-3.0.7-orange.svg)](https://github.com/misutesu-desu/MudaRemote/releases)
[![Status](https://img.shields.io/badge/Status-Ativo_2026-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Entrar%20no%20Servidor-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[English](README.md) | [Français](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md)

**MudaRemote** é o motor de automação mais sofisticado e rico em recursos projetado especificamente para o **Mudae Discord Bot**. Ele vai muito além de simples macros, analisando dados em tempo real ($tu, embeds, componentes) para simular um comportamento humano enquanto maximiza a eficiência do seu harem.

> **⚠️ AVISO CRÍTICO:** O MudaRemote é um **SELF-BOT**. O uso de self-bots viola os Termos de Serviço (ToS) do Discord e acarreta risco de banimento permanente. **Use por sua conta e risco.**

---

## 🏆 Por que o MudaRemote? (Comparação)

Não se contente com scripts da era de 2021. Atualize para o padrão de 2025.

| Recurso | Bots Comuns de Mudae | **MudaRemote v3.0.7** |
| :--- | :--- | :--- |
| **Timing de Rolls** | Timers Constantes/Aleatórios | **Sincronização Estratégica (Claim perfeito)** |
| **Motor de Comandos** | Apenas Texto | **Slash Commands (Suporte à API Moderna)** |
| **Gerenciamento de $rt** | Nenhum / Manual | **Inteligência Totalmente Automatizada** |
| **Atualizações** | Re-download Manual | **Sistema de Auto-Update Integrado** |
| **Furtividade (Stealth)** | Delays Estáticos | **Jitter Humano e Monitor de Inatividade** |
| **Localização** | Apenas Inglês | **Suporte Total a 4 Idiomas** |

---

## ✨ Principais Recursos de Alto Impacto

### 🎯 Ecossistema Avançado de Sniping
*   **Sniping de Wishlist e Séries:** Reivindica instantaneamente personagens ou séries inteiras de anime que outros usuários rodarem.
*   **Sniper de Kakera Inteligente:** Defina um limite (ex: 200+) e deixe o bot garantir o valor automaticamente.
*   **Farming Global de Kakera:** Escaneia todas as mensagens em busca de cristais. Inclui **Filtragem Inteligente** para coletar apenas de usuários específicos (como seus fakes/alts) para não chamar atenção.
*   **Modo Caos:** Lógica especializada para Chaos Keys (personagens com 10+ keys).

### 🤖 Automação Inteligente (O "Cérebro")
*   **Timing Estratégico de Rolls:** O bot segura os rolls até pouco antes do seu reset de claim, garantindo que você nunca desperdice um roll enquanto seu claim estiver em cooldown.
*   **Motor de Slash Commands:** Opcionalmente usa `/wa`, `/ha`, etc., que são mais rápidos e significativamente mais seguros contra a detecção do Discord.
*   **Utilização Inteligente de $rt:** Detecta automaticamente se o `$rt` está disponível e o usa apenas para alvos de wishlist de alta prioridade.
*   **Gerenciamento de Energia DK:** Otimiza o uso do seu poder de Kakera para garantir que você sempre tenha o suficiente para reacts de alto valor.

### 🛡️ Tecnologia Furtiva e Anti-Ban
*   **Intervalos Humanizados:** Implementa um "jitter" (variação) aleatório para que sua atividade nunca pareça um loop de 60 minutos.
*   **Monitor de Inatividade:** Detecta quando um canal está movimentado e espera por uma pausa na conversa antes de rodar — agindo como um usuário educado.
*   **Proteção de Limite de Keys:** Pausa automaticamente se você atingir o limite diário de 1.000 keys para evitar sinalizações.

---

## 🛠️ Início Rápido

1.  **Requisitos**: [Python 3.8+](https://www.python.org/downloads/)
2.  **Instalação**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **Execução**:
    ```bash
    python mudae_bot.py
    ```
    *Selecione seu preset no menu interativo e você está pronto!*

---

## ⚙️ Configuração (`presets.json`)

Defina múltiplos perfis para diferentes contas ou servidores.

```json
{
  "ContaPrincipal": {
    "token": "SEU_TOKEN",
    "channel_id": 123456789,
    "rolling": true,
    "use_slash_rolls": true,            // Recomendado
    "time_rolls_to_claim_reset": true, // Recurso Exclusivo
    "min_kakera": 200,
    "humanization_enabled": true,
    "wishlist": ["Makima", "Rem"]
  }
}
```
📖 **Precisa de ajuda com as configurações?** Confira nosso [Guia de Configuração detalhado (Wiki)](https://github.com/misutesu-desu/MudaRemote/wiki/Configuration-Guide)
---

## 🔒 Obtendo seu Token
1. Abra o Discord no seu Navegador.
2. Pressione `F12` -> `Console`.
3. Cole o código:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
4. **Nunca compartilhe este token!**

---

**⭐ Se esta ferramenta te ajudou a aumentar seu harem, por favor, deixe uma Estrela (Star)! Isso ajuda o projeto a crescer e a manter-se atualizado.**

