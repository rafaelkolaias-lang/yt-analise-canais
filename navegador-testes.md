# 🌐 Guia de Testes via Navegador (para IAs) — MODELO LIMPO

> **Este é o arquivo-MESTRE (template).** Copie-o para a **raiz de cada projeto** e preencha a seção de Memória com o mapa daquele projeto. Mantenha este mestre **sem memória de projeto** (só o comportamento neutro).

> **Quando ler:** SOMENTE quando o usuário pedir explicitamente para entrar no navegador / testar a plataforma na interface real (ex.: "entra no navegador", "testa no navegador", "você pode testar lá"). Fora isso, não carregar.

> **Ao ser acionado, ANTES de tudo:** se o usuário **não informou a porta de debug (CDP)** do navegador, **pergunte a porta** (ex.: Dolphin Anty ou Chrome com `--remote-debugging-port`; portas típicas 8222 / 9222). Sem a porta não há como conectar.

> Este arquivo é **dinâmico e por plataforma**: ao descobrir um fluxo, seletor ou comportamento novo, **anote na seção da plataforma** (na cópia que fica na raiz do projeto), pra a próxima IA já saber onde clicar e o que esperar.

---

## 🧠 Princípio nº 1 — TEXTO é barato, SCREENSHOT é caro

Ler um screenshot custa ~50× mais tokens que ler texto. Portanto:

- O script deve **VERIFICAR e IMPRIMIR TEXTO** (PASS/FAIL, contagens, status, mensagens de toast, se um modal está visível) — em vez de tirar print pra "olhar".
- **Print só quando:** (a) for um detalhe visual que só se enxerga na imagem, ou (b) o usuário pedir pra ver. E aí **1 print**, não vários.
- **Agrupe passos por fase:** 1 execução de script = 1 bloco de resultado. Nunca "1 clique → 1 print → repete".
- Faça os scripts **auto-verificáveis** (eles mesmos imprimem `PASS`/`FAIL`).

## ⚙️ Setup do driver (sem poluir o projeto)

1. Confirmar CDP acessível: `curl -s http://localhost:<PORTA>/json/version` → deve retornar JSON com `webSocketDebuggerUrl`.
2. Driver leve: **`puppeteer-core`** (NÃO baixa navegador, só conecta). Instalar num diretório **scratch** (ex.: `C:\tmp\bt`), nunca no `node_modules` do projeto:
   - `mkdir C:\tmp\bt`, dentro: `npm init -y` e `npm i puppeteer-core`
3. Conectar à instância **já aberta**: `puppeteer.connect({ browserURL: 'http://localhost:<PORTA>', defaultViewport: null })`. Pegar a página existente (`browser.pages()`), não abrir nova aba.

## 🤖 Padrões de automação (apps Livewire / SPA)

- **Clicar por TEXTO visível**, não por seletor CSS frágil: varrer `button, a, [role=button], label` e achar o que contém o texto. O DOM do Livewire muda a cada render.
- **Esperar entre ações**: Livewire re-renderiza assíncrono. Use `waitForFunction(() => document.body.innerText.includes('<texto esperado>'))` antes do próximo passo (um `sleep` curto após o clique também ajuda).
- **Upload de arquivo**: achar `input[type=file]` (mesmo oculto) e `el.uploadFile('C:\\caminho\\arquivo')`. Com vários inputs, mirar pelo `accept`/`wire:model`.
- **Fechar modal clicando fora**: clicar no backdrop com `page.mouse.click(8, 8)` (canto, fora do painel).
- **Assert de modal visível**: checar no DOM se o painel do modal está renderizado E `offsetParent !== null`.
- **Toast**: ler o texto do elemento de toast logo após a ação.
- Reusar um **runner genérico** (`act.js`) que recebe uma lista de passos em JSON (`goto`, `clickText`, `fill`, `upload`, `waitText`, `hasText`, `backdrop`, `shot`). Cada fase vira um JSON de passos + um resultado de texto.

## ⚠️ Limites honestos (avisar o usuário)

- **Não dá pra confirmar a entrega no app do destinatário** (ex.: WhatsApp do celular) — só o lado do **PAINEL** (criado, status "Concluída/Enviado", nº de falhas, billing). A confirmação visual final (ex.: áudio virou nota de voz, PDF chegou) é com o usuário, olhando os aparelhos.
- Reportar fielmente: se um passo falhou (seletor não achado, toast de erro), dizer.

---

# 🗺️ MEMÓRIA — Mapa por plataforma

> **No mestre, esta seção fica VAZIA.** Na cópia da raiz do projeto, preencha uma seção por plataforma seguindo o modelo abaixo.

## <Nome da plataforma> — projeto `<repo>`

### Ambientes
- (URLs de homologue/produção; como o login está — já logado? credenciais?)

### Dados de teste
- (números/contas/arquivos de teste que podem ser usados sem risco)

### Navegação (sidebar / rotas)
- (itens de menu com o texto exato + rotas)

### Fluxos principais
- (passo a passo dos fluxos que você testa: botões, o que esperar em cada etapa)

### Modais / confirmações
- (como abrem/fecham; o que validar)

### Armadilhas conhecidas
- (re-render assíncrono, seletores chatos, coisas que não dá pra verificar pelo painel)
