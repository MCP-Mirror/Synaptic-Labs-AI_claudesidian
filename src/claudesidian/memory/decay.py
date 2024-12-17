# File: claudesidian/memory/decay.py

"""
Memory decay system for Claudesidian.
Handles strength decay, reinforcement, and pruning of memories and relationships.
"""

import asyncio
from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime, timedelta
import logging
import numpy as np
from dataclasses import dataclass
import math

logger = logging.getLogger(__name__)

@dataclass
class DecayConfig:
    """Configuration for decay behavior."""
    base_decay_rate: float = 0.1           # Base rate of decay per day
    min_strength: float = 0.1              # Minimum strength before pruning
    reinforcement_boost: float = 0.2       # Strength boost from usage
    max_strength: float = 1.0              # Maximum possible strength
    context_factor: float = 0.5            # Impact of context on decay
    time_factor: float = 0.7               # Impact of time on decay
    check_interval: int = 3600             # Seconds between decay checks
    
    # Decay rates by memory type
    type_decay_rates: Dict[str, float] = None
    
    def __post_init__(self):
        if self.type_decay_rates is None:
            self.type_decay_rates = {
                'core': 0.05,        # Core memories decay slowly
                'episodic': 0.15,    # Episodic memories decay faster
                'semantic': 0.1,     # Semantic memories decay moderately
                'working': 0.3       # Working memories decay quickly
            }

class DecaySystem:
    """
    Implements memory decay based on time, usage, and context.
    """
    
    def __init__(self, graph, config: Optional[DecayConfig] = None):
        """
        Initialize decay system.
        
        Args:
            graph: KnowledgeGraph instance
            config: Optional decay configuration
        """
        self.graph = graph
        self.config = config or DecayConfig()
        
        # State tracking
        self._last_check = {}    # Last decay check times
        self._access_counts = {} # Memory access counts
        self._reinforcements = {} # Recent reinforcements
        
        # Background task
        self._decay_task = None
        self._running = False
        
    async def start(self):
        """Start background decay processing."""
        self._running = True
        self._decay_task = asyncio.create_task(self._decay_loop())
        logger.info("Started decay system")
        
    async def stop(self):
        """Stop background decay processing."""
        self._running = False
        if self._decay_task:
            self._decay_task.cancel()
            try:
                await self._decay_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped decay system")
        
    async def decay(self, memory_id: str, factor: float = 1.0) -> float:
        """
        Apply decay to a specific memory.
        
        Args:
            memory_id: ID of memory to decay
            factor: Optional multiplier for decay rate
            
        Returns:
            New memory strength
        """
        node = self.graph.graph.nodes.get(memory_id)
        if not node:
            return 0.0
            
        # Calculate time-based decay
        last_access = self._last_check.get(memory_id, node['created'])
        time_decay = self._calculate_time_decay(last_access)
        
        # Get type-specific decay rate
        memory_type = node.get('type', 'semantic')
        type_rate = self.config.type_decay_rates.get(
            memory_type,
            self.config.base_decay_rate
        )
        
        # Calculate usage factor
        uses = self._access_counts.get(memory_id, 0)
        usage_factor = 1.0 / (1.0 + math.log(1 + uses))
        
        # Calculate total decay
        decay_amount = (
            time_decay *
            type_rate *
            usage_factor *
            factor
        )
        
        # Apply decay
        old_strength = node['strength']
        new_strength = max(
            self.config.min_strength,
            old_strength - decay_amount
        )
        
        # Update node
        await self.graph.update_node(
            memory_id,
            metadata={'strength': new_strength}
        )
        
        # Update tracking
        self._last_check[memory_id] = datetime.now()
        
        return new_strength
        
    async def reinforce(self, memory_id: str, boost: float = None) -> float:
        """
        Reinforce a memory through usage.
        
        Args:
            memory_id: ID of memory to reinforce
            boost: Optional custom boost amount
            
        Returns:
            New memory strength
        """
        node = self.graph.graph.nodes.get(memory_id)
        if not node:
            return 0.0
            
        # Calculate reinforcement
        boost = boost or self.config.reinforcement_boost
        old_strength = node['strength']
        new_strength = min(
            self.config.max_strength,
            old_strength + boost
        )
        
        # Update node
        await self.graph.update_node(
            memory_id,
            metadata={'strength': new_strength}
        )
        
        # Update tracking
        self._access_counts[memory_id] = self._access_counts.get(memory_id, 0) + 1
        self._reinforcements[memory_id] = datetime.now()
        
        return new_strength
        
    async def prune(self, min_strength: float = None) -> List[str]:
        """
        Remove weak memories.
        
        Args:
            min_strength: Optional minimum strength threshold
            
        Returns:
            List of pruned memory IDs
        """
        threshold = min_strength or self.config.min_strength
        pruned = []
        
        for node_id, node in self.graph.graph.nodes(data=True):
            if node['strength'] < threshold:
                # Don't prune core memories
                if node.get('type') == 'core':
                    continue
                    
                await self.graph.remove_node(node_id)
                pruned.append(node_id)
                
                # Clean up tracking
                self._last_check.pop(node_id, None)
                self._access_counts.pop(node_id, None)
                self._reinforcements.pop(node_id, None)
                
        return pruned
        
    async def _decay_loop(self):
        """Background task for periodic decay."""
        while self._running:
            try:
                # Get nodes needing decay
                now = datetime.now()
                to_decay = []
                
                for node_id, node in self.graph.graph.nodes(data=True):
                    last_check = self._last_check.get(node_id, node['created'])
                    if (now - last_check).total_seconds() >= self.config.check_interval:
                        to_decay.append(node_id)
                        
                # Apply decay in batches
                for node_id in to_decay:
                    await self.decay(node_id)
                    
                # Prune weak memories periodically (daily)
                if now.hour == 0 and now.minute == 0:
                    await self.prune()
                    
            except Exception as e:
                logger.error(f"Error in decay loop: {e}")
                
            await asyncio.sleep(self.config.check_interval)
            
    def _calculate_time_decay(self, last_access: datetime) -> float:
        """Calculate time-based decay factor."""
        now = datetime.now()
        age = (now - last_access).total_seconds()
        
        # Exponential decay with time factor
        decay = 1 - math.exp(-age / (86400 * self.config.time_factor))
        return decay
        
    def get_memory_stats(self, memory_id: str) -> Dict[str, Any]:
        """Get decay-related stats for a memory."""
        node = self.graph.graph.nodes.get(memory_id)
        if not node:
            return {}
            
        return {
            'strength': node['strength'],
            'last_access': self._last_check.get(memory_id, node['created']),
            'access_count': self._access_counts.get(memory_id, 0),
            'last_reinforced': self._reinforcements.get(memory_id),
            'memory_type': node.get('type', 'semantic'),
            'decay_rate': self.config.type_decay_rates.get(
                node.get('type', 'semantic'),
                self.config.base_decay_rate
            )
        }