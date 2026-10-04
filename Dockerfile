FROM python:3.10

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --system --create-home app \
    && mkdir -p /app/media /app/static \
    && chown -R app:app /app/media /app/static

USER app

EXPOSE 8000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["sh", "-c", "python manage.py collectstatic --noinput && exec gunicorn datahub_gui.wsgi:application --bind 0.0.0.0:8000 --workers 3"]
