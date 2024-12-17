"""
Claudesidian: An MCP server for integrating Obsidian with Claude.
Provides vault management, web scraping, and memory capabilities.
"""

from pathlib import Path
from typing import Optional

from claudesidian.server import ClaudesidianServer
from claudesidian.config import Config

__version__ = "0.1.0"

def create_server(
    vault_path: Optional[str] = None,
    config_path: Optional[str] = None
) -> ClaudesidianServer:
    """Create and configure a Claudesidian server instance."""
    config = Config.load(config_path)
    
    if vault_path:
        config.vault_path = Path(vault_path)
        
    return ClaudesidianServer(config)

# Export main components
__all__ = ['ClaudesidianServer', 'Config', 'create_server']