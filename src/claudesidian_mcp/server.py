# server.py

"""
MCP server for Obsidian vault interaction with fuzzy search capabilities.
"""

import asyncio
import os
import sys
import locale
import time
import re
import hashlib
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from pydantic import BaseModel
from rapidfuzz import fuzz, process

from .vault import VaultManager
from .scraper import RobustScraper
from .memory import MemoryManager
from .reasoning import ReasoningManager
from .tools import create_tools_registry, Tool  # Update import
from .search import SearchEngine  # Add SearchEngine import

# Ensure UTF-8 encoding on all platforms
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr.reconfigure(encoding='utf-8')

# Try to set locale to UTF-8 if possible
try:
    if sys.platform.startswith('win'):
        locale.setlocale(locale.LC_ALL, '.UTF-8')
    else:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except locale.Error:
    locale.setlocale(locale.LC_ALL, '')
    print("Warning: Could not set UTF-8 locale", file=sys.stderr)

class AnyNotification(BaseModel):
    method: str
    params: Optional[Dict[str, Any]] = None

class ClaudesidianServer:
    """
    Main server class that handles MCP protocol implementation and tool registration.
    Adjusted to start interactions with reasoning and end with memory storage.
    """
    
    def __init__(self, vault_path: Path):
        """
        Initialize the server with a path to the Obsidian vault.
        
        Args:
            vault_path (Path): Path to the Obsidian vault directory
        """
        self.vault_path = vault_path
        self.vault = VaultManager(vault_path)  # Initialize VaultManager
        self.server = Server("claudesidian")  # Initialize MCP Server
        self.scraper = RobustScraper()  # Initialize Scraper
        self.memory_manager = MemoryManager(self.vault)  # Initialize MemoryManager
        self.reasoning_manager = ReasoningManager(self.vault)  # Initialize ReasoningManager
        self._search_cache = {}
        self._cache_lock = asyncio.Lock()
        self._initializing = False
        self._initialized = False
        self._shutdown = False

    async def _initialize_folder_structure(self):
        """Initialize the basic folder structure and index file."""
        print("Initializing folder structure...", file=sys.stderr)
        
        # Create base claudesidian folder
        claudesidian_folder = self.vault_path / "claudesidian"
        await self.vault.ensure_folder(claudesidian_folder)

        # Create all required folders
        folders = {
            "memory": claudesidian_folder / "memory",
            "reasoning": claudesidian_folder / "reasoning",
            "websites": claudesidian_folder / "websites",
            "relationships": claudesidian_folder / "relationships"  # Add relationships folder
        }
        
        for folder_path in folders.values():
            await self.vault.ensure_folder(folder_path)

        # Create or update single index file
        index_path = claudesidian_folder / "index.md"
        if not index_path.exists():
            index_content = """# Claudesidian Index

## Memories

## Reasoning

## Websites

## Relationships
"""
            index_path.write_text(index_content, encoding='utf-8')

        print("Folder structure initialized", file=sys.stderr)

    async def setup(self):
        """Initialize all async components"""
        if self._initializing or self._initialized:
            return
        
        self._initializing = True
        try:
            print("Initializing server components...", file=sys.stderr)
            await self._initialize_folder_structure()
            await self.scraper.setup()
            print("Initializing search engine...", file=sys.stderr)
            self.search_engine = SearchEngine(self.vault)
            await self.search_engine.build_index()
            print("Server initialization complete", file=sys.stderr)
        except Exception as e:
            print(f"Error during setup: {e}", file=sys.stderr)
        finally:
            self._initializing = False
        self._initialized = True
        return self

    def _setup_tools(self, dependencies: Dict[str, Any]) -> None:
        """Register all available tools with the MCP server using the tools registry."""
        print("Setting up tools...", file=sys.stderr)
        
        # Ensure scraper is available in dependencies
        dependencies["scraper"] = self.scraper
        dependencies["search_engine"] = self.search_engine
        
        tools = create_tools_registry(self.vault, self.memory_manager, self.reasoning_manager)

        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            print("Listing tools...", file=sys.stderr)
            return [
                types.Tool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.input_schema
                )
                for tool in tools
            ]

        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> List[types.TextContent]:
            if not arguments:
                raise ValueError("Arguments required")
            
            try:
                tool = next((t for t in tools if t.name == name), None)
                if not tool:
                    error_msg = f"Unknown tool: {name}"
                    print(f"[Server] {error_msg}", file=sys.stderr)
                    return [types.TextContent(type="text", text=error_msg)]
                
                print(f"[Server] Executing tool: {name}", file=sys.stderr)
                results = await tool.handler(arguments, dependencies)
                if not results:
                    error_msg = f"Tool {name} returned no results"
                    print(f"[Server] {error_msg}", file=sys.stderr)
                    return [types.TextContent(type="text", text=error_msg)]
                    
                return results
            
            except Exception as e:
                error_msg = f"Error executing {name}: {str(e)}"
                print(f"[Server] {error_msg}", file=sys.stderr)
                return [types.TextContent(type="text", text=error_msg)]

    async def _perform_search(self, query: str, threshold: int) -> List[types.TextContent]:
        """Perform a fuzzy search using the indexed SearchEngine."""
        print(f"Performing search with query: {query} (threshold: {threshold})", file=sys.stderr)
        
        try:
            search_results = await self.search_engine.search(
                query, 
                threshold=threshold,
                max_results=10,
                search_contents=True
            )
            
            if not search_results:
                return [types.TextContent(type="text", text="No matches found.")]
            
            results = []
            for res in search_results:
                results.append(
                    types.TextContent(
                        type="text",
                        text=f"File: {res.file_path}\n"
                             f"Match Score: {res.score}\n"
                             f"Content:\n{res.preview}\n"
                             f"{'='*50}\n"
                    )
                )
            return results
            
        except Exception as e:
            print(f"Search error: {str(e)}", file=sys.stderr)
            return [types.TextContent(type="text", text=f"Error during search: {str(e)}")]

    async def run(self) -> None:
        """
        Start the MCP server using stdio transport.
        Adjusted to work without MoC and sessions.
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
                # Prepare shared dependencies
                dependencies = {
                    "vault": self.vault,
                    "memory_manager": self.memory_manager,
                    "reasoning_manager": self.reasoning_manager,
                    "scraper": self.scraper,
                }
                # Register tools with dependencies
                self._setup_tools(dependencies)
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

def resolve_vault_path(path_str: str) -> Path:
    """Resolve and validate the vault path."""
    try:
        # Expand user home directory and environment variables
        expanded_path = os.path.expandvars(os.path.expanduser(path_str))
        path = Path(expanded_path).resolve()
        
        if not path.exists():
            print(f"Error: Vault path does not exist: {path}", file=sys.stderr)
            sys.exit(1)
        if not path.is_dir():
            print(f"Error: Vault path is not a directory: {path}", file=sys.stderr)
            sys.exit(1)
            
        return path
    except Exception as e:
        print(f"Error resolving vault path: {e}", file=sys.stderr)
        sys.exit(1)

def get_version():
    """Get the package version."""
    try:
        from importlib.metadata import version
        return version("claudesidian")
    except Exception:
        return "unknown"

def main() -> None:
    """
    Main entry point for the server.
    Handles command line arguments and starts the server.
    """
    parser = argparse.ArgumentParser(description="Claudesidian MCP server for Obsidian vault interaction")
    parser.add_argument('vault_path', nargs='?', help='Path to Obsidian vault')
    parser.add_argument('--version', action='store_true', help='Show version number and exit')
    args = parser.parse_args()

    if args.version:
        print(f"Claudesidian version {get_version()}")
        sys.exit(0)

    if not args.vault_path:
        parser.print_help()
        sys.exit(1)

    print(f"Starting Claudesidian v{get_version()}...", file=sys.stderr)
    
    vault_path = resolve_vault_path(args.vault_path)
    print(f"Using vault path: {vault_path}", file=sys.stderr)

    async def run_server():
        server = ClaudesidianServer(vault_path)
        try:
            await server.setup()
            await server.run()
        except Exception as e:
            print(f"Server error: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        sys.exit(0)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
