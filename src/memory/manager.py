# File: claudesidian/memory/manager.py

"""
Memory system manager for Claudesidian.
Coordinates memory operations, context handling, and component interactions.
"""

import asyncio
from typing import Dict, List, Optional, Set, Any
from datetime import datetime
import logging
from pathlib import Path

from .graph import KnowledgeGraph
from .relationships import RelationshipManager
from .decay import DecaySystem
from .moc import MOCGenerator
from ..core.vault import VaultManager
from ..core.notes import NoteManager

logger = logging.getLogger(__name__)

class MemoryContext:
    """Represents the current memory context for operations."""
    def __init__(self, 
                 current_note: Optional[str] = None,
                 active_tags: Optional[Set[str]] = None,
                 recent_notes: Optional[List[str]] = None,
                 importance: float = 0.5):
        self.current_note = current_note
        self.active_tags = active_tags or set()
        self.recent_notes = recent_notes or []
        self.importance = importance
        self.timestamp = datetime.now()
        self.metadata: Dict[str, Any] = {}

class MemoryManager:
    """
    Central coordinator for the memory system.
    Manages interactions between components and handles memory operations.
    """
    
    def __init__(self, vault_manager: VaultManager):
        """
        Initialize the memory system.
        
        Args:
            vault_manager: VaultManager instance
        """
        self.vault = vault_manager
        self.notes = NoteManager(vault_manager)
        
        # Initialize components
        self.graph = KnowledgeGraph()
        self.relationships = RelationshipManager()
        self.decay = DecaySystem()
        self.moc = MOCGenerator(self.graph)
        
        # State tracking
        self.current_context = MemoryContext()
        self._processing_queue = asyncio.Queue()
        self._background_task = None
        
        # Register vault events
        self.vault.on('note_modified', self._handle_note_modified)
        self.vault.on('note_created', self._handle_note_created)
        self.vault.on('note_deleted', self._handle_note_deleted)

    async def initialize(self):
        """Initialize the memory system and start background processing."""
        # Build initial graph from vault
        await self._build_initial_graph()
        
        # Start background processing
        self._background_task = asyncio.create_task(self._background_processor())
        
        logger.info("Memory system initialized")

    async def process_input(self, input_text: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Process new input and update memory system.
        
        Args:
            input_text: Text to process
            context: Optional context information
            
        Returns:
            Dict containing processing results
        """
        # Update context
        self._update_context(context)
        
        # Process input
        result = {
            'memories': [],
            'connections': [],
            'suggestions': []
        }
        
        try:
            # Find relevant existing memories
            relevant_memories = await self.graph.find_relevant(
                input_text, 
                self.current_context
            )
            
            # Create new memory if needed
            if len(input_text) > 50:  # Only create for substantial input
                memory = await self._create_memory(input_text)
                result['memories'].append(memory)
                
            # Update relationships
            connections = await self.relationships.analyze_connections(
                input_text,
                relevant_memories,
                self.current_context
            )
            result['connections'].extend(connections)
            
            # Generate suggestions
            suggestions = await self.moc.generate_suggestions(
                input_text,
                relevant_memories,
                self.current_context
            )
            result['suggestions'].extend(suggestions)
            
            # Queue background processing
            await self._processing_queue.put({
                'type': 'input_processed',
                'content': input_text,
                'context': self.current_context,
                'timestamp': datetime.now()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing input: {e}")
            return result

    async def query_memory(self, query: str, context: Optional[Dict] = None,
                         limit: int = 5) -> Dict[str, Any]:
        """
        Query the memory system.
        
        Args:
            query: Query string
            context: Optional context information
            limit: Maximum number of results
            
        Returns:
            Dict containing query results
        """
        self._update_context(context)
        
        results = {
            'memories': [],
            'paths': [],
            'map': None  # MOC for results
        }
        
        try:
            # Find relevant memories
            memories = await self.graph.query(
                query,
                self.current_context,
                limit=limit
            )
            results['memories'] = memories
            
            # Find connection paths
            if len(memories) >= 2:
                paths = await self.relationships.find_paths(
                    memories,
                    self.current_context
                )
                results['paths'] = paths
                
            # Generate result map
            moc = await self.moc.generate_moc(
                memories,
                self.current_context
            )
            results['map'] = moc
            
            # Update memory strengths
            for memory in memories:
                await self.decay.reinforce(memory['id'])
                
            return results
            
        except Exception as e:
            logger.error(f"Error querying memory: {e}")
            return results

    async def remember(self, note_path: str) -> Dict[str, Any]:
        """
        Strengthen memory of a specific note.
        
        Args:
            note_path: Path to note
            
        Returns:
            Dict containing memory details
        """
        try:
            # Get note content
            content, metadata = await self.notes.get_note(note_path)
            
            # Reinforce memory
            memory = await self.graph.get_node(note_path)
            if memory:
                await self.decay.reinforce(memory['id'])
                
                # Update relationships
                await self.relationships.reinforce_connections(
                    memory['id'],
                    self.current_context
                )
                
            return memory
            
        except Exception as e:
            logger.error(f"Error remembering note {note_path}: {e}")
            return None

    async def forget(self, note_path: str) -> bool:
        """
        Weaken memory of a specific note.
        
        Args:
            note_path: Path to note
            
        Returns:
            True if successful
        """
        try:
            memory = await self.graph.get_node(note_path)
            if memory:
                await self.decay.decay(memory['id'], factor=2.0)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Error forgetting note {note_path}: {e}")
            return False

    async def generate_moc(self, center_note: str) -> Dict[str, Any]:
        """
        Generate a Map of Content centered on a note.
        
        Args:
            center_note: Path to central note
            
        Returns:
            Dict containing MOC data
        """
        try:
            # Get note and its connections
            memory = await self.graph.get_node(center_note)
            if not memory:
                return None
                
            # Generate MOC
            moc = await self.moc.generate_moc(
                [memory],
                self.current_context,
                depth=2
            )
            
            return moc
            
        except Exception as e:
            logger.error(f"Error generating MOC for {center_note}: {e}")
            return None

    def _update_context(self, context: Optional[Dict] = None):
        """Update the current context with new information."""
        if not context:
            return
            
        new_context = MemoryContext(
            current_note=context.get('current_note', self.current_context.current_note),
            active_tags=set(context.get('tags', [])) | self.current_context.active_tags,
            recent_notes=context.get('recent_notes', self.current_context.recent_notes),
            importance=context.get('importance', self.current_context.importance)
        )
        
        self.current_context = new_context

    async def _build_initial_graph(self):
        """Build initial knowledge graph from vault contents."""
        try:
            # Get all notes
            notes = await self.vault.get_all_notes()
            
            # Process each note
            for note_path in notes:
                content, metadata = await self.notes.get_note(note_path)
                
                # Add to graph
                await self.graph.add_node(
                    str(note_path),
                    content=content,
                    metadata=metadata
                )
                
            # Build relationships
            await self.relationships.build_initial_connections()
            
            logger.info(f"Built initial graph with {len(notes)} notes")
            
        except Exception as e:
            logger.error(f"Error building initial graph: {e}")

    async def _background_processor(self):
        """Background task for processing queue items."""
        while True:
            try:
                # Get item from queue
                item = await self._processing_queue.get()
                
                # Process based on type
                if item['type'] == 'input_processed':
                    await self._process_input_background(item)
                elif item['type'] == 'note_modified':
                    await self._process_note_update(item)
                    
                self._processing_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error in background processor: {e}")
                
            await asyncio.sleep(0.1)  # Prevent CPU overuse

    async def _handle_note_modified(self, path: Path):
        """Handle note modification events."""
        await self._processing_queue.put({
            'type': 'note_modified',
            'path': path,
            'timestamp': datetime.now()
        })

    async def _handle_note_created(self, path: Path):
        """Handle note creation events."""
        try:
            content, metadata = await self.notes.get_note(path)
            await self.graph.add_node(
                str(path),
                content=content,
                metadata=metadata
            )
        except Exception as e:
            logger.error(f"Error handling new note {path}: {e}")

    async def _handle_note_deleted(self, path: Path):
        """Handle note deletion events."""
        try:
            await self.graph.remove_node(str(path))
        except Exception as e:
            logger.error(f"Error handling deleted note {path}: {e}")

    async def close(self):
        """Clean up resources."""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
                
        await self.graph.close()