FROM python:3.12-slim

ARG SERVICE_NAME
ARG SERVICE_PORT

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    SERVICE_PORT=${SERVICE_PORT}

WORKDIR /service

COPY shared/ /shared/
RUN pip install /shared/

COPY services/${SERVICE_NAME}/requirements.txt .
RUN pip install -r requirements.txt

COPY services/${SERVICE_NAME}/ .

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /service
USER app

EXPOSE ${SERVICE_PORT}
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${SERVICE_PORT}"]
