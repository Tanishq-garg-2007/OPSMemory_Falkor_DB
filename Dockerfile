FROM python:3.11-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000

# Uses Render's dynamic $PORT or defaults to 8000
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
