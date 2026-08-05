<p align="center">
  <h1 align="center">⚡ MudaRemote: automação de Mudae para Discord</h1>
  <p align="center">
    <strong>Gerencie rolls, claims, Kakera e várias contas em um só aplicativo.</strong>
  </p>
  <p align="center">
    Gerencie rolls, claims, coleta de Kakera e presets de várias contas em um único aplicativo.<br>
    Os controles de tempo não garantem que a conta não seja detectada ou punida.
  </p>
</p>

<p align="center">
  <a href="https://github.com/misutesu-desu/MudaRemote/releases/latest"><img src="https://img.shields.io/badge/Windows-Aplicativo_.exe-0078D6?style=for-the-badge&logo=windows&logoColor=white" alt="Windows EXE"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge" alt="MIT License"></a>
  <a href="https://github.com/misutesu-desu/MudaRemote/releases"><img src="https://img.shields.io/badge/Version-4.7.9-f97316?style=for-the-badge" alt="Version 4.7.9"></a>
  <a href="#"><img src="https://img.shields.io/badge/Status-Active_2026-10b981?style=for-the-badge" alt="Active 2026"></a>
  <a href="https://discord.gg/4WHXkDzuZx"><img src="https://img.shields.io/badge/Discord-Join_Server-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord Server"></a>
</p>

<p align="center">
  <a href="README.md">English</a> •
  <a href="README.fr.md">Français</a> •
  <a href="README.ja.md">日本語</a> •
  <a href="README.ko.md">한국어</a> •
  <a href="README.tr.md">Türkçe</a> •
  <a href="README.zh-CN.md">简体中文</a>
</p>

---

## 💖 Apoie o MudaRemote

O MudaRemote é gratuito e de código aberto. Se você usa o programa com frequência e quer apoiar o tempo dedicado à manutenção, pode fazer uma doação. Isso é totalmente opcional.

O servidor do Discord tem **mais de 310 membros** que usam o aplicativo, relatam problemas e compartilham configurações.

### Meta atual

**40% da meta financiada • US$ 40 de US$ 100 por apoiadores iniciais • Atualizado em agosto de 2026**

As doações apoiam o tempo dedicado a:

- correções de compatibilidade e testes de regressão quando Discord ou Mudae mudarem;
- versões verificadas para Windows, checksums e atualizações mais seguras;
- documentação, traduções e suporte direto à comunidade;
- resolver os recursos e bugs acumulados.

Qualquer valor é bem-vindo. Como referência, você pode escolher o equivalente a **US$ 5**, **US$ 15** ou **US$ 30**. Não há valor mínimo.

| Ativo | Rede | Endereço |
| :--- | :--- | :--- |
| **Litecoin (LTC)** | Litecoin | `LM16i4Sf34zmnGU35AuCmtyMSL3M4Nfutt` |
| **USDT** | TRON (TRC20) | `TQWeEprEbJyk1EcSHDk1pnn7rkgcsTBazp` |

> [!IMPORTANT]
> Confira o ativo e a rede antes de enviar; transações em cripto não podem ser revertidas. Para receber o cargo opcional de **Donator**, envie ao desenvolvedor uma DM no Discord com o ID da transação ou uma captura de tela. Você pode ocultar dados não relacionados da carteira. **Nunca compartilhe sua frase-semente ou chave privada.** Qualquer valor confirmado dá direito ao cargo.

Não quer doar agora? Dar uma estrela no GitHub, enviar um bom relatório de bug ou ajudar outro membro da comunidade também apoia o projeto.

## ❓ O que isso faz?

**MudaRemote** automatiza tarefas repetitivas do minijogo Mudae no Discord.

Principais recursos:

- 🎲 **Rolls automáticos**: envia `$wa`, `$ha` ou outro comando configurado.
- 💍 **Claims automáticos**: aplica suas regras antes de tentar um claim.
- 💎 **Coleta de Kakera**: clica nos tipos selecionados conforme a energia disponível.
- 🎯 **Monitoramento da wishlist**: Detecta personagens configurados e tenta um claim imediato quando permitido.
- 🤖 **Mudae slash commands bot**: Pode usar `/wa` em vez de `$wa` para ganhar 10% a mais de kakera.
- 👥 **Várias contas**: executa vários presets e coordena claims entre contas configuradas.
- 🕒 **Controles de tempo**: Atrasos, horários inativos e espera por canal silencioso reduzem padrões repetitivos, sem garantia de segurança.
- 🖥️ **Interface de configuração**: reúne opções comuns e avançadas no editor de presets.

> **⚠️ AVISO:** Isto é um **self-bot**. Self-bots são **contra as regras do Discord**. Você **pode ser banido**. Isto é apenas para **aprendizado**. Se usar, é **sua escolha e seu risco**. Não somos responsáveis.

---

## 🏆 Por que usar o MudaRemote?

| | Scripts básicos | **MudaRemote** |
| :--- | :---: | :---: |
| Rolls | Geralmente apenas texto | Texto e comandos slash compatíveis |
| Claims | Filtros básicos | Wishlist, série, valor, ranking e proprietário |
| Horários | Agenda fixa | Atrasos e períodos inativos configuráveis |
| Contas | Geralmente uma por processo | Vários presets com coordenação |
| Configuração | Arquivos manuais | Editor gráfico de presets |
| Atualizações | Substituição manual | Atualizações verificadas com confirmação |

---

## ✨ Recursos

### 🎯 Correspondência e claim de personagens

O bot monitora rolls elegíveis e aplica suas regras antes de tentar um claim.

| Recurso | O Que Faz |
| :--- | :--- |
| **Resgate da Wishlist** | Você faz uma lista de personagens que quer. O bot resgata na hora que eles aparecem. |
| **Resgate por Série** | Tenta claims de personagens das séries configuradas. |
| **Claim por Valor** | Tenta claims permitidos em personagens acima do limite de Kakera definido por você. |
| **Auto-Resgate Instantâneo** | Verifica correspondências durante uma sequência de rolls. |
| **Resgate de Pânico** | Pode usar a opção elegível de maior prioridade perto do fim da janela. |
| **Cartas de Evento Grátis** | Personagens de Natal ou Ano Novo são grátis. O bot pega automaticamente. |
| **Auto $rt** | `$rt` te dá um resgate extra. O bot usa sozinho quando você precisa. |
| **Auto $rt após Resgate** | Depois de resgatar alguém, o bot usa `$rt` na hora para poder resgatar de novo. |
| **Lista de Evitados** | Ignora os personagens adicionados à lista. |
| **Verificador de Resgate** | Depois de tentar resgatar, o bot confere se funcionou mesmo. |

---

### 💎 Kakera: Mudae Auto Kakera

Kakeras são os cristais (botões coloridos) que aparecem nos rolos. Clicar neles dá dinheiro. O bot clica para você: mas é esperto.

| Recurso | O Que Faz |
| :--- | :--- |
| **Clique Automático** | O bot clica nos botões de kakera sozinho nos seus rolos e nos dos outros. |
| **Ordem de Prioridade** | Usa a ordem definida por você quando há vários botões. |
| **Seguir Energia** | Clicar em kakera custa energia. O bot olha sua energia e não clica se estiver baixa. |
| **Auto $dk** | Energia baixa? O bot usa `$dk` para encher. |
| **Modo Caos** | Personagens com 10+ keys têm "caos kakera": custa 50% menos energia. O bot pode focar só neles. |
| **Modo Só MK** | Só clica em kakera de rolos `$mk`. Ignora todo o resto: economiza muita energia. |
| **Detectar Spheres** | Detecta spheres compatíveis, que não consomem energia. |
| **Limites Próprios** | Pode dizer "só clique em kakeraY se eu tiver 80%+ de energia." O bot obedece. |
| **Sem Cliques Duplos** | O bot lembra o que já clicou. Nunca gasta energia clicando na mesma coisa de novo. |

---

### 🎲 Rolar: Auto Roll Mudae

Os rolls podem começar imediatamente, em horários marcados ou perto do próximo reset de claim.

| Recurso | O Que Faz |
| :--- | :--- |
| **Rolo Automático** | Envia `$wa`, `$ha`, `$ma`, ou qualquer um que você queira. |
| **Comandos Slash** | Usa comandos slash compatíveis e volta ao texto quando necessário. |
| **Timing Inteligente** | Pode organizar uma sequência de rolls em torno do próximo reset de claim. |
| **Horários Marcados** | Pode dizer "role às 14:00 e 18:30 todo dia" e ele fará. |
| **Auto $us** | Tem rolos guardados? O bot usa sozinho. Pode colocar um limite. |
| **Auto $mk** | Usa `$mk` para ganhar rolos extras de kakera e clica na kakera que vier. |
| **Auto $rolls** | Usa o comando `$rolls` quando seus rolos acabarem. |
| **Detectar Rolo Bônus** | Às vezes clicar em kakera dá rolos extras. O bot vê e usa na hora. |
| **Modo Lurker** | Monitora os canais configurados e usa seus próprios rolls perto do fim da janela de claim. |
| **Farming de Keys** | Mesmo sem resgate, o bot continua rolando para você ganhar keys. |

---

### 🕒 Controles de tempo e atividade

Essas opções apenas variam o tempo das ações. Elas não tornam um self-bot invisível nem garantem a segurança da conta.

| Recurso | O Que Faz |
| :--- | :--- |
| **Atrasos Aleatórios** | Espera um intervalo configurável entre 0 e 40 minutos. |
| **Olhar Canal** | Pode aguardar quando há conversa recente no canal configurado. |
| **Reações Variadas** | Ao resgatar com emoji, ele escolhe um coração diferente cada vez: não é sempre o mesmo. |
| **Atraso de Kakera** | Antes de clicar em kakera, ele espera um tempinho aleatório (0.3-1.0 seg). Nem rápido demais, nem lerdo. |
| **Hora de Dormir** | Suspende as ações automáticas durante o período configurado. |
| **Detectar Manutenção** | Mudae entrou em manutenção? O bot vê e para. Quando volta, ele espera o canal acalmar antes de girar. |
| **Proteção de Limite de Keys** | Chegou em 1.000 keys? O bot para por 1 hora. Nada de comportamento suspeito. |
| **Só Slash** | Nesse modo, nenhuma opção de texto é enviada quando `/wa` falha. |

---

### 👥 Multi-Contas: Mudae Multi-Account Sync

Rode o bot em muitas contas ao mesmo tempo. Cada uma com o seu jeito.

| Recurso | O Que Faz |
| :--- | :--- |
| **Sincronia com Principal** | Sua conta secundária vê que a principal quer alguém ("Wished by @Principal"). Ela resgata NA HORA. |
| **Perfies Separados** | Cada conta tem seu token, canal e lista próprios. |
| **Rodar Tudo Junto** | Use `--all` para começar todas as contas de uma vez. |
| **Início Escalonado** | Separa o início dos presets para evitar comandos simultâneos. |
| **Auto Reinício** | Se uma conta cair, ela volta sozinha depois de 60 segundos. |

---

### 🖥️ Janela de Configuração Fácil (GUI)

Você não precisa mexer em arquivos. O programa `mudae_preset_editor.py` te dá uma janela onde você pode:

- ✅ Colocar seu token e ID do canal
- ✅ Ligar e desligar funções marcando caixinhas
- ✅ Adicionar personagens na wishlist
- ✅ Arrumar regras de kakera
- ✅ Salvar tudo com um clique
- ✅ Começar o bot com um clique
- ✅ Copiar perfis (para criar alts rápido)
- ✅ Colocar para "Iniciar com o Windows"

A janela tem **tema escuro** e tudo explicadinho.

---

### 🔄 Atualizações Automáticas

Toda vez que você abre o bot, ele olha no GitHub se tem versão nova. Se tiver:

1. Ele baixa os arquivos novos
2. Faz cópia dos velhos (por segurança)
3. Troca os arquivos
4. Abre sozinho em uma janela nova

O programa pede confirmação antes de aplicar uma atualização disponível.

---

## 🛠️ Como Instalar (Passo a Passo)

### Você Precisa de

- **[Python 3.8 ou mais novo](https://www.python.org/downloads/)**: Ao instalar, marque ✅ **"Add to PATH"**
- Um token do Discord ([veja abaixo](#-como-pegar-seu-token-do-discord))

### Passo 1: Baixar o Bot

```bash
git clone https://github.com/misutesu-desu/MudaRemote.git
cd MudaRemote
```

Ou clique em **"Code" → "Download ZIP"** no GitHub e descompacte.

### Passo 2: Instalar o que o bot precisa

Abra o terminal (Prompt de Comando) na pasta do MudaRemote e digite:

```bash
pip install -r requirements.txt
```

Espere terminar.

### Passo 3: Abrir a Janela de Configurações

```bash
python mudae_preset_editor.py
```

Uma janela vai abrir. Preencha:
1. Seu **token do Discord** (veja abaixo como pegar)
2. O **ID do Canal** (botão direito no canal → "Copiar ID do Canal")
3. Seu **comando de rolo** (normalmente `wa`)
4. O que mais você quiser

Depois clique em **💾 Save Changes**.

### Passo 4: Começar o Bot

**Jeito fácil:** Clique no botão **▶ Launch Bot** na janela de configurações.

**Ou pelo terminal:**
```bash
# Começar um perfil só
python mudae_bot.py --preset "MinhaConta"

# Começar TODOS os perfis
python mudae_bot.py --all

# Abrir o menu pra escolher
python mudae_bot.py
```

**Pronto. O bot está rodando.** 🎉

---

## 🔑 Como pegar seu Token do Discord

1. Abra o **Discord no navegador** (não use o app)
2. Aperte **F12** no teclado
3. Clique na aba **Console**
4. Cole isto e aperte Enter:
   ```javascript
   window.webpackChunkdiscord_app.push([[Symbol()],{},req=>{for(const m of Object.values(req.c)){if(m.exports?.getToken)console.log(m.exports.getToken())}}]);
   ```
5. Vai aparecer um texto longo: esse é o seu token
6. **Não compartilhe esse token. Quem tiver acesso a ele poderá acessar sua conta.**

---

## ⚠️ Aviso (Leia!)

> **Este programa é apenas para estudo.**
>
> MudaRemote é um self-bot. Self-bots são **contra as regras do Discord**.
>
> Se você usar, você pode:
> - ❌ **Ser banido do Discord** (para sempre)
> - ❌ **Ser expulso de servidores**
> - ❌ **Ter todos os seus personagens de Mudae deletados**
>
> **Nós NÃO somos responsáveis** se algo ruim acontecer com sua conta.
>
> **Só use em contas que você não se importa de perder.**

---

<p align="center">
  <strong>⭐ Se o projeto for útil para você, considere dar uma estrela no GitHub.</strong>
</p>
