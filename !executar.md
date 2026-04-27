# Plano de Execucao - youtube-analyzer

> Use este arquivo so para tarefas pendentes.
> Quando uma tarefa for concluida, remover daqui.
> O historico real de entrega fica no `git log`.

---

## Tarefas Pendentes

## ⏳ 1. Lembrete de deploy de settings/descricoes/analytics-sugestoes

Status: PENDENTE

### Objetivo
Nao esquecer os passos manuais necessarios quando houver deploy da `api` com mudancas de settings, descricoes ou novas keys.

### Escopo
- No deploy futuro da `api`, lembrar de rodar no console:
```bash
cd /app
python -m app.seed
```
- Quando houver migration nova, rodar tambem:
```bash
cd /app
alembic upgrade head
```
- No deploy do `web`, lembrar de publicar junto as mudancas visuais relacionadas.

### Criterios de aceite
- Antes de cada deploy relevante da `api`, esse lembrete ainda esta visivel aqui.

### Possiveis armadilhas
- Esquecer o `python -m app.seed` depois de mudar defaults/descricoes/chaves e achar que a API ou a tela de configuracoes estao erradas.
- Esquecer `alembic upgrade head` quando a entrega tiver migration nova.
