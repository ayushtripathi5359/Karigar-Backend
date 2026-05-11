FROM python:3.12-slim
WORKDIR /service

COPY shared/ /shared/
RUN pip install --no-cache-dir /shared/

COPY services/payments/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/payments/ .

EXPOSE 8006
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
