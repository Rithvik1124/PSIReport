FROM python:3.11-slim

# Install Chrome & dependencies
RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    wget unzip fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="${PATH}:/usr/bin"

# Set workdir and copy files
WORKDIR /app
COPY . .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

# Start API with Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
