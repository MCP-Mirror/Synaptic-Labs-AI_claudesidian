#!/usr/bin/env python3
"""
MCP server for Obsidian vault interaction with fuzzy search capabilities.
"""
import asyncio
import os
import sys
import locale
from pathlib import Path
from typing import Optional, Dict, Any
from fuzzywuzzy import fuzz
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from .vault import VaultManager
from pydantic import BaseModel

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
        self._setup_tools()  # Remove notification setup call

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
                
                else:
                    raise ValueError(f"Unknown tool: {name}")

            except Exception as e:
                print(f"Tool error: {str(e)}", file=sys.stderr)
                return [types.TextContent(type="text", text=f"Error: {str(e)}")]

    async def _perform_search(self, query: str, threshold: int) -> list[types.TextContent]:
        print(f"Performing search with query: {query} (threshold: {threshold})", file=sys.stderr)  # Added debug log
        results = []
        
        # Get notes in batches for better performance
        try:
            notes = await self.vault.get_all_notes()
            
            for note in notes:
                ratio = fuzz.partial_ratio(query.lower(), note.title.lower())
                if ratio >= threshold:
                    results.append(types.TextContent(
                        type="text",
                        text=f"File: {note.path}\n"
                             f"Match Score: {ratio}\n"
                             f"Content:\n{note.content}\n"
                             f"{'='*50}\n"
                    ))

            return results[:10] if results else [types.TextContent(type="text", text="No matches found")]

        except Exception as e:
            print(f"Search error: {str(e)}", file=sys.stderr)
            return [types.TextContent(type="text", text=f"Error during search: {str(e)}")]

    async def run(self) -> None:
        """
        Start the MCP server using stdio transport.
        """
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

    server = ClaudesidianServer(vault_path)
    asyncio.run(server.run())

if __name__ == "__main__":
    main()