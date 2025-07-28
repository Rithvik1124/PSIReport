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

# Copy project files
COPY . .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Ensure startup.sh is executable
RUN chmod +x startup.sh

# Use Railway's port env variable for Streamlit
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# Expose the port (Railway uses $PORT)
EXPOSE 8000

# Start everything via startup script
CMD ["bash", "startup.sh"]
