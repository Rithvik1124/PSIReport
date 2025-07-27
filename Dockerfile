# Base Python (you asked for Lighthouse CLI, so we also add Node + Chromium here)
FROM python:3.11-slim

# Install system deps: node, chromium, fonts
RUN apt-get update && apt-get install -y \
    nodejs npm chromium chromium-common chromium-driver fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Lighthouse CLI
RUN npm install -g lighthouse@11

# Workdir
WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Add code
COPY run.py .

# Default command example (override with docker run args)
# You WILL override --url at runtime.
CMD ["python", "run.py", "--url", "https://example.com", "--strategy", "mobile"]
