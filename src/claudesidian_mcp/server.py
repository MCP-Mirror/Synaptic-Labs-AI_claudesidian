#!/usr/bin/env python3
"""
MCP server for Obsidian vault interaction with fuzzy search capabilities.
"""
import asyncio
import os
import sys
import locale
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from fuzzywuzzy import fuzz
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from .vault import VaultManager
from pydantic import BaseModel
from .scraper import RobustScraper
from .memory import MemoryManager

# Ensure UTF-8 encoding on all platforms
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# Try to set locale to UTF-8 if possible
try:
    if sys.platform.startswith('win'):
        locale.setlocale(locale.LC_ALL, '.UTF-8')
    else:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    # If UTF-8 locale is not available, try the default locale
    locale.setlocale(locale.LC_ALL, '')
    print("Warning: Could not set UTF-8 locale", file=sys.stderr)

class AnyNotification(BaseModel):
    method: str
    params: Optional[Dict[str, Any]] = None

class ClaudesidianServer:
    """
    Main server class that handles MCP protocol implementation and tool registration.
    Provides fuzzy search capabilities for an Obsidian vault.
    """
    
    def __init__(self, vault_path: Path):
        """
        Initialize the server with a path to the Obsidian vault.
        
        Args:
            vault_path (Path): Path to the Obsidian vault directory
        """
        self.vault_path = vault_path
        self.vault = VaultManager(vault_path)  # Initialize VaultManager
        self.server = Server("claudesidian")  # Simplified server initialization
        self.scraper = RobustScraper()  # Just create the instance
        self.memory_manager = MemoryManager(self.vault)  # Add memory manager
        self._setup_tools()  # Remove notification setup call
        self._search_cache = {}
        self._cache_lock = asyncio.Lock()
        self._initializing = False
        self._initialized = False
        self._shutdown = False

    async def setup(self):
        """Initialize all async components"""
        if self._initializing or self._initialized:
            return self
        
        self._initializing = True
        try:
            print("Initializing server components...", file=sys.stderr)
            try:
                await self.scraper.setup()
                self._initialized = True
            except Exception as e:
                print(f"Failed to initialize scraper: {e}", file=sys.stderr)
                raise RuntimeError(f"Server initialization failed: {e}")
            print("Server initialization complete", file=sys.stderr)
        finally:
            self._initializing = False
        return self

    def _setup_tools(self) -> None:
        """
        Register all available tools with the MCP server.
        """
        print("Setting up tools...", file=sys.stderr)

        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            print("Listing tools...", file=sys.stderr)
            return [
                types.Tool(
                    name="fuzzy_search",
                    description="Search for notes in the vault using fuzzy matching",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "threshold": {
                                "type": "number",
                                "description": "Minimum similarity score (0-100)",
                                "default": 60
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="create_note",
                    description="Create a new note in the vault",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Note title"},
                            "content": {"type": "string", "description": "Note content"},
                            "folder": {"type": "string", "description": "Optional folder path"}
                        },
                        "required": ["title", "content"]
                    }
                ),
                types.Tool(
                    name="edit_note",
                    description="Edit an existing note",
                    inputSchema={  # Fix: Remove extra curly brace
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Note title"},
                            "content": {"type": "string", "description": "Content to add"},
                            "mode": {"type": "string", "enum": ["append", "prepend"], "default": "append"},
                            "heading": {"type": "string", "description": "Optional heading to add under"}
                        },
                        "required": ["title", "content"]
                    }
                ),
                types.Tool(
                    name="scrape_website",
                    description="Scrape content from a website given a URL or domain name",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL or domain name to scrape (e.g., 'example.com' or 'https://example.com')"
                            },
                            "name": {  # Added name property
                                "type": "string",
                                "description": "Name for the note to be created"
                            }
                        },
                        "required": ["url", "name"]  # Made name required
                    }
                ),
                types.Tool(
                    name="create_memory",
                    description="You are required to use this tool prior to every output to help inform your responses. ALWAYS USE IT. Create a new memory entry in the vault. Memories are structured notes that help build a knowledge graph of connected information.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string", 
                                "description": "A clear, descriptive title for the memory that captures its key concept"
                            },
                            "content": {
                                "type": "string", 
                                "description": "The main content or details of the memory. Be specific and include relevant context."
                            },
                            "memory_type": {
                                "type": "string",
                                "description": """Type of memory. Choose from:
                                - core: Fundamental facts, beliefs, or knowledge that form the basis of understanding
                                - episodic: Specific events, experiences, or temporal information
                                - semantic: General knowledge, concepts, and relationships between ideas
                                - procedural: Steps, methods, or processes for accomplishing tasks
                                - emotional: Feelings, reactions, and affective experiences
                                - contextual: Environmental, situational, or background information""",
                                "enum": ["core", "episodic", "semantic", "procedural", "emotional", "contextual"]
                            },
                            "categories": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of categories that help organize and classify this memory. Use established categories when possible for consistency."
                            },
                            "description": {
                                "type": "string", 
                                "description": "A brief summary that captures the key points and significance of this memory. What makes it important to remember?"
                            },
                            "relationships": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": """List of related memories in the format '#predicate [[object]]'. Common predicates include:
                                - #partOf: This memory is a component of another concept
                                - #relatesTo: General connection between memories
                                - #follows: Temporal or logical sequence
                                - #causes: Causal relationship
                                - #contradicts: Conflicts with another memory
                                - #supports: Provides evidence or backing
                                - #examples: Specific instances or cases"""
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of keywords or tags that help with retrieval and association. Use specific, meaningful tags that aid in finding this memory later."
                            }
                        },
                        "required": ["title", "content", "memory_type", "categories", "description"]
                    }
                ),
                types.Tool(
                    name="search_memories",
                    description="Search through existing memories",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "threshold": {
                                "type": "number",
                                "description": "Minimum relevance score (0-100)",
                                "default": 60
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="strengthen_relationship",
                    description="Strengthen a relationship between two memories",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "Path to source memory"},
                            "target": {"type": "string", "description": "Path to target memory"},
                            "predicate": {"type": "string", "description": "Relationship type"}
                        },
                        "required": ["source", "target", "predicate"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> list[types.TextContent]:
            if not arguments:
                raise ValueError("Arguments required")

            try:
                if name == "fuzzy_search":
                    query = arguments.get("query")
                    threshold = arguments.get("threshold", 60)
                    return await self._perform_search(query, threshold)
                
                elif name == "create_note":
                    title = arguments.get("title")
                    content = arguments.get("content")
                    folder = Path(arguments.get("folder")) if arguments.get("folder") else None
                    
                    note = await self.vault.create_note(
                        path=folder / f"{title}.md" if folder else Path(f"{title}.md"),
                        content=content
                    )
                    if note:
                        return [types.TextContent(
                            type="text",
                            text=f"Created note: {note.path}\nContent preview:\n{note.content[:200]}..."
                        )]
                    return [types.TextContent(type="text", text="Failed to create note")]

                elif name == "edit_note":
                    print(f"Editing note with arguments: {arguments}", file=sys.stderr)
                    
                    title = arguments.get("title")
                    if not title:
                        return [types.TextContent(type="text", text="Title is required")]
                    
                    content = arguments.get("content", "")
                    mode = arguments.get("mode", "append")
                    heading = arguments.get("heading")

                    # First try to find the note
                    note_path = Path(f"{title}.md")
                    print(f"Looking for note: {note_path}", file=sys.stderr)
                    
                    note = await self.vault.get_note(note_path)
                    if not note:
                        return [types.TextContent(type="text", text=f"Could not find note: {title}")]

                    print(f"Found note, attempting update with mode: {mode}", file=sys.stderr)
                    
                    try:
                        success = await self.vault.update_note(
                            path=note.path,
                            content=content,
                            mode=mode,
                            heading=heading
                        )
                        
                        if not success:
                            return [types.TextContent(type="text", text=f"Failed to update note: {title}")]
                            
                        # Get the updated note to show the changes
                        updated_note = await self.vault.get_note(note.path)
                        if not updated_note:
                            return [types.TextContent(type="text", text="Note was updated but couldn't be reloaded")]
                            
                        preview = updated_note.content[:200] + "..." if len(updated_note.content) > 200 else updated_note.content
                        return [types.TextContent(
                            type="text",
                            text=f"Successfully updated note: {title}\nPreview:\n{preview}"
                        )]
                        
                    except Exception as e:
                        print(f"Error updating note: {e}", file=sys.stderr)
                        return [types.TextContent(type="text", text=f"Error updating note: {str(e)}")]
                
                elif name == "scrape_website":
                    url = arguments.get("url")
                    note_name = arguments.get("name")  # Get the provided name
                    if not url or not note_name:
                        return [types.TextContent(type="text", text="URL and name are required")]
                    
                    try:
                        # Scrape the content
                        result = await self.scraper.search_and_scrape(url)
                        
                        # Use the provided name for the filename
                        sanitized_title = "".join(c for c in note_name if c.isalnum() or c in (' ', '-', '_')).strip()
                        if not sanitized_title:
                            sanitized_title = "scraped-content"
                        
                        # Create the note with updated metadata
                        note = await self.vault.create_note(
                            path=Path(f"{sanitized_title}.md"),
                            content=result['content'],
                            metadata={
                                "url": result.get('final_url', url),
                                "date_scraped": datetime.now().isoformat()
                            }
                        )
                        
                        if note:
                            return [types.TextContent(
                                type="text",
                                text=f"Successfully scraped and created note: {note.path}\n\n"
                                     f"Title: {result['title']}\n"
                                     f"URL: {result['url']}\n\n"
                                     f"Preview:\n{result['content'][:500]}..."
                            )]
                        return [types.TextContent(type="text", text="Failed to create note from scraped content")]
                            
                    except Exception as e:
                        print(f"Error scraping website: {e}", file=sys.stderr)
                        return [types.TextContent(type="text", text=f"Error scraping website: {str(e)}")]
                
                elif name == "create_memory":
                    memory = await self.memory_manager.create_memory(
                        title=arguments.get("title"),
                        content=arguments.get("content"),
                        memory_type=arguments.get("memory_type"),
                        categories=arguments.get("categories", []),
                        description=arguments.get("description"),
                        relationships=arguments.get("relationships", []),
                        tags=arguments.get("tags", [])
                    )
                    
                    if memory:
                        return [types.TextContent(
                            type="text",
                            text=f"Created memory: {memory['title']}\nPath: {memory['path']}\nMetadata: {memory['metadata']}"
                        )]
                    return [types.TextContent(type="text", text="Failed to create memory")]

                elif name == "search_memories":
                    query = arguments.get("query")
                    threshold = arguments.get("threshold", 60)
                    
                    memories = await self.memory_manager.search_relevant_memories(query, threshold)
                    
                    if not memories:
                        return [types.TextContent(type="text", text="No relevant memories found")]
                        
                    results = [f"Found {len(memories)} relevant memories:"]
                    for memory in memories:
                        results.append(
                            f"\nTitle: {memory['title']}\n"
                            f"Path: {memory['path']}\n"
                            f"Preview: {memory['preview']}\n"
                            f"{'='*50}"
                        )
                    
                    return [types.TextContent(type="text", text="\n".join(results))]

                elif name == "strengthen_relationship":
                    success = await self.memory_manager.strengthen_relationship(
                        source_path=Path(arguments.get("source")),
                        target_path=Path(arguments.get("target")),
                        predicate=arguments.get("predicate")
                    )
                    
                    return [types.TextContent(
                        type="text",
                        text="Successfully strengthened relationship" if success else "Failed to strengthen relationship"
                    )]

                else:
                    raise ValueError(f"Unknown tool: {name}")

            except Exception as e:
                print(f"Tool error: {str(e)}", file=sys.stderr)
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async def _perform_search(self, query: str, threshold: int) -> list[types.TextContent]:
        print(f"Performing search with query: {query} (threshold: {threshold})", file=sys.stderr)  # Added debug log
        results = []
        
        # Cache key includes query and threshold
        cache_key = f"{query}:{threshold}"
        
        async with self._cache_lock:
            if cache_key in self._search_cache:
                cache_time, results = self._search_cache[cache_key]
                if time.time() - cache_time < 300:  # 5 minute cache
                    return results

        try:
            notes = await self.vault.get_all_notes()
            
            # Process in parallel using asyncio.gather
            async def process_note(note):
                ratio = fuzz.partial_ratio(query.lower(), note.title.lower())
                if ratio >= threshold:
                    return types.TextContent(
                        type="text",
                        text=f"File: {note.path}\n"
                             f"Match Score: {ratio}\n"
                             f"Content:\n{note.content}\n"
                             f"{'='*50}\n"
                    )
                return None

            results = await asyncio.gather(*[process_note(note) for note in notes])
            results = [r for r in results if r is not None]
            results = results[:10] if results else [types.TextContent(type="text", text="No matches found")]
            
            # Cache results
            async with self._cache_lock:
                self._search_cache[cache_key] = (time.time(), results)
            
            return results
        except Exception as e:
            print(f"Search error: {str(e)}", file=sys.stderr)
            return [types.TextContent(type="text", text=f"Error during search: {str(e)}")]

    async def run(self) -> None:
        """
        Start the MCP server using stdio transport.
        """
        if not self._initialized:
            await self.setup()

        print("Starting server...", file=sys.stderr)
        try:
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                print("Server transport established", file=sys.stderr)
                # Initialize capabilities with required arguments
                capabilities = self.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="claudesidian",
                        server_version="0.1.0",
                        capabilities=capabilities
                    )
                )
        except Exception as e:
            print(f"Server error: {e}", file=sys.stderr)
            raise
        finally:
            self._shutdown = True
            await self.scraper.cleanup()  # Ensure scraper cleanup
            await self.vault.cleanup()  # Clean up all resources

def main() -> None:
    """
    Main entry point for the server.
    Handles command line arguments and starts the server.
    """
    print("Starting claudesidian MCP server...", file=sys.stderr)  # Added debug log
    
    if len(sys.argv) != 2:
        print("Usage: claudesidian <vault-path>", file=sys.stderr)  # Changed from claudesidian-mcp
        sys.exit(1)

    vault_path = Path(os.path.expanduser(sys.argv[1]))
    print(f"Using vault path: {vault_path}", file=sys.stderr)  # Added debug log
    
    if not vault_path.is_dir():
        print(f"Error: {vault_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    async def run_server():
        server = ClaudesidianServer(vault_path)
        await server.setup()  # Initialize async components
        await server.run()

    asyncio.run(run_server())

if __name__ == "__main__":
    main()