FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# C5: incluir alembic/ para que alembic upgrade head pueda correr en
# el entrypoint (necesario para que las migraciones nuevas se apliquen
# en produccion cuando el engine async ya esta inicializado).
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

