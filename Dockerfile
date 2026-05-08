FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Cache-Buster: Wert ändern erzwingt Rebuild ab hier
ARG CACHE_BUST=2
RUN echo "Build: $CACHE_BUST"

COPY *.py ./
COPY templates/ ./templates/
COPY static/ ./static/

RUN mkdir -p /app/data /app/reports

EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

CMD ["python", "run.py", "daemon"]
