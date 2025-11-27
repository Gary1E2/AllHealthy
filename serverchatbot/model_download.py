from huggingface_hub import snapshot_download

model_id = "Qwen/Qwen3-VL-8B-Instruct-GGUF"

# Download to a custom directory
snapshot_download(
    repo_id=model_id,
    local_dir=r"C:\models\Qwen3-VL-8B-Instruct-GGUF",
    local_dir_use_symlinks=False,
)
