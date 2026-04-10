"""
FAISS-based Vector Search Engine

Purpose:
    Provides efficient vector similarity search using FAISS library.
    Replaces naive linear scan with indexed search for O(log n) complexity.
    
Responsibilities:
    - Manage FAISS index lifecycle (create, train, add, search)
    - Support multiple index types (Flat, IVF, HNSW)
    - Persist index and metadata to disk
    - Handle index updates and deletions
    
Not Responsible For:
    - Embedding generation (delegated to LLM providers)
    - Keyword search (handled by separate engine)
    - Result fusion (handled by HybridRetrievalEngine)
"""

import logging
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Lazy import FAISS
faiss = None
try:
    import faiss as _faiss
    faiss = _faiss
except ImportError:
    logger.warning("faiss-cpu not installed. FAISSVectorIndex will not be available.")


class FAISSVectorIndex:
    """
    Efficient vector index based on FAISS.
    
    Features:
        - Support million-scale vectors
        - Millisecond-level retrieval
        - Multiple index types (Flat, IVF, HNSW)
        - Persistence support
        
    Index Types:
        - flat: Exact search, best accuracy, slower for large datasets
        - ivf: Inverted File Index, good balance of speed/accuracy
        - hnsw: Hierarchical Navigable Small World, fastest for large datasets
    
    Usage:
        >>> index = FAISSVectorIndex(dimension=768, index_type="hnsw")
        >>> index.add_batch(vectors, ids)
        >>> results = index.search(query_vector, k=10)
    """
    
    def __init__(
        self,
        dimension: int = 768,
        index_type: str = "hnsw",  # flat, ivf, hnsw
        nlist: int = 100,  # For IVF: number of clusters
        m: int = 16,  # For HNSW: number of connections per layer
    ):
        if faiss is None:
            raise ImportError(
                "faiss-cpu is required. Install with: pip install faiss-cpu"
            )
        
        self.dimension = dimension
        self.index_type = index_type.lower()
        self.nlist = nlist
        self.m = m
        
        # Metadata storage (maps internal ID to external metadata)
        self.metadata: List[dict] = []
        
        # Create FAISS index
        self.index = self._create_index(index_type, nlist, m)
        
        logger.info(
            f"FAISSVectorIndex initialized: "
            f"dimension={dimension}, type={index_type}, "
            f"nlist={nlist}, m={m}"
        )
    
    def _create_index(self, index_type: str, nlist: int, m: int):
        """Create FAISS index based on type."""
        if index_type == "flat":
            # Exact search - no approximation
            return faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))
        
        elif index_type == "ivf":
            # Inverted File Index - good for medium-large datasets
            quantizer = faiss.IndexFlatL2(self.dimension)
            index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist)
            # Note: IVF needs training before use
            return index
        
        elif index_type == "hnsw":
            # HNSW - fastest for large datasets
            index = faiss.IndexHNSWFlat(self.dimension, m)
            index.hnsw.efConstruction = 40  # Higher = better quality, slower build
            index.hnsw.efSearch = 16  # Higher = better recall, slower search
            return faiss.IndexIDMap(index)
        
        else:
            raise ValueError(f"Unknown index type: {index_type}. Use 'flat', 'ivf', or 'hnsw'")
    
    def add(
        self,
        vector: np.ndarray,
        metadata: dict,
        vector_id: Optional[int] = None,
    ) -> int:
        """
        Add single vector to index.
        
        Args:
            vector: Vector array (dimension,)
            metadata: Metadata dictionary to associate with vector
            vector_id: Optional explicit ID (auto-generated if None)
        
        Returns:
            Assigned vector ID
        """
        if len(vector.shape) == 1:
            vector = vector.reshape(1, -1)
        
        vector = np.asarray(vector, dtype='float32')
        
        # Generate ID if not provided
        if vector_id is None:
            vector_id = len(self.metadata)
        
        # Train IVF index if needed
        if self.index_type == "ivf" and not self.index.is_trained:
            logger.info("Training IVF index...")
            # Need at least nlist * 39 vectors for training
            if len(self.metadata) < self.nlist * 39:
                logger.warning(
                    f"Not enough vectors for IVF training. "
                    f"Need {self.nlist * 39}, have {len(self.metadata)}"
                )
                # Fallback: add without training (will use brute force)
            else:
                # Collect some vectors for training
                training_vectors = np.array([
                    item['vector'] for item in self.metadata[-1000:]
                ])
                self.index.train(training_vectors)
                logger.info("IVF index trained")
        
        # Add to index
        self.index.add_with_ids(vector, np.array([vector_id], dtype='int64'))
        
        # Store metadata
        if vector_id >= len(self.metadata):
            # Extend list if needed
            self.metadata.extend([{}] * (vector_id - len(self.metadata) + 1))
        self.metadata[vector_id] = metadata
        
        logger.debug(f"Added vector {vector_id} to index")
        return vector_id
    
    def add_batch(
        self,
        vectors: np.ndarray,
        metadatas: List[dict],
        start_id: Optional[int] = None,
    ) -> List[int]:
        """
        Add batch of vectors to index.
        
        Args:
            vectors: Array of shape (n, dimension)
            metadatas: List of metadata dicts
            start_id: Starting ID for auto-generation
        
        Returns:
            List of assigned vector IDs
        """
        if len(vectors) != len(metadatas):
            raise ValueError(
                f"vectors ({len(vectors)}) and metadatas ({len(metadatas)}) "
                f"must have same length"
            )
        
        if len(vectors) == 0:
            return []
        
        vectors = np.asarray(vectors, dtype='float32')
        if len(vectors.shape) == 1:
            vectors = vectors.reshape(1, -1)
        
        # Generate IDs
        if start_id is None:
            start_id = len(self.metadata)
        
        vector_ids = list(range(start_id, start_id + len(vectors)))
        
        # Train IVF if needed
        if self.index_type == "ivf" and not self.index.is_trained:
            if len(vectors) >= self.nlist * 39:
                logger.info(f"Training IVF index with {len(vectors)} vectors...")
                self.index.train(vectors)
            else:
                logger.warning("Not enough vectors for IVF training")
        
        # Add to index
        self.index.add_with_ids(vectors, np.array(vector_ids, dtype='int64'))
        
        # Store metadata
        if start_id >= len(self.metadata):
            self.metadata.extend([{}] * (start_id - len(self.metadata)))
        
        for i, (vid, meta) in enumerate(zip(vector_ids, metadatas)):
            if vid >= len(self.metadata):
                self.metadata.extend([{}] * (vid - len(self.metadata) + 1))
            self.metadata[vid] = meta
        
        logger.info(f"Added batch of {len(vectors)} vectors (IDs {start_id}-{vector_ids[-1]})")
        return vector_ids
    
    def search(
        self,
        query_vector: np.ndarray,
        k: int = 10,
    ) -> List[Tuple[float, dict]]:
        """
        Search for k most similar vectors.
        
        Args:
            query_vector: Query vector (dimension,)
            k: Number of results to return
        
        Returns:
            List of (distance, metadata) tuples, sorted by distance (ascending)
        """
        if self.index.ntotal == 0:
            logger.warning("Index is empty")
            return []
        
        try:
            query_vector = np.asarray(query_vector, dtype='float32').reshape(1, -1)
            
            # Ensure k doesn't exceed total vectors
            k = min(k, self.index.ntotal)
            
            # Search
            distances, indices = self.index.search(query_vector, k)
            
            # Convert to results
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx != -1 and idx < len(self.metadata):
                    results.append((float(dist), self.metadata[idx]))
            
            logger.debug(f"Search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"FAISS search failed: {e}. Returning empty results.")
            return []
    
    def remove(self, vector_id: int) -> bool:
        """
        Remove vector from index.
        
        Note: FAISS doesn't support efficient removal. This marks as deleted.
        
        Args:
            vector_id: ID of vector to remove
        
        Returns:
            True if removed, False if not found
        """
        if vector_id >= len(self.metadata):
            return False
        
        # Mark as deleted (set metadata to None)
        if self.metadata[vector_id] is not None:
            self.metadata[vector_id] = None
            logger.debug(f"Marked vector {vector_id} as deleted")
            return True
        
        return False
    
    def reset(self):
        """Reset index to empty state."""
        self.index.reset()
        self.metadata.clear()
        logger.info("Index reset")
    
    def save(self, path: Path):
        """
        Save index and metadata to disk.
        
        Args:
            path: Directory to save files
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        # Save FAISS index
        index_path = path / f"faiss_index_{self.index_type}.bin"
        faiss.write_index(self.index, str(index_path))
        
        # Save metadata
        import pickle
        metadata_path = path / "metadata.pkl"
        with open(metadata_path, 'wb') as f:
            pickle.dump({
                'metadata': self.metadata,
                'dimension': self.dimension,
                'index_type': self.index_type,
                'nlist': self.nlist,
                'm': self.m,
            }, f)
        
        logger.info(f"Index saved to {path}")
    
    @classmethod
    def load(cls, path: Path) -> 'FAISSVectorIndex':
        """
        Load index from disk.
        
        Args:
            path: Directory containing saved files
        
        Returns:
            Loaded FAISSVectorIndex instance
        """
        path = Path(path)
        
        # Load metadata
        import pickle
        metadata_path = path / "metadata.pkl"
        with open(metadata_path, 'rb') as f:
            data = pickle.load(f)
        
        # Create instance
        instance = cls(
            dimension=data['dimension'],
            index_type=data['index_type'],
            nlist=data.get('nlist', 100),
            m=data.get('m', 16),
        )
        
        # Load FAISS index
        index_path = path / f"faiss_index_{data['index_type']}.bin"
        instance.index = faiss.read_index(str(index_path))
        
        # Restore metadata
        instance.metadata = data['metadata']
        
        logger.info(f"Index loaded from {path} with {instance.index.ntotal} vectors")
        return instance
    
    @property
    def size(self) -> int:
        """Get number of vectors in index."""
        return self.index.ntotal
    
    def get_stats(self) -> dict:
        """Get index statistics."""
        return {
            'size': self.index.ntotal,
            'dimension': self.dimension,
            'index_type': self.index_type,
            'memory_metadata_mb': len(self.metadata) * 0.001,  # Rough estimate
        }
