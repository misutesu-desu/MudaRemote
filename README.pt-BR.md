# ⚡ MudaRemote: A Ferramenta Suprema de Automoção para Mudae ⚡

[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![Discord](https://img.shields.io/badge/Discord-Selfbot-7289DA.svg)](https://discord.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Versão](https://img.shields.io/badge/Version-2.8.0-orange.svg)]()
[![Status](https://img.shields.io/badge/Status-Active-success.svg)]()
[![Discord Server](https://img.shields.io/badge/Discord-Entrar-7289DA?logo=discord&logoColor=white)](https://discord.gg/4WHXkDzuZx)

[English](README.md) | [Français](README.fr.md) | [日本語](README.ja.md) | [한국어](README.ko.md) | [Türkçe](README.tr.md) | [简体中文](README.zh-CN.md)

> **⚠️ AVISO CRÍTICO ⚠️**
> 
> **MudaRemote é um SELF-BOT.** Automatizar contas de usuário é uma violação dos [Termos de Serviço do Discord](https://discord.com/terms). 
> O uso desta ferramenta acarreta risco de suspensão ou banimento da conta. **Use por sua própria conta e risco.** Os desenvolvedores não aceitam responsabilidade por quaisquer consequências.

---

## 🚀 Visão Geral

**MudaRemote** é um motor de automação de alto desempenho e rico em recursos, projetado especificamente para o bot Mudae no Discord. Ele vai muito além de simples rolagens automáticas, oferecendo gerenciamento inteligente de estado, capacidades cirúrgicas de "sniping" (roubo/interceptação) e humanização avançada para manter sua conta segura enquanto maximiza a eficiência do seu harém.

Ao contrário de macros básicos, o MudaRemote analisa as respostas do Mudae em tempo real ($tu, mensagens, embeds) para tomar decisões inteligentes sobre quando rodar, quando dormir e o que reivindicar.

---

## ✨ Principais Recursos

### 🎯 Ecossistema Avançado de Sniping
*   **Wishlist Sniping**: Reivindica instantaneamente personagens da sua `wishlist` que são rodados por *outros usuários*.
*   **Series Sniping**: Mire em séries inteiras! Se alguém rodar um personagem de uma série rastreada, ele é seu.
*   **Kakera Value Sniping**: "Snipa" automaticamente *qualquer* personagem (mesmo fora da wishlist) se o valor de kakera exceder seu limite.
*   **Global Kakera Farming**: O bot observa **todas** as mensagens em busca de botões de reação de kakera.
    *   *Novo:* **Filtragem Inteligente**: Configure para roubar kakera apenas de usuários específicos (ex: suas contas secundárias) para evitar dramas no servidor.
    *   *Novo:* **Modo Caos**: Manuseio inteligente de Chaves do Caos vs Kakera Normal.

### 🤖 Automação Inteligente
*   **Sistema de Atualização Automática**: 
    *   Detecta automaticamente novas versões no repositório remoto e atualiza o script localmente.
*   **Configuração de Emojis Personalizados**: 
    *   *Novo:* Personalize seu bot! Listas personalizadas para corações de reivindicação, cristais de kakera e chaves do caos agora podem ser definidas por preset.
*   **Otimização do Reset Timer ($rt)**: 
    *   Detecção inteligente e execução automática do `$rt` para garantir múltiplos alvos de alto valor.
*   **Tempo Estratégico de Rolagem**: 
    *   **Lógica Anti-Desperdício**: Se sua reivindicação estiver em cooldown, o bot sincroniza as rolagens para terminarem precisamente antes do reset, garantindo que cada roll conte para o novo ciclo.
*   **Modo Pânico**: Se o reset de reivindicação estiver a menos de 60 minutos (`snipe_ignore_min_kakera_reset`), o bot reduz seus padrões e reivindica *qualquer coisa* para evitar desperdiçar o cooldown.
*   **Gerenciamento de Poder DK**: Analisa o poder de reação e estoque em tempo real. Ele só consome uma carga `$dk` (Daily Kakera) quando o poder é realmente muito baixo para reagir.

### 🛡️ Furtividade e Segurança
*   **Intervalos Humanizados**: Chega de temporizadores robóticos de 60 minutos. O bot adiciona um "jitter" (variação) aleatório a cada período de espera.
*   **Monitor de Inatividade**: detecta quando um canal está ocupado e espera por uma calmaria na conversa antes de disparar rolagens, simulando um usuário humano educado.
*   **Detecção de Limite de Chaves**: Pausa automaticamente as rolagens se você atingir o limite de chaves do Mudae.

---

## 🛠️ Instalação

1.  **Pré-requisitos**:
    *   Instale [Python 3.8](https://www.python.org/downloads/) ou superior.
2.  **Instalar Dependências**:
    ```bash
    pip install discord.py-self inquirer requests
    ```
3.  **Configuração**:
    *   Baixe este repositório.
    *   Crie um arquivo `presets.json` (veja a configuração abaixo).

---

## ⚙️ Configuração (`presets.json`)

Todas as configurações são gerenciadas em `presets.json`. Você pode definir múltiplos perfis de bot (ex: "ContaPrincipal", "ContaSecundaria") e executá-los simultaneamente.

```json
{
  "MeuBotProMuda": {
    "token": "SEU_TOKEN_DISCORD_AQUI",
    "channel_id": 123456789012345678,
    "prefix": "!", 
    "mudae_prefix": "$",
    "roll_command": "wa",

    "// --- CONFIGURAÇÕES CENTRAIS ---": "",
    "rolling": true,                       // Defina como false para modo "Apenas Snipe" (sem rolar, apenas observar)
    "min_kakera": 200,                     // Valor mínimo para reivindicar um personagem durante suas próprias rolagens
    "delay_seconds": 2,                    // Atraso base de processamento
    "roll_speed": 1.5,                     // Segundos entre comandos de rolagem

    "// --- CONFIGURAÇÃO DE SNIPING ---": "",
    "snipe_mode": true,                    // Interruptor mestre para sniping de Wishlist
    "wishlist": ["Makima", "Rem"],         // Lista de nomes exatos de personagens para snipar
    "snipe_delay": 0.5,                    // Quão rápido snipar (segundos)
    
    "// --- SNIPING DE SÉRIE ---": "",
    "series_snipe_mode": true,
    "series_wishlist": ["Chainsaw Man"],   // Lista de nomes de séries para snipar
    "series_snipe_delay": 1.0,

    "// --- FARM DE KAKERA ---": "",
    "kakera_reaction_snipe_mode": true,    // Clicar em botões de kakera em QUALQUER mensagem?
    "kakera_reaction_snipe_delay": 0.8,
    "kakera_reaction_snipe_targets": [     // OPCIONAL: Apenas roubar desses usuários específicos (ex: suas alts)
        "nome_usuario_minha_alt"
    ],
    "only_chaos": false,                   // Se true, reage apenas a cristais de Chave do Caos (roxos).

    "// --- LÓGICA AVANÇADA ---": "",
    "use_slash_rolls": true,               // Usar /wa em vez de $wa (Altamente Recomendado)
    "dk_power_management": true,           // Economizar cargas de $dk para quando você realmente precisar
    "snipe_ignore_min_kakera_reset": true, // Reivindicar QUALQUER personagem se o reset de claim for em < 1 hora.
    "key_mode": false,                     // Continuar rodando por chaves mesmo se não puder reivindicar?
    "time_rolls_to_claim_reset": true,    // Sincronizar rolagens com o reset do claim (Máxima Eficiência)
    "rt_ignore_min_kakera_for_wishlist": false, // Usar $rt para wishlist mesmo se kakera < min_kakera?

    "// --- EMOJIS PERSONALIZADOS (Opcional) ---": "",
    "claim_emojis": ["💖", "💗"],          // Corações personalizados para clicar
    "kakera_emojis": ["kakeraY", "kakeraO"], // Cristais personalizados
    "chaos_emojis": ["kakeraP"],           // Chaves do caos personalizadas (persos 10+ chaves)

    "// --- HUMANIZAÇÃO ---": "",
    "humanization_enabled": true,
    "humanization_window_minutes": 30,     // Esperar aleatoriamente 0-30 mins extras após o reset
    "humanization_inactivity_seconds": 10  // Esperar por 10s de silêncio no canal antes de rodar
  }
}
```

---

## 🎮 Uso

1.  Abra seu terminal na pasta do bot.
2.  Execute o script:
    ```bash
    python mudae_bot.py
    ```
3.  Selecione seu preset no menu.
4.  Relaxe e veja o harém crescer. 📈

---

## 🔒 Obtendo Seu Token

1.  Entre no Discord pelo navegador (Chrome/Firefox).
2.  Pressione **F12** (Ferramentas do Desenvolvedor) -> guia **Console**.
3.  Cole este código para revelar seu token:
    ```javascript
    window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
    ```
    *(Nota: Nunca compartilhe este token com ninguém. Ele dá acesso total à sua conta.)*

---

**Boa Caçada!** 💖
