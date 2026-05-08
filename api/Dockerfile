FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv && \
    uv pip install --system -e ".[api]"

COPY api/ ./api/
COPY orchestrator/ ./orchestrator/
COPY scanner/ ./scanner/

EXPOSE 8000
CMD ["python", "-m", "api"]
