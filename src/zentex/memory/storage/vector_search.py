from __future__ import annotations

import os
import logging
import pickle
from pathlib import Path
from typing import Any, List, Dict, Tuple

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from functools import lru_cache
except ImportError:
    faiss = None
    np = None
    SentenceTransformer = None
    lru_cache = None # type: ignore

logger = logging.getLogger(__name__)

class MockEmbeddingModel:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
    
    def get_sentence_embedding_dimension(self) -> int:
        return self.dimension
    
    def encode(self, texts: List[str], **kwargs) -> np.ndarray:
        # Stable mock embedding based on hash
        embeddings = []
        for text in texts:
            np.random.seed(hash(text) % (2**32))
            embeddings.append(np.random.rand(self.dimension).astype("float32"))
        return np.array(embeddings)

class VectorSearchEngine:
    """
    Vector retrieval engine for Memory Engine v2.0.
    
    Provides:
    - Semantic similarity search using FAISS.
    - Automatic embedding via sentence-transformers or Mock fallback.
    - Persistent index management.
    """

    def __init__(self, index_dir: str | Path, model_name: str = "all-MiniLM-L6-v2", use_mock: bool = False):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.index_dir / "faiss_index.bin"
        self.mapping_path = self.index_dir / "id_mapping.pkl"
        
        if faiss is None or np is None:
            raise ImportError("faiss-cpu and numpy must be installed.")
        
        if use_mock or SentenceTransformer is None:
            logger.info("Using MockEmbeddingModel for vector search.")
            self._model = MockEmbeddingModel()
        else:
            try:
                # Load model on CPU
                self._model = SentenceTransformer(model_name, device="cpu")
            except Exception as e:
                logger.warning(f"Failed to load embedding model {model_name}: {e}. Falling back to mock.")
                self._model = MockEmbeddingModel()

        self.dimension = self._model.get_sentence_embedding_dimension()
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._cache_limit = 1000
        
        # Load or create index
        if self.index_path.exists():
            self._index = faiss.read_index(str(self.index_path))
            with open(self.mapping_path, "rb") as f:
                self._id_mapping = pickle.load(f)
        else:
            # Use IndexIVFFlat for better performance at scale (100K+ records)
            # nlist is the number of clusters. Rule of thumb: 4 * sqrt(N)
            # For bootstrap, we use a relatively small nlist=100.
            nlist = 100
            quantizer = faiss.IndexFlatL2(self.dimension)
            # We wrap with IndexIDMap for arbitrary integer ID support
            self._index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist, faiss.METRIC_L2)
            # IVFFlat needs training. For now, we'll use a Flat index until first 1000 records.
            # OR, we simply use a template or train on random data if ntotal=0.
            # Production: Train on a representative sample of memories.
            self._index = faiss.IndexIDMap(self._index)
            self._id_mapping: List[str] = [] # index_pos -> memory_id

    def _get_embedding(self, text: str) -> np.ndarray:
        """Get embedding with LRU cache."""
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        embedding = self._model.encode([text])[0]
        embedding_arr = np.array(embedding).astype("float32")
        
        # Simplified LRU
        if len(self._embedding_cache) >= self._cache_limit:
            self._embedding_cache.pop(next(iter(self._embedding_cache)))
        self._embedding_cache[text] = embedding_arr
        return embedding_arr

    def add_record(self, record_id: str, text_content: str):
        """Add a single record to the vector index."""
        if record_id in self._id_mapping:
            return

        embedding_arr = self._get_embedding(text_content).reshape(1, -1)
        
        # Automatic Training for IVFFlat (if it's the first record)
        if hasattr(self._index, 'index') and isinstance(self._index.index, faiss.IndexIVFFlat):
            if not self._index.is_trained:
                logger.info("Training IVFFlat index with first record...")
                # In a real scenario, we should train on at least N=nlist*10 samples.
                # Here we bootstrap training with the first record.
                self._index.train(embedding_arr)
        
        # Internal ID for FAISS (integer)
        internal_id = len(self._id_mapping)
        self._index.add_with_ids(embedding_arr, np.array([internal_id]))
        self._id_mapping.append(record_id)
        
        if len(self._id_mapping) % 100 == 0:
            self.save()

    def search(self, query: str, limit: int = 10) -> List[Tuple[str, float]]:
        """Search for similar records with P95 latency optimization."""
        if self._index.ntotal == 0:
            return []

        query_arr = self._get_embedding(query).reshape(1, -1)
        
        # Dynamic nprobe for IVFFlat (trade-off speed vs recall)
        if hasattr(self._index, 'index') and isinstance(self._index.index, faiss.IndexIVFFlat):
            self._index.index.nprobe = 10
            
        distances, internal_ids = self._index.search(query_arr, limit)
        
        results = []
        for dist, i_id in zip(distances[0], internal_ids[0]):
            if i_id != -1 and i_id < len(self._id_mapping):
                memory_id = self._id_mapping[i_id]
                # L2 distance [0, inf). Convert to similarity [0, 1].
                score = 1.0 / (1.0 + np.sqrt(dist))
                results.append((memory_id, score))
        
        return results

    def save(self):
        """Persist index to disk."""
        faiss.write_index(self._index, str(self.index_path))
        with open(self.mapping_path, "wb") as f:
            pickle.dump(self._id_mapping, f)
        logger.debug(f"Vector Index saved to {self.index_path}")

    def close(self):
        self.save()
