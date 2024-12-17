"""
Map of Content (MOC) generator for Claudesidian memory system.
Generates dynamic content maps and navigation structures.
"""

import asyncio
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging
from pathlib import Path
import networkx as nx
import numpy as np
from collections import defaultdict

from .graph import KnowledgeGraph

logger = logging.getLogger(__name__)

@dataclass
class MOCNode:
    """Represents a node in the Map of Content."""
    id: str
    title: str
    type: str
    strength: float
    level: int
    children: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.children is None:
            self.children = []

@dataclass
class MOCStructure:
    """Overall MOC structure."""
    root: MOCNode
    nodes: Dict[str, MOCNode]
    relationships: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    timestamp: datetime

class MOCGenerator:
    """
    Generates Maps of Content (MOCs) to aid navigation and discovery.
    """
    
    def __init__(self, graph: KnowledgeGraph,
                 max_nodes: int = 50,
                 min_similarity: float = 0.3):
        """
        Initialize MOC generator.
        
        Args:
            graph: Knowledge graph instance
            max_nodes: Maximum nodes in a single MOC
            min_similarity: Minimum similarity for connections
        """
        self.graph = graph
        self.max_nodes = max_nodes
        self.min_similarity = min_similarity
        
        # Default templates for different MOC types
        self.templates = {
            'topic': {
                'levels': 3,
                'include_tags': True,
                'group_by': 'type'
            },
            'timeline': {
                'levels': 2,
                'sort_by': 'created',
                'group_by': 'date'
            },
            'network': {
                'levels': 2,
                'max_connections': 5,
                'min_strength': 0.4
            }
        }
        
        # Enhanced caching
        self._moc_cache = {}
        self._cache_ttl = 600  # 10 minutes
        
        # Parallel processing settings
        self._chunk_size = 25
        self._max_workers = 4

    async def generate_moc(self, context: Dict) -> MOCStructure:
        """
        Generate a context-based Map of Content.
        
        Args:
            context: Generation context including:
                - query: Search query
                - tags: Relevant tags
                - note_type: Type of notes to include
                - template: MOC template to use
                
        Returns:
            Generated MOC structure
        """
        try:
            # Extract key context elements
            query = context.get('query', '')
            tags = set(context.get('tags', []))
            note_type = context.get('note_type')
            template = self.templates.get(
                context.get('template', 'topic')
            )
            
            # Find relevant nodes
            relevant = await self._find_relevant_nodes(
                query, tags, note_type, template
            )
            
            # Discover connections
            connections = await self._discover_connections(
                relevant, template
            )
            
            # Build hierarchy
            root, nodes = await self._build_hierarchy(
                relevant, connections, template
            )
            
            # Create MOC structure
            moc = MOCStructure(
                root=root,
                nodes=nodes,
                relationships=connections,
                metadata={
                    'query': query,
                    'tags': list(tags),
                    'type': note_type,
                    'template': template
                },
                timestamp=datetime.now()
            )
            
            return moc
            
        except Exception as e:
            logger.error(f"Error generating MOC: {e}")
            raise

    async def generate_moc_parallel(self, contexts: List[Dict]) -> List[MOCStructure]:
        """Generate multiple MOCs in parallel."""
        results = []
        for i in range(0, len(contexts), self._chunk_size):
            chunk = contexts[i:i + self._chunk_size]
            tasks = [self.generate_moc(ctx) for ctx in chunk]
            chunk_results = await asyncio.gather(*tasks)
            results.extend(chunk_results)
        return results

    async def suggest_connections(self, note_id: str,
                                limit: int = 10) -> List[Dict[str, Any]]:
        """
        Suggest relevant connections for a note.
        
        Args:
            note_id: ID of note to find connections for
            limit: Maximum number of suggestions
            
        Returns:
            List of suggested connections with metadata
        """
        try:
            # Get note data
            note = await self.graph.get_node(note_id)
            if not note:
                return []
                
            # Calculate similarities
            similarities = []
            for other_id, other in self.graph.graph.nodes(data=True):
                if other_id == note_id:
                    continue
                    
                # Calculate multiple similarity factors
                content_sim = self._calculate_content_similarity(
                    note.get('content', ''),
                    other.get('content', '')
                )
                
                tag_sim = self._calculate_tag_similarity(
                    note.get('metadata', {}).get('tags', []),
                    other.get('metadata', {}).get('tags', [])
                )
                
                temporal_sim = self._calculate_temporal_similarity(
                    note.get('created'),
                    other.get('created')
                )
                
                # Combine similarities
                total_sim = (
                    content_sim * 0.5 +
                    tag_sim * 0.3 +
                    temporal_sim * 0.2
                )
                
                if total_sim >= self.min_similarity:
                    similarities.append({
                        'id': other_id,
                        'title': other.get('metadata', {}).get('title', other_id),
                        'similarity': total_sim,
                        'type': other.get('type'),
                        'tags': other.get('metadata', {}).get('tags', []),
                        'created': other.get('created')
                    })
                    
            # Sort and limit results
            similarities.sort(key=lambda x: x['similarity'], reverse=True)
            return similarities[:limit]
            
        except Exception as e:
            logger.error(f"Error suggesting connections: {e}")
            return []

    async def _find_relevant_nodes(self, query: str,
                                 tags: Set[str],
                                 note_type: Optional[str],
                                 template: Dict) -> List[Dict]:
        """Find nodes relevant to the MOC context."""
        relevant = []
        
        # Query graph
        results = await self.graph.query(
            query,
            {'tags': list(tags)},
            limit=self.max_nodes
        )
        
        for node in results:
            # Filter by type if specified
            if note_type and node.get('type') != note_type:
                continue
                
            # Add to relevant nodes
            relevant.append(node)
            
        return relevant

    async def _discover_connections(self, nodes: List[Dict],
                                  template: Dict) -> List[Dict]:
        """Discover connections between relevant nodes."""
        connections = []
        
        # Get subgraph
        node_ids = [n['id'] for n in nodes]
        subgraph = await self.graph.get_subgraph(
            node_ids[0],
            depth=template.get('levels', 2)
        )
        
        # Find paths between nodes
        for i, node1 in enumerate(nodes):
            for node2 in nodes[i+1:]:
                paths = await self.graph.find_paths(
                    node1['id'],
                    node2['id'],
                    max_depth=template.get('levels', 2)
                )
                
                if paths:
                    connections.append({
                        'source': node1['id'],
                        'target': node2['id'],
                        'paths': paths,
                        'strength': self._calculate_connection_strength(paths)
                    })
                    
        return connections

    async def _build_hierarchy(self, nodes: List[Dict],
                             connections: List[Dict],
                             template: Dict) -> Tuple[MOCNode, Dict[str, MOCNode]]:
        """Build MOC hierarchy from nodes and connections."""
        # Create MOC nodes
        moc_nodes = {}
        for node in nodes:
            moc_nodes[node['id']] = MOCNode(
                id=node['id'],
                title=node.get('metadata', {}).get('title', node['id']),
                type=node.get('type', 'note'),
                strength=node.get('strength', 0.5),
                level=0,
                metadata=node.get('metadata', {})
            )
            
        # Build hierarchy based on template
        if template.get('group_by') == 'type':
            root = await self._build_type_hierarchy(moc_nodes, connections)
        elif template.get('group_by') == 'date':
            root = await self._build_temporal_hierarchy(moc_nodes, connections)
        else:
            root = await self._build_network_hierarchy(moc_nodes, connections)
            
        return root, moc_nodes

    def _calculate_content_similarity(self, text1: str, text2: str) -> float:
        """Calculate content similarity between texts."""
        if not text1 or not text2:
            return 0.0
            
        vec1 = self.graph.vectorizer.fit_transform([text1])
        vec2 = self.graph.vectorizer.fit_transform([text2])
        
        return float(vec1.dot(vec2.T).toarray()[0][0])

    def _calculate_tag_similarity(self, tags1: List[str],
                                tags2: List[str]) -> float:
        """Calculate similarity between tag sets."""
        if not tags1 or not tags2:
            return 0.0
            
        intersection = set(tags1) & set(tags2)
        union = set(tags1) | set(tags2)
        
        return len(intersection) / len(union)

    def _calculate_temporal_similarity(self, time1: datetime,
                                    time2: datetime) -> float:
        """Calculate temporal similarity between dates."""
        if not time1 or not time2:
            return 0.0
            
        diff = abs((time1 - time2).total_seconds())
        # Decay over 30 days
        decay = np.exp(-diff / (30 * 24 * 3600))
        
        return float(decay)

    def _calculate_connection_strength(self, paths: List[List[str]]) -> float:
        """Calculate connection strength from paths."""
        if not paths:
            return 0.0
            
        # Use shortest path length as main factor
        min_length = min(len(path) for path in paths)
        strength = 1.0 / min_length
        
        # Boost for multiple paths
        path_boost = min(len(paths) * 0.1, 0.5)
        strength += path_boost
        
        return min(strength, 1.0)