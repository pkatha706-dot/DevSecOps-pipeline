# Stage 1: build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

COPY app/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime image
FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ .

RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000

ENV FLASK_APP=app.py
ENV FLASK_RUN_HOST=0.0.0.0

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:5000/health').status == 200 else 1)"

CMD ["python", "app.py"]
