"""
Configuration management for Claudesidian.
Handles loading and validating configuration from files and environment.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field
import traceback
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

@dataclass
class ServerConfig:
    """MCP server-specific configuration."""
    name: str = "claudesidian"
    version: str = "0.1.0"
    capabilities: Dict[str, Any] = field(default_factory=lambda: {
        "tools": {},
        "resources": {},
        "prompts": {}
    })

@dataclass
class Config:
    """Configuration settings for Claudesidian."""
    
    # Required settings
    vault_path: Path
    server: ServerConfig = field(default_factory=ServerConfig)
    
    # Optional settings with defaults
    daily_notes_folder: Optional[str] = None
    attachment_folder: str = "attachments"
    screenshot_folder: str = "screenshots"
    
    # Memory settings
    memory_decay_rate: float = 0.1
    memory_strength_threshold: float = 0.3
    max_memory_age_days: int = 365
    
    # Path resolution settings
    path_cache_ttl: int = 300
    min_path_confidence: float = 0.3
    
    # Web scraping settings
    max_scrape_size: int = 1024 * 1024  # 1MB
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> 'Config':
        """Load configuration from file and/or environment variables."""
        try:
            # Check environment variable first
            vault_path_env = os.getenv('VAULT_PATH')
            logger.info(f"VAULT_PATH from environment: {vault_path_env}")
            
            if vault_path_env:
                # Normalize Windows path
                vault_path = Path(vault_path_env.replace('"', ''))
                logger.info(f"Normalized vault path: {vault_path}")
                
                # Validate path
                if not vault_path.exists():
                    raise ValueError(f"Vault path does not exist: {vault_path}")
                if not vault_path.is_dir():
                    raise ValueError(f"Vault path is not a directory: {vault_path}")
                
                logger.info(f"Validated vault path: {vault_path}")
                return cls(vault_path=vault_path)
            
            # If no environment variable, try config files
            config_file = cls._get_config_file(config_path)
            if config_file:
                logger.info(f"Loading config from file: {config_file}")
                config_data = cls._load_config_data(config_file)
            else:
                logger.warning("No config file found")
                config_data = {}
            
            # Get and validate vault path from config
            vault_path = cls._get_vault_path(config_data)
            
            # Create config instance
            config = cls(vault_path=vault_path)
            
            # Update with any additional config data
            config._update_from_dict(config_data)
            
            return config
            
        except Exception as e:
            logger.error(
                "Configuration error:\n" + 
                ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            )
            raise
    
    @staticmethod
    def _get_config_file(config_path: Optional[str]) -> Optional[Path]:
        """Get configuration file path."""
        default_locations = [
            Path.cwd() / "claudesidian.json",
            Path.home() / ".config" / "claudesidian" / "config.json",
            Path.home() / ".claudesidian.json",
            Path.home() / "AppData/Roaming/Claude/claude_desktop_config.json"
        ]
        
        if config_path:
            return Path(config_path)
            
        for loc in default_locations:
            if loc.exists():
                logger.debug(f"Checking config location: {loc}")
                return loc
        return None
    
    @staticmethod
    def _load_config_data(config_file: Optional[Path]) -> Dict[str, Any]:
        """Load configuration data from file."""
        config_data = {}
        
        if config_file:
            try:
                with open(config_file) as f:
                    data = json.load(f)
                    logger.debug(f"Loaded JSON data: {data}")
                    
                # Handle Claude Desktop config structure
                if 'mcpServers' in data and 'claudesidian' in data['mcpServers']:
                    server_config = data['mcpServers']['claudesidian']
                    logger.info(f"Found Claude Desktop server config: {server_config}")
                    if 'env' in server_config:
                        config_data.update(server_config['env'])
                    if 'args' in server_config:
                        config_data['server_args'] = server_config['args']
                else:
                    config_data = data
                    
                logger.info(f"Loaded config from {config_file}")
            except Exception as e:
                logger.warning(f"Error loading config file: {e}")
                
        return config_data
    
    @staticmethod
    def _get_vault_path(config_data: Dict[str, Any]) -> Path:
        """Get and validate vault path."""
        vault_path = config_data.get('vault_path')
        
        if not vault_path:
            raise ValueError(
                "Vault path must be provided in config file or VAULT_PATH environment variable"
            )
            
        vault_path = Path(vault_path).expanduser().resolve()
        logger.info(f"Resolved vault path: {vault_path}")
        
        if not vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")
        if not vault_path.is_dir():
            raise ValueError(f"Vault path is not a directory: {vault_path}")
            
        return vault_path
    
    def _update_from_dict(self, config_data: Dict[str, Any]) -> None:
        """Update config from dictionary data."""
        for key, value in config_data.items():
            if hasattr(self, key):
                if key.endswith('_path') and isinstance(value, str):
                    value = Path(value)
                setattr(self, key, value)
                logger.debug(f"Updated config {key}: {value}")
    
    def save(self, config_path: Optional[str] = None) -> None:
        """Save current configuration to file."""
        if not config_path:
            config_path = str(Path.home() / ".claudesidian.json")
            
        # Convert to dictionary and handle Path objects
        config_dict = asdict(self)
        config_dict['vault_path'] = str(config_dict['vault_path'])
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
            
        logger.info(f"Saved config to {config_path}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        config_dict = asdict(self)
        config_dict['vault_path'] = str(config_dict['vault_path'])
        return config_dict

    def __str__(self) -> str:
        """String representation of config."""
        return f"Config(vault_path={self.vault_path})"