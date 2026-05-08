#!/bin/bash

# FastAPI (webhooks) — porta 8000 — background
uvicorn backend:app --host 0.0.0.0 --port 8000 &

# Streamlit (UI) — porta $PORT (domínio principal Railway) — foreground
exec streamlit run app.py \
    --server.port "${PORT:-8501}" \
    --server.address 0.0.0.0 \
    --server.headless true
