# File: claudesidian/server.py

"""
Main server implementation for Claudesidian.
"""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server

from claudesidian.config import Config
from claudesidian.core.vault import VaultManager
from claudesidian.utils.path_resolver import PathResolver
from claudesidian.web.scraper import WebScraper

# Memory system imports
from claudesidian.memory.manager import MemoryManager
from claudesidian.memory.graph import KnowledgeGraph
from claudesidian.memory.relationships import RelationshipManager
from claudesidian.memory.decay import DecaySystem

from claudesidian.tools import get_all_tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claudesidian")

# Get vault path from environment
vault_path = os.getenv("VAULT_PATH")
if not vault_path:
    raise ValueError("VAULT_PATH environment variable required")

class ClaudesidianServer:
    """MCP server for managing Obsidian vaults with Claude."""
    
    def __init__(self, config: Config):
        self.config = config
        self.server = Server("claudesidian")
        self.components = {}
        
    async def setup(self):
        """Initialize components asynchronously."""
        try:
            logger.info("Starting Claudesidian server initialization...")
            await self._init_components()
            logger.info("✓ Server initialization completed successfully!")
        except Exception as e:
            logger.error(f"Failed to initialize server: {e}")
            raise

    async def _init_components(self):
        """Initialize all server components."""
        # Initialize path resolver first
        logger.info("Initializing path resolver...")
        self.path_resolver = PathResolver(str(self.config.vault_path))
        
        # Pass path resolver to vault manager
        logger.info("Setting up vault manager...")
        self.vault = VaultManager(self.config.vault_path, self.path_resolver)
        
        # Initialize web scraper
        logger.info("Configuring web scraper...")
        self.web = WebScraper()
        await self.web.setup()
        
        # Initialize memory system
        logger.info("Setting up memory system...")
        self.memory = await self._setup_memory()
        
        # Store components for easier access/shutdown
        self.components.update({
            'path_resolver': self.path_resolver,
            'vault': self.vault,
            'web': self.web,
            'memory': self.memory
        })
        
        logger.info("Registering handlers...")
        self._register_handlers()
        logger.info("All components initialized successfully!")

    async def _setup_memory(self):
        """Set up memory system components."""
        # Create core components
        graph = KnowledgeGraph()
        relationships = RelationshipManager(graph)
        decay = DecaySystem(graph)
        
        # Create and initialize memory manager
        memory = MemoryManager(
            self.vault,
            graph=graph,
            relationships=relationships,
            decay=decay
        )
        await memory.initialize()
        return memory

    def _register_handlers(self):
        """Register all tool and resource handlers."""
        # Defer to tools module for tool registration
        self.server.tools = get_all_tools()
        
        # Register resource handlers with error handling
        @self.server.list_resources()
        async def handle_list_resources():
            try:
                return await self.vault.list_resources()
            except Exception as e:
                logger.error(f"Error listing resources: {e}")
                raise
                
        @self.server.read_resource()
        async def handle_read_resource(uri: str):
            try:
                return await self.vault.read_resource(uri)
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}")
                raise

    async def shutdown(self):
        """Gracefully shutdown server components."""
        try:
            # First close the web scraper to handle Chrome
            if hasattr(self, 'web'):
                await self.web.close()
            
            # Then close other components
            for name, component in reversed(list(self.components.items())):
                if name == 'web':
                    continue  # Already handled
                try:
                    if hasattr(component, 'close'):
                        await component.close()
                    elif hasattr(component, 'cleanup'):
                        await component.cleanup()
                except Exception as e:
                    logger.error(f"Error shutting down {name}: {e}")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def run(self):
        """Run the server."""
        try:
            logger.info("🚀 Starting Claudesidian server...")
            await self.setup()
            
            logger.info("Server is ready to handle requests!")
            logger.info("----------------------------------------")
            logger.info(f"Vault path: {self.config.vault_path}")
            logger.info("----------------------------------------")
            
            async with stdio_server() as (read_stream, write_stream):
                try:
                    await self.server.run(
                        read_stream,
                        write_stream,
                        self.server.create_initialization_options()
                    )
                finally:
                    # Ensure cleanup happens before the event loop closes
                    await self.shutdown()
        except Exception as e:
            logger.error(f"Server error: {e}")
            await self.shutdown()
            raise

async def main():
    """Main entry point."""
    config = Config.load()
    server = ClaudesidianServer(config)
    
    try:
        await server.run()
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())