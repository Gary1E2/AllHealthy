# LLM Server Docker Setup

This Docker container packages your Qwen3-VL-8B nutrition analysis server for easy deployment.

## Prerequisites

1. **Docker Desktop** - Already installed ✓
2. **WSL 2 with Ubuntu** - Already installed ✓
3. **NVIDIA GPU (optional)** - For faster inference
4. **NVIDIA Container Toolkit** (if using GPU):
   ```bash
   # Install NVIDIA Container Toolkit (Updated method)
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```

## Project Structure

```
your-project/
├── chatbot.py           # Your LLM server code
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker image definition
├── .dockerignore       # Files to exclude from build
├── run.sh             # Start script
├── stop.sh            # Stop script
└── models/            # Model files directory
    └── Qwen3-VL-8B-Instruct/
        └── (model files here)
```

## Setup Instructions

### 1. Prepare Your Files

Ensure you have these files in your project directory:
- `chatbot.py` (your Python script)
- `requirements.txt` (cleaned version without comments)
- `Dockerfile`
- `.dockerignore`
- `run.sh`
- `stop.sh`

### 2. Download the Model

Place your Qwen3-VL-8B-Instruct model in:
```
models/Qwen3-VL-8B-Instruct/
```

The directory structure should look like:
```
models/
└── Qwen3-VL-8B-Instruct/
    ├── config.json
    ├── model.safetensors
    ├── tokenizer.json
    └── (other model files)
```

### 3. Make Scripts Executable

```bash
chmod +x run.sh stop.sh
```

### 4. Run the Container

```bash
bash run.sh
```

This will:
- Build the Docker image (first time only, ~5-10 minutes)
- Start the container with GPU support (if available)
- Mount your models directory
- Show live logs from the server

**Important**: When you see the ngrok public URL in the logs, copy it and update your client application!

## Usage

### Start the Server
```bash
bash run.sh
```

### View Logs
```bash
docker logs -f llm-server-container
```

### Stop the Server
```bash
bash stop.sh
```

### Restart the Server
```bash
bash stop.sh
bash run.sh
```

### Access the Container Shell
```bash
docker exec -it llm-server-container bash
```

## Troubleshooting

### GPU Not Detected
If you have an NVIDIA GPU but it's not being detected:
1. Install NVIDIA Container Toolkit (see Prerequisites)
2. Restart Docker Desktop
3. Test with: `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi`

### Container Exits Immediately
Check logs for errors:
```bash
docker logs llm-server-container
```

Common issues:
- Model files not found in `models/Qwen3-VL-8B-Instruct/`
- Insufficient memory (model requires ~8GB+ RAM)
- Port 5000 already in use

### Port Already in Use
If port 5000 is occupied, modify `run.sh`:
```bash
-p 5001:5000 \  # Use external port 5001 instead
```

### Rebuild After Code Changes
```bash
docker build -t llm-server .
bash stop.sh
bash run.sh
```

## Container Management

### Remove Container and Image
```bash
docker stop llm-server-container
docker rm llm-server-container
docker rmi llm-server
```

### Check Container Status
```bash
docker ps -a | grep llm-server
```

### Monitor Resource Usage
```bash
docker stats llm-server-container
```

## Notes

- The container automatically restarts unless manually stopped
- Model files are mounted as a volume (not copied into the image)
- First build takes 5-10 minutes due to PyTorch and dependencies
- Subsequent builds are faster (cached layers)
- The container runs on port 5000 internally and externally

## API Endpoints

Once running, the server exposes:

- `GET /health` - Health check
- `POST /estimate_nutrition` - Analyze food images
- `POST /describe_food` - Generate food descriptions
- `POST /dynamic_tips` - Get personalized nutrition tips
- `POST /chat` - Chat with the nutrition assistant

Access via the ngrok URL shown in the logs!