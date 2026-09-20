FROM python:3.12.12-slim-bookworm

RUN groupadd --gid 10001 mlflow \
    && useradd --uid 10001 --gid mlflow --create-home mlflow \
    && pip install --no-cache-dir \
        "boto3>=1.42,<2" \
        "mlflow==3.16.1" \
        "prometheus-flask-exporter>=0.23,<1" \
        "psycopg[binary]>=3.3,<4"

USER 10001:10001
EXPOSE 5000
