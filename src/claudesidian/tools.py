"""
Tool definitions for the Claudesidian MCP server.
Provides flexible note management capabilities through generic operations.
"""

from typing import List, Dict, Any, Optional, Sequence
from abc import ABC, abstractmethod
import mcp.types as types
from mcp.types import TextContent, ImageContent, EmbeddedResource, Tool
from datetime import datetime
import json
import os
from pathlib import Path

class ToolHandler(ABC):
    """Base class for tool handlers"""
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def get_tool_description(self) -> Tool:
        """Return tool description"""
        pass

    @abstractmethod
    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        """Execute the tool"""
        pass

# Base schema with flexible properties
NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string", 
            "description": "Note path or identifier"
        },
        "content": {
            "type": "string",
            "description": "Note content"
        },
        "metadata": {
            "type": "object",
            "description": "Flexible metadata key-value pairs",
            "additionalProperties": True
        }
    }
}

# Add memory-specific schema
MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Unique memory identifier"
        },
        "content": {
            "type": "string",
            "description": "Memory content"
        },
        "strength": {
            "type": "number",
            "description": "Memory strength (0.0 to 1.0)",
            "minimum": 0,
            "maximum": 1
        },
        "type": {
            "type": "string",
            "enum": ["core", "episodic", "semantic", "working"],
            "description": "Type of memory"
        },
        "metadata": {
            "type": "object",
            "description": "Memory metadata",
            "properties": {
                "created": {"type": "string", "format": "date-time"},
                "accessed": {"type": "string", "format": "date-time"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "relationships": {"type": "array", "items": {"type": "string"}},
                "context": {"type": "object", "additionalProperties": True}
            }
        }
    }
}

# Add scraping-specific schema
SCRAPING_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {
            "type": "string",
            "description": "URL to scrape"
        },
        "selectors": {
            "type": "object",
            "description": "CSS selectors to extract specific content",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "date": {"type": "string"},
                "author": {"type": "string"}
            }
        },
        "options": {
            "type": "object",
            "properties": {
                "wait_for": {"type": "string", "description": "Selector to wait for before scraping"},
                "timeout": {"type": "integer", "description": "Timeout in milliseconds", "default": 30000},
                "javascript": {"type": "boolean", "description": "Enable JavaScript", "default": True},
                "screenshots": {"type": "boolean", "description": "Capture screenshots", "default": False}
            }
        }
    },
    "required": ["url"]
}

# Define core tool operations
TOOL_DEFINITIONS = {
    "note": {
        "name": "note",
        "description": "Create, read, update or delete notes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "read", "update", "delete"],
                    "description": "Operation to perform"
                },
                "path": {
                    "type": "string",
                    "description": "Note path"
                },
                "content": {
                    "type": "string",
                    "description": "Note content for create/update"
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata",
                    "additionalProperties": True
                }
            },
            "required": ["action", "path"]
        }
    },

    "search": {
        "name": "search",
        "description": "Search notes with flexible criteria",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (natural language or structured)"
                },
                "filters": {
                    "type": "object",
                    "description": "Optional search filters",
                    "additionalProperties": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },

    "analyze": {
        "name": "analyze",
        "description": "Analyze notes and relationships",
        "inputSchema": {
            "type": "object", 
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Note path, folder, or tag to analyze"
                },
                "operation": {
                    "type": "string",
                    "description": "Analysis operation to perform"
                },
                "options": {
                    "type": "object",
                    "description": "Operation-specific options",
                    "additionalProperties": True
                }
            },
            "required": ["target", "operation"]
        }
    }
}

# Update tool definitions with memory operations
TOOL_DEFINITIONS.update({
    "memory": {
        "name": "memory",
        "description": "Manage memory operations in the vault",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["store", "retrieve", "reinforce", "forget", "associate"],
                    "description": "Memory operation to perform"
                },
                "id": {
                    "type": "string",
                    "description": "Memory identifier"
                },
                "content": {
                    "type": "string",
                    "description": "Memory content for store/update operations"
                },
                "type": {
                    "type": "string",
                    "enum": ["core", "episodic", "semantic", "working"],
                    "description": "Type of memory"
                },
                "strength": {
                    "type": "number",
                    "description": "Memory strength (0.0 to 1.0)"
                },
                "context": {
                    "type": "object",
                    "description": "Optional context information",
                    "additionalProperties": True
                }
            },
            "required": ["action"]
        }
    },

    "recall": {
        "name": "recall",
        "description": "Search and retrieve memories based on various criteria",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or memory pattern"
                },
                "type": {
                    "type": "string",
                    "enum": ["core", "episodic", "semantic", "working"],
                    "description": "Filter by memory type"
                },
                "min_strength": {
                    "type": "number",
                    "description": "Minimum memory strength",
                    "minimum": 0,
                    "maximum": 1
                },
                "context": {
                    "type": "object",
                    "description": "Context for contextual recall",
                    "additionalProperties": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of memories to recall",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    }
})

# Update tool definitions with scraping operations
TOOL_DEFINITIONS.update({
    "scrape": {
        "name": "scrape",
        "description": "Scrape web content and convert to notes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to scrape"
                },
                "mode": {
                    "type": "string",
                    "enum": ["auto", "article", "full"],
                    "description": "Scraping mode",
                    "default": "auto"
                },
                "selectors": {
                    "type": "object",
                    "description": "Optional CSS selectors for targeted scraping",
                    "additionalProperties": True
                },
                "options": {
                    "type": "object",
                    "description": "Additional scraping options",
                    "additionalProperties": True
                }
            },
            "required": ["url"]
        }
    },

    "extract-links": {
        "name": "extract-links",
        "description": "Extract and analyze links from web pages",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to analyze"
                },
                "depth": {
                    "type": "integer",
                    "description": "Link crawling depth",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 3
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "internal_only": {"type": "boolean", "default": True},
                        "exclude_patterns": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["url"]
        }
    },

    "monitor": {
        "name": "monitor",
        "description": "Monitor web pages for changes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "list", "check"],
                    "description": "Monitor operation to perform"
                },
                "url": {
                    "type": "string",
                    "description": "URL to monitor"
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for specific content"
                },
                "frequency": {
                    "type": "string",
                    "description": "Check frequency (e.g., '1h', '1d')"
                },
                "notify": {
                    "type": "boolean",
                    "description": "Enable notifications",
                    "default": True
                }
            },
            "required": ["action"]
        }
    }
})

def get_all_tools() -> List[types.Tool]:
    """Get all available tools with their definitions."""
    return [types.Tool(**tool_config) for tool_config in TOOL_DEFINITIONS.values()]

def create_tool_response(
    content: str | Dict[str, Any],
    metadata: Dict[str, Any] = None,
    is_error: bool = False
) -> List[Dict[str, Any]]:
    """Create a standardized tool response."""
    response = [{
        "type": "text",
        "text": content if isinstance(content, str) else json.dumps(content, indent=2),
        "isError": is_error
    }]
    
    if metadata:
        response.append({
            "type": "metadata",
            "data": metadata
        })
    
    return response

def create_memory_response(
    memory: Dict[str, Any],
    operation: str,
    success: bool = True
) -> List[Dict[str, Any]]:
    """Create a standardized memory operation response."""
    response = [{
        "type": "text",
        "text": f"Memory {operation} {'successful' if success else 'failed'}"
    }]
    
    if success and memory:
        response.append({
            "type": "memory",
            "data": memory
        })
        
    return response

def create_scraping_response(
    url: str,
    content: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
    screenshots: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Create a standardized scraping response."""
    response = [{
        "type": "text",
        "text": f"Content scraped from {url}:\n\n{json.dumps(content, indent=2)}"
    }]
    
    if metadata:
        response.append({
            "type": "metadata",
            "data": metadata
        })
        
    if screenshots:
        response.extend([{
            "type": "image",
            "data": screenshot,
            "mimeType": "image/png"
        } for screenshot in screenshots])
        
    return response

def validate_path(path: str) -> str:
    """Validate and normalize a path."""
    # Basic path sanitization
    invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
    path = ''.join(c if c not in invalid_chars else '-' for c in path)
    
    # Ensure .md extension for notes
    if not path.endswith('.md'):
        path += '.md'
        
    # Add special handling for memory paths
    if path.startswith('memories/'):
        parts = path.split('/')
        if len(parts) > 1 and parts[1] in ['core', 'episodic', 'semantic', 'working']:
            return path
            
    return path

def validate_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and normalize memory data."""
    if not memory.get('id'):
        memory['id'] = f"mem_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
    if 'strength' not in memory:
        memory['strength'] = 1.0
        
    if 'type' not in memory:
        memory['type'] = 'semantic'
        
    if 'metadata' not in memory:
        memory['metadata'] = {}
        
    memory['metadata'].update({
        'created': memory['metadata'].get('created', datetime.now().isoformat()),
        'accessed': datetime.now().isoformat()
    })
    
    return memory

def calculate_memory_path(memory: Dict[str, Any]) -> str:
    """Calculate the vault path for a memory."""
    memory_type = memory.get('type', 'semantic')
    timestamp = datetime.fromisoformat(memory['metadata']['created']).strftime('%Y/%m')
    return f"memories/{memory_type}/{timestamp}/{memory['id']}.md"

def normalize_url(url: str) -> str:
    """Normalize and validate a URL."""
    if not url.startswith(('http://', 'https://')):
        url = f"https://{url}"
    return url

def sanitize_filename(url: str) -> str:
    """Convert URL to safe filename."""
    # Remove protocol and special characters
    filename = url.split('://')[-1]
    invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    filename = ''.join(c if c not in invalid_chars else '-' for c in filename)
    return filename[:200]  # Limit length

def calculate_scrape_path(url: str, timestamp: Optional[str] = None) -> str:
    """Calculate the vault path for scraped content."""
    if not timestamp:
        timestamp = datetime.now().strftime('%Y/%m')
    filename = sanitize_filename(url)
    return f"web/{timestamp}/{filename}.md"

class ListFilesInVaultToolHandler(ToolHandler):
    def run_tool(self, args: dict) -> Sequence[TextContent]:
        vault = Path(os.getenv("VAULT_PATH"))
        files = []
        
        for path in vault.rglob("*"):
            if path.is_file():
                files.append(str(path.relative_to(vault)))
                
        return [
            TextContent(
                type="text",
                text=json.dumps(files, indent=2)
            )
        ]

# ... similarly update other tool handlers to use direct file access ...