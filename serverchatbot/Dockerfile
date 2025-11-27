FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system packages (for torch + scientific libs)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    ffmpeg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements first (caching optimization)
COPY app/requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy full application
COPY app/ /app/

# Expose port (API)
EXPOSE 8000

# Default command
CMD ["python", "serverchatbot.py"]
