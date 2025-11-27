#!/bin/bash

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}LLM Server Docker Setup${NC}"
echo -e "${GREEN}========================================${NC}"

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running. Please start Docker Desktop.${NC}"
    exit 1
fi

# Check if NVIDIA Docker runtime is available (for GPU support)
if docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi > /dev/null 2>&1; then
    echo -e "${GREEN}✓ NVIDIA GPU support detected${NC}"
    GPU_FLAG="--gpus all"
else
    echo -e "${YELLOW}⚠ No GPU support detected. Running in CPU mode.${NC}"
    GPU_FLAG=""
fi

# Set image and container names
IMAGE_NAME="llm-server"
CONTAINER_NAME="llm-server-container"

# Check if container already exists
if [ "$(docker ps -aq -f name=${CONTAINER_NAME})" ]; then
    echo -e "${YELLOW}Stopping and removing existing container...${NC}"
    docker stop ${CONTAINER_NAME} 2>/dev/null
    docker rm ${CONTAINER_NAME} 2>/dev/null
fi

# Build Docker image
echo -e "${GREEN}Building Docker image...${NC}"
docker build -t ${IMAGE_NAME} .

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Docker build failed${NC}"
    exit 1
fi

# Get the absolute path to the models directory
MODELS_PATH="$(pwd)/models"

# Check if models directory exists
if [ ! -d "${MODELS_PATH}" ]; then
    echo -e "${YELLOW}Warning: models directory not found at ${MODELS_PATH}${NC}"
    echo -e "${YELLOW}Creating models directory...${NC}"
    mkdir -p "${MODELS_PATH}"
    echo -e "${YELLOW}Please place your model files in: ${MODELS_PATH}/Qwen3-VL-8B-Instruct${NC}"
fi

# Run Docker container
echo -e "${GREEN}Starting container...${NC}"
docker run -d \
    ${GPU_FLAG} \
    --name ${CONTAINER_NAME} \
    -p 5000:5000 \
    -v "${MODELS_PATH}:/app/models" \
    --restart unless-stopped \
    ${IMAGE_NAME}

if [ $? -ne 0 ]; then
    echo -e "${RED}Error: Failed to start container${NC}"
    exit 1
fi

# Wait for container to start
echo -e "${GREEN}Waiting for server to initialize...${NC}"
sleep 5

# Show logs
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Container started successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${GREEN}Viewing logs (Ctrl+C to exit log view):${NC}"
echo ""

# Follow logs
docker logs -f ${CONTAINER_NAME}