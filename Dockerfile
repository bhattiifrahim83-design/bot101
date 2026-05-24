FROM python:3.11-slim

ENV PYTHONIOENCODING=utf-8 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY ["python bot_real.py", "./bot.py"]

CMD ["python", "bot.py"]
