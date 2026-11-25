#!/usr/bin/env bash
# Script para entrar ou criar a sessão persistente do agente no tmux
SESSION_NAME="agente-24-7"

echo "======================================================"
echo " Conectando à sessão persistente: $SESSION_NAME"
echo " Para desanexar da sessão sem fechar o processo: Ctrl+B depois D"
echo "======================================================"

tmux attach-session -t "$SESSION_NAME" 2>/dev/null || tmux new-session -s "$SESSION_NAME"
