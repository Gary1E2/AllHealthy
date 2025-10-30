from huggingface_hub import snapshot_download

# Correct model name on Hugging Face
repo_id = "Qwen/Qwen2-VL-2B-Instruct"

# Directory where the model will be stored locally
local_dir = r"C:\Users\cryp1\AllHealthy\models\Qwen2-VL-2B-Instruct"

# Download all model files
snapshot_download(
    repo_id=repo_id,
    local_dir=local_dir,
    local_dir_use_symlinks=False
)

print(" Model downloaded to:", local_dir)
