#!/bin/bash

# Streamlit roda internamente na 8501
streamlit run app.py \
    --server.port 8501 \
    --server.address 127.0.0.1 \
    --server.headless true &

# FastAPI roda na porta pública ($PORT do Railway)
# Recebe webhooks diretamente e proxia o Streamlit
exec uvicorn backend:app --host 0.0.0.0 --port "${PORT:-8080}"
