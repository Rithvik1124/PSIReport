FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    nodejs npm \
    chromium chromium-common chromium-driver \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install Lighthouse globally
RUN npm install -g lighthouse@11

# Set work directory
WORKDIR /app

# Copy files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set environment variable for Streamlit to listen correctly on Railway
ENV STREAMLIT_SERVER_PORT=8000
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

EXPOSE 8000

# Start the Streamlit app
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8000", "--server.address=0.0.0.0"]
