# File: claudesidian/memory/relationships.py

"""
Relationship management for Claudesidian memory system.
Handles relationship detection, strength calculation, and pattern analysis.
"""

from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime
import logging
from pathlib import Path
import networkx as nx
from collections import defaultdict
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

logger = logging.getLogger(__name__)

class RelationshipType:
    """Types of relationships between notes."""
    LINK = "link"               # Explicit wiki link
    BACKLINK = "backlink"       # Reverse wiki link
    REFERENCE = "reference"     # Referenced but not linked
    SEMANTIC = "semantic"       # Content similarity
    COOCCURRENCE = "cooccur"   # Tag co-occurrence
    TEMPORAL = "temporal"      # Created/modified close in time
    PARENT = "parent"          # Parent folder relationship
    SIBLING = "sibling"        # Same folder relationship
    CHILD = "child"           # Child note relationship

class RelationshipManager:
    """
    Manages relationships between notes in the memory system.
    """
    
    def __init__(self, graph, min_similarity: float = 0.3):
        """
        Initialize relationship manager.
        
        Args:
            graph: KnowledgeGraph instance
            min_similarity: Minimum similarity for semantic relationships
        """
        self.graph = graph
        self.min_similarity = min_similarity
        
        # Vectorizer for semantic similarity
        self.vectorizer = TfidfVectorizer(
            max_features=10000,
            stop_words='english'
        )
        
        # Pattern detection
        self._pattern_cache = {}
        self._cooccurrence_matrix = defaultdict(lambda: defaultdict(int))
        
    async def analyze_connections(self, content: str, 
                                related_notes: List[Dict],
                                context: Dict) -> List[Dict[str, Any]]:
        """
        Analyze connections for new content.
        
        Args:
            content: Content to analyze
            related_notes: List of related notes
            context: Current context
            
        Returns:
            List of detected relationships
        """
        relationships = []
        
        # Extract wiki links
        wiki_links = self._extract_wiki_links(content)
        for link in wiki_links:
            relationships.append({
                'type': RelationshipType.LINK,
                'target': link,
                'strength': 1.0,
                'metadata': {'explicit': True}
            })
            
        # Find semantic relationships
        semantic_rels = await self._find_semantic_relationships(
            content,
            related_notes
        )
        relationships.extend(semantic_rels)
        
        # Check temporal relationships
        temporal_rels = self._find_temporal_relationships(
            context.get('timestamp'),
            related_notes
        )
        relationships.extend(temporal_rels)
        
        # Analyze patterns
        pattern_rels = await self._analyze_patterns(
            content,
            related_notes,
            context
        )
        relationships.extend(pattern_rels)
        
        return relationships
        
    async def find_paths(self, notes: List[Dict],
                        context: Dict,
                        max_depth: int = 3) -> List[Dict]:
        """
        Find connection paths between notes.
        
        Args:
            notes: List of notes to connect
            context: Current context
            max_depth: Maximum path depth
            
        Returns:
            List of paths with metadata
        """
        paths = []
        
        for i, note1 in enumerate(notes):
            for note2 in notes[i+1:]:
                # Find all paths between notes
                note_paths = await self.graph.find_paths(
                    note1['id'],
                    note2['id'],
                    max_depth=max_depth
                )
                
                for path in note_paths:
                    # Calculate path strength
                    strength = self._calculate_path_strength(path)
                    
                    # Get relationship types along path
                    rel_types = []
                    for j in range(len(path)-1):
                        edge = self.graph.graph.edges[path[j], path[j+1]]
                        rel_types.append(edge['type'])
                        
                    paths.append({
                        'start': note1['id'],
                        'end': note2['id'],
                        'path': path,
                        'types': rel_types,
                        'strength': strength
                    })
                    
        # Sort by strength
        paths.sort(key=lambda x: x['strength'], reverse=True)
        
        return paths
        
    async def build_initial_connections(self) -> None:
        """Build initial relationships for all notes."""
        # Get all notes
        notes = list(self.graph.graph.nodes(data=True))
        
        # Build relationships between all pairs
        for i, (id1, note1) in enumerate(notes):
            for id2, note2 in notes[i+1:]:
                # Skip if already connected
                if self.graph.graph.has_edge(id1, id2):
                    continue
                    
                relationships = []
                
                # Check for wiki links
                if self._has_wiki_link(note1['content'], id2):
                    relationships.append({
                        'type': RelationshipType.LINK,
                        'strength': 1.0
                    })
                    
                if self._has_wiki_link(note2['content'], id1):
                    relationships.append({
                        'type': RelationshipType.BACKLINK,
                        'strength': 1.0
                    })
                    
                # Check for semantic similarity
                similarity = self._calculate_similarity(
                    note1['content'],
                    note2['content']
                )
                if similarity >= self.min_similarity:
                    relationships.append({
                        'type': RelationshipType.SEMANTIC,
                        'strength': similarity
                    })
                    
                # Check for tag co-occurrence
                cooccur = self._calculate_tag_cooccurrence(
                    note1['metadata'].get('tags', []),
                    note2['metadata'].get('tags', [])
                )
                if cooccur > 0:
                    relationships.append({
                        'type': RelationshipType.COOCCURRENCE,
                        'strength': cooccur
                    })
                    
                # Check for temporal proximity
                temporal = self._calculate_temporal_proximity(
                    note1['created'],
                    note2['created']
                )
                if temporal > 0:
                    relationships.append({
                        'type': RelationshipType.TEMPORAL,
                        'strength': temporal
                    })
                    
                # Add folder relationships
                if self._are_siblings(id1, id2):
                    relationships.append({
                        'type': RelationshipType.SIBLING,
                        'strength': 0.7
                    })
                elif self._is_parent(id1, id2):
                    relationships.append({
                        'type': RelationshipType.PARENT,
                        'strength': 0.8
                    })
                elif self._is_parent(id2, id1):
                    relationships.append({
                        'type': RelationshipType.CHILD,
                        'strength': 0.8
                    })
                    
                # Add combined relationships
                for rel in relationships:
                    await self.graph.add_edge(
                        id1,
                        id2,
                        edge_type=rel['type'],
                        strength=rel['strength']
                    )
                    
    async def update_relationships(self, note_id: str,
                                 old_content: str,
                                 new_content: str) -> None:
        """Update relationships when note content changes."""
        # Remove old semantic relationships
        old_edges = list(self.graph.graph.edges(note_id, data=True))
        for _, target, data in old_edges:
            if data['type'] == RelationshipType.SEMANTIC:
                self.graph.graph.remove_edge(note_id, target)
                
        # Calculate new semantic relationships
        note_data = self.graph.graph.nodes[note_id]
        other_notes = [
            (nid, data) for nid, data in self.graph.graph.nodes(data=True)
            if nid != note_id
        ]
        
        for other_id, other_data in other_notes:
            similarity = self._calculate_similarity(
                new_content,
                other_data['content']
            )
            if similarity >= self.min_similarity:
                await self.graph.add_edge(
                    note_id,
                    other_id,
                    edge_type=RelationshipType.SEMANTIC,
                    strength=similarity
                )
                
        # Update wiki link relationships
        old_links = set(self._extract_wiki_links(old_content))
        new_links = set(self._extract_wiki_links(new_content))
        
        # Remove obsolete links
        for link in old_links - new_links:
            if self.graph.graph.has_edge(note_id, link):
                self.graph.graph.remove_edge(note_id, link)
                
        # Add new links
        for link in new_links - old_links:
            await self.graph.add_edge(
                note_id,
                link,
                edge_type=RelationshipType.LINK,
                strength=1.0
            )
            
    async def reinforce_connections(self, note_id: str,
                                  context: Dict) -> None:
        """Reinforce relationships based on usage."""
        edges = list(self.graph.graph.edges(note_id, data=True))
        for _, target, data in edges:
            # Boost strength based on relationship type
            boost = {
                RelationshipType.LINK: 0.1,
                RelationshipType.SEMANTIC: 0.05,
                RelationshipType.COOCCURRENCE: 0.03,
                RelationshipType.TEMPORAL: 0.02
            }.get(data['type'], 0.01)
            
            # Apply context boost
            if context.get('tags'):
                target_tags = self.graph.graph.nodes[target].get('metadata', {}).get('tags', [])
                matching_tags = len(set(context['tags']) & set(target_tags))
                boost *= (1 + 0.1 * matching_tags)
                
            # Update strength
            new_strength = min(data['strength'] + boost, 1.0)
            await self.graph.update_edge(
                note_id,
                target,
                strength=new_strength
            )

    def _extract_wiki_links(self, content: str) -> List[str]:
        """Extract wiki links from content."""
        return re.findall(r'\[\[(.*?)\]\]', content)
        
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate semantic similarity between texts."""
        vectors = self.vectorizer.fit_transform([text1, text2])
        similarity = cosine_similarity(vectors[0:1], vectors[1:2])[0][0]
        return float(similarity)
        
    def _calculate_tag_cooccurrence(self, tags1: List[str],
                                  tags2: List[str]) -> float:
        """Calculate tag co-occurrence strength."""
        if not tags1 or not tags2:
            return 0.0
            
        intersection = set(tags1) & set(tags2)
        union = set(tags1) | set(tags2)
        
        return len(intersection) / len(union)
        
    def _calculate_temporal_proximity(self, time1: datetime,
                                   time2: datetime) -> float:
        """Calculate temporal proximity strength."""
        if not time1 or not time2:
            return 0.0
            
        diff = abs((time1 - time2).total_seconds())
        # Decay over 24 hours
        decay = np.exp(-diff / (24 * 3600))
        
        return float(decay)
        
    def _calculate_path_strength(self, path: List[str]) -> float:
        """Calculate overall path strength."""
        strengths = []
        for i in range(len(path)-1):
            edge = self.graph.graph.edges[path[i], path[i+1]]
            strengths.append(edge['strength'])
            
        # Multiply strengths and penalize path length
        return np.prod(strengths) * (0.9 ** (len(path)-2))
        
    def _are_siblings(self, id1: str, id2: str) -> bool:
        """Check if notes are siblings (same folder)."""
        path1 = Path(id1).parent
        path2 = Path(id2).parent
        return path1 == path2
        
    def _is_parent(self, id1: str, id2: str) -> bool:
        """Check if id1 is parent of id2."""
        path1 = Path(id1).parent
        path2 = Path(id2)
        return path2.is_relative_to(path1)