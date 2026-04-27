# Plano de Execucao - youtube-analyzer

> Use este arquivo so para tarefas pendentes.
> Quando uma tarefa for concluida, remover daqui.

---

## ⏳ 1. Lembrete de deploy (permanente)

- Sempre que mudar settings/descricoes na api: `python -m app.seed` no console.
- Sempre que tiver migration nova: `alembic upgrade head` antes do seed.
- Pos-deploy do `web`: F5 no navegador (Next.js compila no build, sem etapa manual).

> **Nota Fase 5:** o seed adicionou `notifications.last_suggestions_count`
> (interna). Apos deploy desta versao da api, rodar `python -m app.seed`
> uma vez para inserir a chave; do contrario o sync ainda funciona, mas a
> primeira detecao de "sugestoes mudaram" cria a row sozinha.
