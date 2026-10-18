FROM python:3.12-slim

RUN useradd --create-home --uid 1000 app \
    && mkdir /dados \
    && chown app:app /dados

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simulador.py .

USER app
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "simulador.py", "--saida", "/dados"]