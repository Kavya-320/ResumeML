from fastembed import TextEmbedding

from .app import config

if __name__ == "__main__":
    TextEmbedding(model_name=config.MODEL_NAME, cache_dir=config.MODEL_CACHE_DIR)
    print("Model downloaded and ready.")