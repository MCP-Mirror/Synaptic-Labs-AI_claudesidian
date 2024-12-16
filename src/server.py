# File: claudesidian/server.py

"""
Main MCP server implementation for Claudesidian.
Integrates vault operations, web scraping, and memory systems.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from config import Config
from core.vault import VaultManager
from web.scraper import WebScraper
from memory.manager import MemoryManager
from utils.path_resolver import PathResolver
from tools import get_all_tools

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ClaudesidianServer:
    """
    MCP server implementation combining Obsidian vault access, web scraping,
    and memory systems.
    """
    
    def __init__(self, config: Config):
        """Initialize server with configuration."""
        self.config = config
        self.server = Server("claudesidian")
        
        # Initialize components
        self.path_resolver = PathResolver(config.vault_path)
        self.vault = VaultManager(config.vault_path, self.path_resolver)
        self.web = WebScraper()
        self.memory = MemoryManager(self.vault)
        
        # Register handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register all tool handlers with the MCP server."""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """List all available tools."""
            return get_all_tools()

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> types.CallToolResult:
            """Handle tool calls."""
            try:
                if arguments is None:
                    arguments = {}
                
                # Vault operations
                if name == "update_daily_note":
                    daily_path = await self.path_resolver.get_todays_note_path()
                    content = arguments["content"]
                    position = arguments.get("position", "append")
                    section = arguments.get("section")
                    
                    await self.vault.update_note(daily_path, content, position, section)
                    return types.CallToolResult(
                        content=[types.TextContent(type="text", 
                            text=f"Updated daily note at {daily_path}")]
                    )
                
                elif name == "smart_create_note":
                    # Let path resolver find the best location
                    location, confidence = await self.path_resolver.find_best_location(
                        title=arguments["title"],
                        content=arguments["content"],
                        note_type=arguments.get("type"),
                        tags=arguments.get("tags")
                    )
                    
                    path = location / f"{arguments['title']}.md"
                    await self.vault.create_note(
                        path=path,
                        content=arguments["content"],
                        frontmatter={
                            "title": arguments["title"],
                            "type": arguments.get("type"),
                            "tags": arguments.get("tags", [])
                        }
                    )
                    
                    return types.CallToolResult(
                        content=[types.TextContent(type="text",
                            text=f"Created note at {path} (confidence: {confidence:.2f})")]
                    )
                
                # Web operations
                elif name == "smart_web_capture":
                    content = await self.web.scrape(arguments["url"])
                    
                    # Extract title if not provided
                    title = arguments.get("custom_title") or \
                           await self.web.extract_title(arguments["url"])
                    
                    # Find best location for the captured content
                    location, confidence = await self.path_resolver.find_best_location(
                        title=title,
                        content=content,
                        note_type="article",
                        context={"folder_hint": arguments.get("folder_hint")}
                    )
                    
                    path = location / f"{title}.md"
                    await self.vault.create_note(
                        path=path,
                        content=content,
                        frontmatter={
                            "title": title,
                            "source_url": arguments["url"],
                            "type": "article",
                            "date_captured": datetime.now().isoformat()
                        }
                    )
                    
                    return types.CallToolResult(
                        content=[types.TextContent(type="text",
                            text=f"Captured web content to {path}")]
                    )
                
                # Memory operations
                elif name == "remember":
                    memory = await self.memory.create(
                        content=arguments["content"],
                        type_hint=arguments.get("type_hint"),
                        importance=arguments.get("importance", 0.5)
                    )
                    
                    # Also create a note for significant memories
                    if memory.importance > 0.7:
                        location, _ = await self.path_resolver.find_best_location(
                            title=memory.title,
                            content=memory.content,
                            note_type=memory.type
                        )
                        await self.vault.create_note(
                            path=location / f"{memory.title}.md",
                            content=memory.content,
                            frontmatter={
                                "title": memory.title,
                                "type": memory.type,
                                "memory_id": memory.id,
                                "importance": memory.importance
                            }
                        )
                    
                    return types.CallToolResult(
                        content=[types.TextContent(type="text",
                            text=f"Created memory: {memory.title}")]
                    )
                
                else:
                    raise ValueError(f"Unknown tool: {name}")
                
            except Exception as e:
                logger.error(f"Error in tool {name}: {str(e)}")
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=f"Error: {str(e)}")],
                    isError=True
                )

    async def run(self):
        """Run the server."""
        logger.info("Starting Claudesidian server...")
        
        async with stdio_server() as streams:
            await self.server.run(
                streams[0],
                streams[1],
                self.server.create_initialization_options(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )

def main():
    """Main entry point."""
    config = Config.load()
    server = ClaudesidianServer(config)
    
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise

if __name__ == "__main__":
    main()