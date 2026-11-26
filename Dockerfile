FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --break-system-packages

COPY src/ ./src/
COPY data/ ./data/

# Les modules de src/ s'importent entre eux par leur nom (import config,
# import assistant...) : src/ doit etre dans le chemin, comme pour
# "PYTHONPATH=src uvicorn src.api:app" en local.
ENV PYTHONPATH=/app/src

CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]