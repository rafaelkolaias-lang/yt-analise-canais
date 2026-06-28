# Bugs críticos descobertos — varredura colaborativa multi-IA

> **Como usar este arquivo:**
> - Múltiplas IAs estão varrendo a plataforma em paralelo procurando bugs e problema de segurança.
> - **Antes de adicionar um bug/problema**, faça `grep` aqui pra ver se já está documentado (mesmo arquivo/linha/sintoma).
> - **Critério "crítico":** mistura dados entre tenants, dado que deveria salvar e não salva, dado que deveria ser deletado e fica órfão, estados incoerentes, botões que não funcionam, falhas de segurança.
> - **Ignorar:** bugs já listados em `!executar.md` e os que estão como "concluído" aqui.
> - Cada bug deve descrever **QUANDO acontece** (linguagem leiga), arquivo/linha, severidade, e detalhe técnico opcional, e **qual o impacto** disso no usuário.
> - **Não corrigir nada** aqui — só catalogar pro humano testar e então pedir explicitamente depois para corrigir o bug.
> - **Status** Bugs achados devem colocar como pendente de correção e bugs arrumados colocar status concluido

---

## Convenção de severidade
> Cada um recebe uma nota onde nota 0 = indiferente não vai mudar nada pro usuario final nem pra segurança do sistema e 10 = Crítico ou muito grave para o sistema onde vai impedir o uso correto da plataforma.

- 🔴 **Crítico — Nota 9-10**
  Bugs que colocam o sistema, os dados ou os usuários em risco grave.  
  Inclui: vazamento ou mistura de dados entre tenants/usuários, falhas de segurança exploráveis, perda permanente de dados, arquivos/dados que deveriam ser excluídos e permanecem no banco/servidor, valores monetários incorretos, cobranças erradas, ações importantes que parecem funcionar mas não persistem, dados que somem do sistema, corrupção de dados ou qualquer falha que possa gerar prejuízo financeiro, jurídico ou de segurança.

- 🟠 **Alto — Nota 7-8**
  Bugs que quebram funcionalidades importantes em cenários comuns, mas sem causar vazamento grave, perda permanente de dados ou risco crítico imediato.  
  Inclui: botões ou fluxos principais que não funcionam, usuário impedido de concluir uma ação importante, dados exibidos de forma errada mas recuperável, permissões incorretas sem vazamento crítico, falhas frequentes em produção, erros que exigem intervenção manual, duplicação de registros, race conditions ativas com impacto real, ou bugs que afetam muitos usuários.

- 🟡 **Médio — Nota 5-6**
  Bugs que causam inconsistência, confusão ou falha parcial, mas possuem contorno simples e não impedem o uso principal do sistema.  
  Inclui: edge cases reproduzíveis, validações incompletas, mensagens de erro ruins, filtros/paginação/ordenação com falhas pontuais, dados temporariamente inconsistentes, problemas visuais que atrapalham um pouco, falhas que ocorrem apenas em combinações específicas de ações, ou comportamentos errados que não causam perda de dados, falha de segurança ou bloqueio do usuário.

- 🟢 **Baixo — Nota 0-4**
  Bugs pequenos, cosméticos ou de baixa prioridade, sem impacto relevante no usuário final, na segurança, nos dados ou no funcionamento principal do sistema.  
  Inclui: textos errados, desalinhamentos visuais leves, ícones incorretos, pequenos problemas de espaçamento, logs desnecessários, mensagens pouco claras mas não bloqueantes, inconsistências visuais raras ou melhorias que não afetam o uso real.

Regra geral:
A nota deve considerar o pior impacto realista do bug, não apenas o erro visível na tela.

Se envolver segurança, dinheiro, perda de dados, mistura de dados entre usuários/tenants ou falha de exclusão/persistência de dados sensíveis, a severidade deve subir automaticamente para Alto ou Crítico.

Se o bug tiver contorno simples, afetar poucos usuários e não envolver dados sensíveis, segurança ou dinheiro, a severidade pode ser reduzida.

---

## Bugs em catalogação:

### Pendente de correção:

---

### Concluído:


---

