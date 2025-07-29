FROM python:3.9

RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/data /app/logs

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY db.py .
COPY config.py .
COPY config.json .

RUN touch /app/logs/bot.log

CMD ["python", "main.py"]