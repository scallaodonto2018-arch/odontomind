#!/bin/bash
# Inicia FastAPI (webhooks) em background na porta 8000
uvicorn backend:app --host 0.0.0.0 --port 8000 &

# Inicia Streamlit (frontend) em foreground na porta 8501
exec streamlit run app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true
