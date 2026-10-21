FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN SECRET_KEY=build-only ALLOWED_HOSTS=localhost DATA_DIR=/tmp/build-data python manage.py collectstatic --noinput && mkdir -p /data && chmod +x /app/start.sh && chown -R app:app /app /data
EXPOSE 8000
CMD ["/app/start.sh"]
