FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

# Streamlit (frontend) na 8501 + FastAPI (webhooks) na 8000
CMD ["./start.sh"]
