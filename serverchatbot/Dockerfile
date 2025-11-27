# Use NVIDIA CUDA base image with Ubuntu 22.04
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    wget \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Upgrade pip
RUN pip3 install --no-cache-dir --upgrade pip

# Install PyTorch with CUDA 12.1 support
RUN pip3 install --no-cache-dir \
    torch==2.5.1 \
    torchvision==0.20.1 \
    torchaudio==2.5.1 \
    --index-url https://download.pytorch.org/whl/cu121

# Install transformers from GitHub (required for Qwen3-VL)
RUN pip3 install --no-cache-dir git+https://github.com/huggingface/transformers
RUN pip3 install --no-cache-dir git+https://github.com/huggingface/accelerate

# Copy requirements file
COPY requirements.txt .

# Install remaining dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
# Copy application files
COPY serverchatbot.py .
COPY model_download.py .
COPY entrypoint.sh .

# Make entrypoint executable
RUN chmod +x entrypoint.sh


# Create directory for models (will be mounted as volume)
RUN mkdir -p /app/models

# Expose Flask port
EXPOSE 5000

# Run the application
ENTRYPOINT ["./entrypoint.sh"]