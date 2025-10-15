# syntax directive removed for compatibility with older Docker engines
FROM python:3.12-slim AS base

ARG DEBIAN_FRONTEND=noninteractive

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone

COPY requirements.txt ./

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY backend backend
COPY README.md README.md
COPY docker/entrypoint.py /entrypoint.py

RUN addgroup --system app \
    && adduser --system --ingroup app app \
    && chown -R app:app /app

EXPOSE 8000

ENTRYPOINT ["python", "/entrypoint.py"]
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000"]
