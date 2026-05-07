#!/bin/bash
set -e

# Gera nginx.conf com a porta real do Railway ($PORT)
envsubst '${PORT}' < /app/nginx.conf.template > /etc/nginx/conf.d/default.conf

# FastAPI (webhooks + API)
uvicorn backend:app --host 127.0.0.1 --port 8000 &

# Streamlit (frontend)
streamlit run app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true &

# Aguarda os dois processos subirem
sleep 3

# nginx em foreground (processo principal)
exec nginx -g "daemon off;"
