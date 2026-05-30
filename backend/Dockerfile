# NextWatch backend — runtime image (sample bundle works with zero data setup).
FROM python:3.11-slim

WORKDIR /app

# Install runtime deps only (the heavy training stack is not needed to serve).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# AUTO_SAMPLE lets startup generate the sample artifacts if none are baked in.
ENV AUTO_SAMPLE=true \
    MODEL_ARTIFACTS_PATH=./data/artifacts \
    DATABASE_URL=sqlite:///./nextwatch.db

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
