FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Команда переопределяется в docker-compose (web / bot / migrate)
CMD ["uvicorn", "app.web.main:app", "--host", "0.0.0.0", "--port", "8000"]
