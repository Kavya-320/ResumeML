from sentence_transformers import SentenceTransformer

from . import config

if __name__ == "__main__":
    SentenceTransformer(config.MODEL_NAME, cache_folder=config.MODEL_CACHE_DIR)
    print("Model downloaded and ready.")
