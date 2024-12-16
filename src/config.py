# File: claudesidian/config.py

"""
Configuration management for Claudesidian.
Handles loading and validating configuration from files and environment.
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class Config:
    """Configuration settings for Claudesidian."""
    
    # Vault settings
    vault_path: Path
    daily_notes_folder: Optional[str] = None
    attachment_folder: str = "attachments"
    
    # Web scraping settings
    max_scrape_size: int = 1024 * 1024  # 1MB
    screenshot_folder: str = "screenshots"
    
    # Memory settings
    memory_decay_rate: float = 0.1
    memory_strength_threshold: float = 0.3
    max_memory_age_days: int = 365
    
    # Path resolution settings
    path_cache_ttl: int = 300  # 5 minutes
    min_path_confidence: float = 0.3
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> 'Config':
        """
        Load configuration from file and/or environment variables.
        
        Args:
            config_path: Optional path to config file. If not provided,
                        will look in default locations.
        
        Returns:
            Config instance with loaded settings
        
        Raises:
            ValueError: If required settings are missing
        """
        # Default config locations
        default_locations = [
            Path.cwd() / "claudesidian.json",
            Path.home() / ".config" / "claudesidian" / "config.json",
            Path.home() / ".claudesidian.json"
        ]
        
        # Load from file
        config_data: Dict[str, Any] = {}
        config_file: Optional[Path] = None
        
        if config_path:
            config_file = Path(config_path)
        else:
            for loc in default_locations:
                if loc.exists():
                    config_file = loc
                    break
                    
        if config_file:
            try:
                with open(config_file) as f:
                    config_data = json.load(f)
                logger.info(f"Loaded config from {config_file}")
            except Exception as e:
                logger.warning(f"Error loading config file: {e}")
        
        # Load from environment
        env_prefix = "CLAUDESIDIAN_"
        for key, value in os.environ.items():
            if key.startswith(env_prefix):
                config_key = key[len(env_prefix):].lower()
                config_data[config_key] = value
        
        # Get required vault path
        vault_path = config_data.get('vault_path') or os.getenv('CLAUDESIDIAN_VAULT_PATH')
        if not vault_path:
            raise ValueError(
                "Vault path must be provided in config file or CLAUDESIDIAN_VAULT_PATH environment variable"
            )
        
        # Convert path strings to Path objects
        vault_path = Path(vault_path).expanduser().resolve()
        
        # Validate vault path
        if not vault_path.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")
        if not vault_path.is_dir():
            raise ValueError(f"Vault path is not a directory: {vault_path}")
        
        # Create with defaults, overridden by config
        return cls(
            vault_path=vault_path,
            daily_notes_folder=config_data.get('daily_notes_folder'),
            attachment_folder=config_data.get('attachment_folder', 'attachments'),
            max_scrape_size=int(config_data.get('max_scrape_size', 1024 * 1024)),
            screenshot_folder=config_data.get('screenshot_folder', 'screenshots'),
            memory_decay_rate=float(config_data.get('memory_decay_rate', 0.1)),
            memory_strength_threshold=float(config_data.get('memory_strength_threshold', 0.3)),
            max_memory_age_days=int(config_data.get('max_memory_age_days', 365)),
            path_cache_ttl=int(config_data.get('path_cache_ttl', 300)),
            min_path_confidence=float(config_data.get('min_path_confidence', 0.3))
        )
    
    def save(self, config_path: Optional[str] = None) -> None:
        """
        Save current configuration to file.
        
        Args:
            config_path: Optional path to save config file. If not provided,
                        will save to first default location.
        """
        if not config_path:
            config_path = str(Path.home() / ".claudesidian.json")
            
        # Convert Path objects to strings
        config_dict = asdict(self)
        config_dict['vault_path'] = str(config_dict['vault_path'])
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
            
        logger.info(f"Saved config to {config_path}")
    
    def update(self, **kwargs) -> None:
        """
        Update configuration settings.
        
        Args:
            **kwargs: Settings to update
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                # Convert string paths to Path objects
                if key.endswith('_path') and isinstance(value, str):
                    value = Path(value)
                setattr(self, key, value)
            else:
                logger.warning(f"Unknown config setting: {key}")