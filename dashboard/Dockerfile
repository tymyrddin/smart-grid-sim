FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard/ ./dashboard/
COPY config/    ./config/

ENV PYTHONUNBUFFERED=1

EXPOSE 8050

CMD ["python", "-m", "dashboard.app"]
