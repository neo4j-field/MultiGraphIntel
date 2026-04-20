FROM python:3.11-slim

ENV PYTHONUNBUFFERED=True

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/console_app/backend/
RUN touch /app/console_app/__init__.py

CMD ["uvicorn", "console_app.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
