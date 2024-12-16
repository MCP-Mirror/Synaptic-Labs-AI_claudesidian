# File: claudesidian/core/vault.py

"""
Vault management for Claudesidian.
Handles vault operations, cache management, and file system events.
"""

import os
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable, Any
from datetime import datetime
import asyncio
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from . import VaultConfig, VaultError, VaultConfigError
from ..utils.path_resolver import PathResolver

logger = logging.getLogger(__name__)

class VaultEventHandler(FileSystemEventHandler):
    """Handles file system events in the vault."""
    
    def __init__(self, vault_manager: 'VaultManager'):
        self.vm = vault_manager
        
    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.md'):
            asyncio.create_task(self.vm.handle_note_modified(Path(event.src_path)))
            
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.md'):
            asyncio.create_task(self.vm.handle_note_created(Path(event.src_path)))
            
    def on_deleted(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith('.md'):
            asyncio.create_task(self.vm.handle_note_deleted(Path(event.src_path)))

class VaultManager:
    """
    Manages an Obsidian vault, handling configuration, events, and operations.
    """
    
    DEFAULT_CONFIG = {
        "attachments_path": "attachments",
        "daily_notes_path": "Daily Notes",
        "templates_path": "templates"
    }
    
    def __init__(self, vault_path: Path, path_resolver: Optional[PathResolver] = None):
        """
        Initialize vault manager.
        
        Args:
            vault_path: Path to Obsidian vault
            path_resolver: Optional PathResolver instance
        """
        self.vault_path = Path(vault_path).resolve()
        self.path_resolver = path_resolver or PathResolver(self.vault_path)
        
        # Internal state
        self._config: Optional[VaultConfig] = None
        self._observer: Optional[Observer] = None
        self._event_handlers: Dict[str, Set[Callable]] = {
            'note_modified': set(),
            'note_created': set(),
            'note_deleted': set(),
            'config_changed': set()
        }
        self._cache: Dict[str, Any] = {}
        
    async def initialize(self) -> None:
        """Initialize the vault manager."""
        # Validate vault
        if not self.vault_path.exists():
            raise VaultError(f"Vault path does not exist: {self.vault_path}")
        if not self.vault_path.is_dir():
            raise VaultError(f"Vault path is not a directory: {self.vault_path}")
            
        # Load config
        await self.load_config()
        
        # Setup file watching
        await self.start_file_watcher()
        
        logger.info(f"Initialized vault at {self.vault_path}")
        
    async def load_config(self) -> VaultConfig:
        """
        Load vault configuration.
        
        Returns:
            VaultConfig object
        """
        config_path = self.vault_path / '.obsidian' / 'app.json'
        
        try:
            if config_path.exists():
                with open(config_path) as f:
                    config_data = json.load(f)
            else:
                config_data = {}
                
            # Merge with defaults
            self._config = {**self.DEFAULT_CONFIG, **config_data}
            
            return self._config
            
        except Exception as e:
            raise VaultConfigError(f"Error loading vault config: {e}")
            
    async def save_config(self) -> None:
        """Save current configuration to disk."""
        if not self._config:
            return
            
        config_path = self.vault_path / '.obsidian' / 'app.json'
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
        except Exception as e:
            raise VaultConfigError(f"Error saving vault config: {e}")
            
    async def start_file_watcher(self) -> None:
        """Start watching vault for file changes."""
        if self._observer:
            return
            
        self._observer = Observer()
        handler = VaultEventHandler(self)
        self._observer.schedule(handler, str(self.vault_path), recursive=True)
        self._observer.start()
        
        logger.info("Started vault file watcher")
        
    async def stop_file_watcher(self) -> None:
        """Stop watching vault for file changes."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            
    async def get_all_notes(self) -> List[Path]:
        """
        Get paths to all markdown notes in the vault.
        
        Returns:
            List of paths to markdown files
        """
        notes = []
        for path in self.vault_path.rglob("*.md"):
            # Skip files in hidden directories
            if not any(part.startswith('.') for part in path.parts):
                notes.append(path.relative_to(self.vault_path))
        return notes
        
    async def get_attachments(self) -> List[Path]:
        """
        Get paths to all attachments in the vault.
        
        Returns:
            List of paths to attachment files
        """
        attachments_dir = self.vault_path / self._config["attachments_path"]
        if not attachments_dir.exists():
            return []
            
        return list(attachments_dir.rglob("*.*"))
        
    async def create_note(self, path: Path, content: str = "") -> None:
        """
        Create a new note at the specified path.
        
        Args:
            path: Path for new note
            content: Optional initial content
        """
        full_path = self.vault_path / path
        
        # Ensure parent directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
    async def delete_note(self, path: Path) -> None:
        """
        Delete a note.
        
        Args:
            path: Path to note to delete
        """
        full_path = self.vault_path / path
        if full_path.exists():
            full_path.unlink()
            
    async def move_note(self, source: Path, destination: Path) -> None:
        """
        Move/rename a note.
        
        Args:
            source: Current note path
            destination: New note path
        """
        src_path = self.vault_path / source
        dst_path = self.vault_path / destination
        
        # Ensure parent directory exists
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file
        shutil.move(str(src_path), str(dst_path))
        
    async def backup_vault(self, backup_path: Path) -> None:
        """
        Create a backup of the vault.
        
        Args:
            backup_path: Where to store the backup
        """
        # Ensure backup directory exists
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup name with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"vault_backup_{timestamp}"
        backup_file = backup_path / f"{backup_name}.zip"
        
        # Create zip backup
        shutil.make_archive(
            str(backup_path / backup_name),
            'zip',
            str(self.vault_path)
        )
        
        logger.info(f"Created vault backup at {backup_file}")
        
    # Event handling
    async def handle_note_modified(self, path: Path) -> None:
        """Handle note modification event."""
        for handler in self._event_handlers['note_modified']:
            await handler(path)
            
    async def handle_note_created(self, path: Path) -> None:
        """Handle note creation event."""
        for handler in self._event_handlers['note_created']:
            await handler(path)
            
    async def handle_note_deleted(self, path: Path) -> None:
        """Handle note deletion event."""
        for handler in self._event_handlers['note_deleted']:
            await handler(path)
            
    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler."""
        if event in self._event_handlers:
            self._event_handlers[event].add(handler)
            
    def off(self, event: str, handler: Callable) -> None:
        """Unregister an event handler."""
        if event in self._event_handlers:
            self._event_handlers[event].discard(handler)
            
    async def close(self) -> None:
        """Clean up resources."""
        await self.stop_file_watcher()
        self._event_handlers.clear()