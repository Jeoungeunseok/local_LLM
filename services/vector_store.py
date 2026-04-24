from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from config import QDRANT_HOST, QDRANT_PORT, EMBEDDING_MODEL_NAME

# Initialize Embedding model
embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)

# Initialize Qdrant Client
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
