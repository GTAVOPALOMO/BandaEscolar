FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN SECRET_KEY=build-only ALLOWED_HOSTS=localhost \
    DATABASE_URL=postgresql://build:build@localhost:5432/build \
    SUPABASE_S3_ENDPOINT_URL=https://build.invalid/storage/v1/s3 \
    SUPABASE_S3_ACCESS_KEY_ID=build SUPABASE_S3_SECRET_ACCESS_KEY=build \
    SUPABASE_S3_REGION_NAME=us-east-1 \
    python manage.py collectstatic --noinput \
    && mkdir -p /data && chmod +x /app/start.sh && chown -R app:app /app /data
EXPOSE 8000
CMD ["/app/start.sh"]
