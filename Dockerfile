FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

# FastAPI na $PORT (webhooks + proxy Streamlit) | Streamlit na 8501 (interno)
CMD ["./start.sh"]
