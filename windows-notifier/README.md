# RK YT Analyzer — Notificador do Windows

Programinha que fica em segundo plano no PC e mostra um **popup no canto da
tela** quando algum canal monitorado dispara **pico de views** (o alerta que
você liga por canal no Monitoramento, com o multiplicador — ex.: 2x).
Clicar no popup abre o **Analytics do site já filtrado naquele canal**.

- Sem instalação de dependências: usa só o Python padrão do Windows.
- Login uma vez só: a sessão "desktop" dura 1 ano e o token fica salvo em
  `%APPDATA%\RK-YT-Notifier\config.json`. Se a senha for trocada no site,
  ele pede login de novo.
- **Inicia junto com o Windows automaticamente** após o primeiro login
  (registro Run do usuário — pode desligar nas Configurações).
- Instância única: abrir duas vezes não duplica popups.
- Consulta a API a cada 60 segundos. O popup **fica na tela até você fechar**
  (✕) ou clicar nele — não some sozinho.
- **Som estilo game** ao chegar alerta (padrão: "Alerta arcade", 3 bips).
  Som e volume configuráveis (50% = volume de referência).

## Como usar

1. Tenha Python 3.10+ instalado (https://python.org, marcar "Add to PATH").
2. Dê dois cliques em `iniciar-notificador.bat` (roda sem janela de console).
3. Na primeira vez, faça login com o mesmo usuário/senha do site. A partir
   daí ele já se registra pra iniciar junto com o Windows.

## Configurações

Duas formas de abrir:

- Clique no **⚙** de qualquer popup; ou
- Dê dois cliques em `configurar-notificador.bat`.

Na janela dá pra:

- Ligar/desligar **"Iniciar junto com o Windows"**;
- Ajustar as URLs da **API** e do **site**;
- Escolher o **som** do alerta (estilo game: moeda, level up, power-up,
  alerta arcade, sino, fanfarra — ou sem som) e o **volume** (5–100%);
- **Sair da conta** (apaga o token — pede login de novo);
- **Encerrar o notificador**.

## Encerrar manualmente

Pelo botão "Encerrar notificador" nas Configurações, ou: Gerenciador de
Tarefas → `pythonw.exe` → Finalizar tarefa.

## Arquivo de configuração

`%APPDATA%\RK-YT-Notifier\config.json`:

- `api_url` — default `https://youtube-analyzer-api.duckdns.org`
- `site_url` — default `https://youtube-analyzer.duckdns.org`
- `autostart` — preferência de iniciar com o Windows
- `sound` / `volume` — som do alerta (gerado em `sounds\` ao lado do config)
- `token` / `last_seen_id` — gerenciados automaticamente (não mexer).
