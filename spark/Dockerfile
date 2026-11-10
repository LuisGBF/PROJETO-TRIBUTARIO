FROM python:3.12-slim

# O Spark roda na JVM, então precisamos do Java
RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

ENV PYTHONUNBUFFERED=1