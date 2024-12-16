# File: claudesidian/tools.py

"""
Tool definitions for the Claudesidian MCP server.
Each tool includes comprehensive documentation, examples, and context rules.
"""

from typing import List
import mcp.types as types

VAULT_TOOLS = [
    {
        "name": "update_daily_note",
        "description": """
        Update or create a daily note with new content.
        
        The system will:
        1. Automatically find your daily notes folder
        2. Create today's note if it doesn't exist
        3. Add the content in the specified way
        
        Context Rules:
        - Searches for common daily notes folder patterns
        - Remembers last used daily notes location
        - Creates consistent file names (YYYY-MM-DD.md)
        
        Examples:
        - "Add 'Started working on project X' to my daily notes"
        - "Create todo list in today's note"
        """,
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content to add"
                },
                "position": {
                    "type": "string",
                    "enum": ["append", "prepend", "replace"],
                    "default": "append",
                    "description": "Where to add the content"
                },
                "section": {
                    "type": "string",
                    "description": "Optional section heading to add under"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "smart_create_note",
        "description": """
        Intelligently create a note in the most appropriate location.
        
        The system will:
        1. Analyze note content and title
        2. Find similar notes
        3. Suggest appropriate location
        4. Create note with proper frontmatter
        
        Context Rules:
        - Uses existing folder structure patterns
        - Considers note relationships
        - Maintains consistent naming
        
        Examples:
        - "Create note about Python programming"
        - "Make new project page for ClaudeSidian"
        """,
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Note title"
                },
                "content": {
                    "type": "string",
                    "description": "Note content"
                },
                "type": {
                    "type": "string",
                    "description": "Optional note type (project, concept, etc.)"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags"
                }
            },
            "required": ["title", "content"]
        }
    }
]

WEB_TOOLS = [
    {
        "name": "smart_web_capture",
        "description": """
        Intelligently capture web content and organize it in your vault.
        
        The system will:
        1. Scrape the content
        2. Extract key information
        3. Generate appropriate frontmatter
        4. Place in optimal location
        5. Create/update relevant MOCs
        
        Context Rules:
        - Categorizes content type (article, documentation, etc.)
        - Maintains source attribution
        - Creates meaningful connections
        
        Examples:
        - "Save this programming tutorial"
        - "Capture blog post about productivity"
        """,
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to capture"
                },
                "custom_title": {
                    "type": "string",
                    "description": "Optional custom title"
                },
                "folder_hint": {
                    "type": "string",
                    "description": "Optional hint about desired location"
                }
            },
            "required": ["url"]
        }
    }
]

MEMORY_TOOLS = [
    {
        "name": "remember",
        "description": """
        Create a memory with intelligent categorization and connections.
        
        The system will:
        1. Analyze the memory content
        2. Determine appropriate memory type
        3. Extract and create relationships
        4. Update knowledge graph
        
        Context Rules:
        - Categorizes memory type automatically
        - Maintains relationship strength
        - Updates related memories
        
        Examples:
        - "Remember that I prefer working out in the morning"
        - "Note that Project X is related to concept Y"
        """,
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Memory content"
                },
                "type_hint": {
                    "type": "string",
                    "enum": ["core", "episodic", "semantic"],
                    "description": "Optional memory type hint"
                },
                "importance": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Optional importance score"
                }
            },
            "required": ["content"]
        }
    }
]

def get_all_tools() -> List[types.Tool]:
    """Get all available tools with their definitions."""
    all_tools = [*VAULT_TOOLS, *WEB_TOOLS, *MEMORY_TOOLS]
    return [types.Tool(**tool) for tool in all_tools]