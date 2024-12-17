# File: claudesidian/memory/graph.py

"""
Knowledge graph implementation for Claudesidian memory system.
Handles storage, querying, and maintenance of the memory graph structure.
"""

import networkx as nx
from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime
import asyncio
import logging
from pathlib import Path
import json
from dataclasses import dataclass, asdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

@dataclass
class Node:
    """Represents a node in the knowledge graph."""
    id: str
    type: str  # 'note', 'concept', 'tag'
    content: Optional[str] = None
    metadata: Dict[str, Any] = None
    embedding: Optional[np.ndarray] = None
    created: datetime = None
    modified: datetime = None
    strength: float = 1.0
    hits: int = 0

@dataclass
class Edge:
    """Represents an edge in the knowledge graph."""
    source: str
    target: str
    type: str
    strength: float = 1.0
    metadata: Dict[str, Any] = None
    created: datetime = None
    bidirectional: bool = False

class KnowledgeGraph:
    """
    Implementation of the knowledge graph using NetworkX.
    Provides graph operations, querying, and maintenance.
    """
    
    def __init__(self, embedding_dimension: int = 384):
        """
        Initialize the knowledge graph.
        
        Args:
            embedding_dimension: Dimension for node embeddings
        """
        # Main graph
        self.graph = nx.MultiDiGraph()
        
        # Index structures
        self._content_index = {}  # id -> content mapping
        self._tag_index = {}      # tag -> node_ids mapping
        self._type_index = {}     # type -> node_ids mapping
        
        # Vectorization
        self.vectorizer = TfidfVectorizer(
            max_features=10000,
            stop_words='english'
        )
        self.embedding_dim = embedding_dimension
        
        # Cache
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        
    async def add_node(self, node_id: str, attributes: Dict[str, Any]) -> None:
        """
        Add a node to the graph with attributes.
        
        Args:
            node_id: Unique identifier for the node
            attributes: Dictionary of node attributes
        """
        self.graph.add_node(node_id, **attributes)

    async def add_edge(self, source: str, target: str,
                      edge_type: str, strength: float = 1.0,
                      metadata: Optional[Dict] = None,
                      bidirectional: bool = False) -> Edge:
        """
        Add an edge to the graph.
        
        Args:
            source: Source node ID
            target: Target node ID
            edge_type: Type of edge
            strength: Edge strength
            metadata: Optional metadata
            bidirectional: Whether edge is bidirectional
            
        Returns:
            Created Edge object
        """
        # Create edge object
        edge = Edge(
            source=source,
            target=target,
            type=edge_type,
            strength=strength,
            metadata=metadata or {},
            created=datetime.now(),
            bidirectional=bidirectional
        )
        
        # Add to graph
        self.graph.add_edge(
            source,
            target,
            **asdict(edge)
        )
        
        if bidirectional:
            self.graph.add_edge(
                target,
                source,
                **asdict(edge)
            )
            
        # Clear cache
        self._clear_cache()
        
        return edge
        
    async def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node by ID."""
        if node_id in self.graph:
            return dict(self.graph.nodes[node_id])
        return None

    async def get_edges(self, node_id: str, 
                       edge_type: Optional[str] = None) -> List[Dict]:
        """Get edges connected to a node."""
        edges = []
        
        # Outgoing edges
        for _, target, data in self.graph.edges(node_id, data=True):
            if not edge_type or data['type'] == edge_type:
                edges.append({
                    'source': node_id,
                    'target': target,
                    **data
                })
                
        # Incoming edges
        for source, _, data in self.graph.in_edges(node_id, data=True):
            if not edge_type or data['type'] == edge_type:
                edges.append({
                    'source': source,
                    'target': node_id,
                    **data
                })
                
        return edges

    async def query(self, query: str, context: Dict,
                   limit: int = 5) -> List[Dict]:
        """
        Query the graph for relevant nodes.
        
        Args:
            query: Query string
            context: Query context
            limit: Maximum results
            
        Returns:
            List of relevant nodes with scores
        """
        # Generate query embedding
        query_embedding = await self._generate_embedding(query)
        
        # Calculate similarity scores
        scores = []
        for node_id, node_data in self.graph.nodes(data=True):
            if node_data.get('embedding') is not None:
                similarity = cosine_similarity(
                    query_embedding.reshape(1, -1),
                    node_data['embedding'].reshape(1, -1)
                )[0][0]
                
                # Apply context boost
                boost = self._calculate_context_boost(node_id, context)
                final_score = similarity * boost
                
                scores.append((node_id, final_score))
                
        # Sort and return top results
        scores.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for node_id, score in scores[:limit]:
            node_data = dict(self.graph.nodes[node_id])
            node_data['score'] = score
            results.append(node_data)
            
        return results

    async def find_paths(self, source: str, target: str,
                        max_depth: int = 3) -> List[List[str]]:
        """Find paths between nodes."""
        try:
            paths = list(nx.all_simple_paths(
                self.graph,
                source=source,
                target=target,
                cutoff=max_depth
            ))
            return paths
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    async def get_subgraph(self, center_node: str,
                          depth: int = 2) -> nx.DiGraph:
        """Get subgraph centered on a node."""
        nodes = {center_node}
        current_depth = 0
        
        while current_depth < depth:
            new_nodes = set()
            for node in nodes:
                neighbors = set(self.graph.successors(node)) | set(self.graph.predecessors(node))
                new_nodes.update(neighbors)
            nodes.update(new_nodes)
            current_depth += 1
            
        return self.graph.subgraph(nodes).copy()

    async def update_node(self, node_id: str,
                         content: Optional[str] = None,
                         metadata: Optional[Dict] = None) -> bool:
        """Update a node's content and/or metadata."""
        if node_id not in self.graph:
            return False
            
        node_data = dict(self.graph.nodes[node_id])
        
        if content is not None:
            node_data['content'] = content
            node_data['embedding'] = await self._generate_embedding(content)
            self._content_index[node_id] = content
            
        if metadata is not None:
            # Remove old tag indexing
            old_metadata = node_data.get('metadata', {})
            if 'tags' in old_metadata:
                for tag in old_metadata['tags']:
                    if tag in self._tag_index:
                        self._tag_index[tag].discard(node_id)
                        
            # Update metadata
            node_data['metadata'] = metadata
            
            # Add new tag indexing
            if 'tags' in metadata:
                for tag in metadata['tags']:
                    if tag not in self._tag_index:
                        self._tag_index[tag] = set()
                    self._tag_index[tag].add(node_id)
                    
        node_data['modified'] = datetime.now()
        
        # Update graph
        self.graph.nodes[node_id].update(node_data)
        
        # Clear cache
        self._clear_cache()
        
        return True

    async def update_edge(self, source: str, target: str,
                         strength: Optional[float] = None,
                         metadata: Optional[Dict] = None) -> bool:
        """Update an edge's properties."""
        if not self.graph.has_edge(source, target):
            return False
            
        edge_data = dict(self.graph.edges[source, target])
        
        if strength is not None:
            edge_data['strength'] = strength
            
        if metadata is not None:
            edge_data['metadata'] = metadata
            
        # Update graph
        self.graph.edges[source, target].update(edge_data)
        
        # Update bidirectional edge if exists
        if edge_data.get('bidirectional') and self.graph.has_edge(target, source):
            self.graph.edges[target, source].update(edge_data)
            
        # Clear cache
        self._clear_cache()
        
        return True

    async def remove_node(self, node_id: str) -> bool:
        """Remove a node and its edges."""
        if node_id not in self.graph:
            return False
            
        # Remove from indexes
        node_data = dict(self.graph.nodes[node_id])
        
        self._content_index.pop(node_id, None)
        
        node_type = node_data.get('type')
        if node_type in self._type_index:
            self._type_index[node_type].discard(node_id)
            
        metadata = node_data.get('metadata', {})
        if 'tags' in metadata:
            for tag in metadata['tags']:
                if tag in self._tag_index:
                    self._tag_index[tag].discard(node_id)
                    
        # Remove from graph
        self.graph.remove_node(node_id)
        
        # Clear cache
        self._clear_cache()
        
        return True

    async def _generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for text."""
        # Use TF-IDF for now - could be replaced with more sophisticated embedding
        try:
            vector = self.vectorizer.fit_transform([text])
            return vector.toarray()[0]
        except:
            # Return zero vector if vectorization fails
            return np.zeros(self.embedding_dim)

    def _calculate_context_boost(self, node_id: str, context: Dict) -> float:
        """Calculate context-based boost for node."""
        boost = 1.0
        
        # Boost for matching tags
        node_data = dict(self.graph.nodes[node_id])
        node_tags = set(node_data.get('metadata', {}).get('tags', []))
        context_tags = set(context.get('tags', []))
        matching_tags = len(node_tags & context_tags)
        
        if matching_tags > 0:
            boost *= (1 + 0.2 * matching_tags)
            
        # Boost for recent access
        if node_data.get('hits', 0) > 0:
            recency_boost = min(1 + (node_data['hits'] / 100), 2.0)
            boost *= recency_boost
            
        return boost

    def _clear_cache(self):
        """Clear the cache."""
        self._cache.clear()
        
    async def save(self, path: Path):
        """Save graph to file."""
        data = {
            'nodes': dict(self.graph.nodes(data=True)),
            'edges': list(self.graph.edges(data=True)),
            'indexes': {
                'tags': {tag: list(nodes) for tag, nodes in self._tag_index.items()},
                'types': {type_: list(nodes) for type_, nodes in self._type_index.items()}
            }
        }
        
        with open(path, 'w') as f:
            json.dump(data, f)
            
    async def load(self, path: Path):
        """Load graph from file."""
        with open(path) as f:
            data = json.load(f)
            
        # Clear current graph
        self.graph.clear()
        self._tag_index.clear()
        self._type_index.clear()
        
        # Load nodes
        for node_id, node_data in data['nodes'].items():
            self.graph.add_node(node_id, **node_data)
            
        # Load edges
        for source, target, edge_data in data['edges']:
            self.graph.add_edge(source, target, **edge_data)
            
        # Load indexes
        for tag, nodes in data['indexes']['tags'].items():
            self._tag_index[tag] = set(nodes)
            
        for type_, nodes in data['indexes']['types'].items():
            self._type_index[type_] = set(nodes)

    async def close(self):
        """Clean up resources."""
        self._cache.clear()
        self.graph.clear()