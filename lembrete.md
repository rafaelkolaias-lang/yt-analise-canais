# Lembrete - ideias pendentes

## Arquivamento de trechos de videos removidos

Antes de implementar, perguntar ao usuario se ele quer fazer essa alteracao agora.

Perguntas obrigatorias:
- Quer salvar apenas metadados/thumbnails primeiro ou tambem trechos de video?
- Qual destino prefere: Google Drive, MEGA, storage proprio/VPS, S3/compatível ou outro?
- O arquivamento deve ser manual, automatico para candidatos fortes, ou misto?

Objetivo:
- Guardar material de estudo caso um video/canal seja removido do YouTube.
- Permitir entender o que havia no video e aprender a produzir conteudo de forma correta.
- Qualidade baixa e aceitavel; 480p e suficiente.

Ideias:
- Comecar com metadados, thumbnail e transcricao quando disponivel.
- Salvar frames ou thumbnails periodicos para reduzir armazenamento.
- Salvar trechos curtos em 480p, nao necessariamente o video inteiro.
- Arquivar video inteiro em 480p apenas para canais/videos muito relevantes.
- Aplicar limites de armazenamento, limite diario e politica de retencao.

Opcoes de armazenamento:
- Google Drive: facil de acessar e organizar, mas exige integracao OAuth/service account.
- MEGA: pode ter bastante espaco, mas a automacao precisa ser validada.
- Storage proprio/VPS: mais controle, mas exige disco, backup e limpeza.
- S3/compatível: mais robusto para automacao, mas pode ter custo recorrente.

Cuidados:
- Confirmar uso privado/de estudo.
- Nao redistribuir conteudo baixado.
- Nao salvar credenciais em texto puro.
- Pedir permissao antes de migration/banco.
- Pedir permissao antes de usar pasta de backup ou armazenamento externo.
