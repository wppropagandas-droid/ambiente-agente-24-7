# Especificação Técnica do Projeto (SPEC.md)

## 1. Visão Geral
Este repositório hospeda o ambiente de desenvolvimento autônomo do projeto. O objetivo é permitir que agentes de IA e desenvolvedores operem de forma contínua, segura e coordenada, acessível tanto localmente quanto via nuvem (GitHub Codespaces / Web).

## 2. Arquitetura do Ambiente
- **Ambiente de Execução Remoto**: GitHub Codespaces (Linux Ubuntu LTS).
- **Interface Visual**: VS Code Web (acessível pelo navegador no PC e no smartphone).
- **Gerenciamento de Sessão**: `tmux` para persistência de processos e terminais em segundo plano (`sessão: agente-24-7`).
- **Linguagens e Runtimes**:
  - Python 3 + `pip` + `venv`
  - Node.js LTS + `npm`
  - Git para controle de versão e rastreabilidade

## 3. Diretrizes de Segurança e Isolamento
- Todo trabalho deve ser executado em branches de desenvolvimento (`dev/agente`).
- A branch `main` é protegida e serve como fonte da verdade estável.
- Comunicação e registro de tarefas gerenciados estritamente pelo arquivo `TICKETS.md`.
