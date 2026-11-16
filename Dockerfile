FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home sentinel \
    && mkdir /secrets && chown sentinel:sentinel /secrets && chmod 700 /secrets
COPY alembic.ini ./
COPY migrations ./migrations
USER sentinel
EXPOSE 8000
CMD ["uvicorn", "api_sentinel.app:create_app", "--factory", "--host", "0.0.0.0", "--no-access-log"]
