# Build from the repo root: docker build -f inference/Dockerfile .
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/inference \
    INFERENCE_NEWS2_CONFIG=/app/inference/config/news2.yaml     INFERENCE_ASSIGNMENT_CONFIG=/app/inference/config/assignment.yaml

COPY inference/requirements.txt inference/requirements.txt
RUN pip install --no-cache-dir -r inference/requirements.txt

COPY inference/config inference/config
COPY inference/borj_inference inference/borj_inference

EXPOSE 8001
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')"
CMD ["uvicorn", "borj_inference.main:app", "--host", "0.0.0.0", "--port", "8001"]
