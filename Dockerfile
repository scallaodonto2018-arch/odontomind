FROM python:3.11-slim

# nginx + envsubst (gettext-base)
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx gettext-base \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x start.sh

# nginx na $PORT (Railway injeta), FastAPI na 8000, Streamlit na 8501
CMD ["./start.sh"]
