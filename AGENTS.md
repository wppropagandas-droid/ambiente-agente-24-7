# Regras Obrigatórias para Agentes Autônomos (AGENTS.md)

> [!IMPORTANT]
> Estas regras são invioláveis por qualquer agente de IA que opere neste repositório.

## 1. Política de Branches
1. **NUNCA modifique ou comite diretamente na branch `main`**.
2. Todo o trabalho deve ser realizado na branch `dev/agente` (ou em branches de feature específicas `feature/<nome-da-tarefa>`).
3. Para iniciar qualquer tarefa:
   ```bash
   git checkout -b dev/agente || git checkout dev/agente
   git pull origin dev/agente || true
   ```

## 2. Ciclo de Vida da Tarefa
Para cada tarefa em `TICKETS.md`:
1. **Assumir a tarefa**: Marque o ticket de `[ ]` para `[-]` no `TICKETS.md`.
2. **Implementar**: Escreva código modular, limpo e documentado.
3. **Testar**: Execute testes manuais ou automatizados para validar que nada quebrou.
4. **Comitar**: Faça commits semânticos e objetivos, citando o ID do ticket (ex: `feat: conclui TICKET-003`).
5. **Concluir**: Marque o ticket como `[x]` no `TICKETS.md` e adicione uma linha no log de conclusões com a data e o resumo do que foi feito.

## 3. Ambiente e Persistência
- Sempre mantenha os processos de longa duração rodando dentro da sessão `tmux` (`agente-24-7`).
- Nunca execute comandos destrutivos sem aprovação do usuário (`rm -rf /`, `git push --force`, etc.).
- Não exponha senhas, chaves de API ou dados sensíveis em arquivos commitados.
