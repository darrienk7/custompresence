FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY custompresence ./custompresence
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 app
USER app
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn custompresence.upload_service:create_upload_service --factory --host 0.0.0.0 --port \"${PORT:-8000}\" --no-access-log --limit-concurrency 16"]
