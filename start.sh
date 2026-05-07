#!/bin/bash

NGINX_PORT=${PORT:-8080}
echo "Iniciando OdontoMind — porta pública: $NGINX_PORT"

# Gera nginx.conf com a porta real
sed "s/NGINX_PORT/$NGINX_PORT/g" /app/nginx.conf.template \
    > /etc/nginx/conf.d/odontomind.conf

# FastAPI (webhooks + API)
uvicorn backend:app --host 127.0.0.1 --port 8000 &

# Streamlit (frontend)
streamlit run app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true &

# nginx inicia imediatamente — responde na porta pública enquanto
# FastAPI e Streamlit sobem em background (retorna 502 temporariamente)
exec nginx -g "daemon off;"
