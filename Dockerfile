FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DOCKER_CONTAINER=true \
    DATA_DIR=/data

WORKDIR /app

# ca-certificates: TLS pro portal/Sheets/LLM. apt-get em si é usado pelo
# "browser-use install" abaixo (--with-deps resolve as libs do Chromium).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# browser-use não depende de playwright diretamente; "browser-use install"
# roda `uvx playwright install chromium --with-deps` por baixo (uv já é
# dependência do projeto). Ver app/agent/runner.py (browser_use.Browser).
RUN browser-use install

COPY app ./app
COPY calcular_metricas.py .

# /data é o volume persistente (downloads/, reports/, metricas/, histórico) —
# em Fargate, montar via EFS (ver docs/Deploy_AWS_Metricas_Custo_RPA_vs_APA.docx).
RUN mkdir -p /data

# Container "one-shot": processa o lote e encerra (sem restart automático —
# ver docker-compose.yml e a seção 1 do documento de deploy).
CMD ["python", "-m", "app.main"]
