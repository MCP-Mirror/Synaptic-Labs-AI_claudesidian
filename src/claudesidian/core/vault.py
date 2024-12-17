# File: claudesidian/core/vault.py

"""
Vault management for Claudesidian.
Handles vault operations, cache management, and file system events.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Callable, Any, Union, ForwardRef, Tuple  # Added Tuple
from datetime import datetime
import asyncio
import logging
import yaml
from functools import lru_cache
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import mcp.types as types  # Add this import
from urllib.parse import quote, urlparse  # Add this import
import re
import unicodedata

from .types import (
    VaultConfig,
    VaultError,
    VaultConfigError,
    NoteNotFoundError
)
from ..utils.path_resolver import PathResolver  # Fix the import path

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
        self.path_resolver = path_resolver or PathResolver(str(self.vault_path))
        
        # Internal state
        self._config: Union[VaultConfig, None] = None
        self._observer: Optional[Observer] = None
        self._event_handlers: Dict[str, Set[Callable]] = {
            'note_modified': set(),
            'note_created': set(),
            'note_deleted': set(),
            'config_changed': set()
        }
        self._cache: Dict[str, Any] = {}
        self._note_lock = asyncio.Lock()
        
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
        
    @lru_cache(maxsize=100)
    async def get_note(self, path: Path) -> str:
        """Get note content with caching."""
        full_path = self.vault_path / path
        if not full_path.exists():
            raise NoteNotFoundError(f"Note not found: {path}")
            
        async with self._note_lock:  # Add lock for thread safety
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
                
    async def create_note(self, path: Path, content: str = "", **metadata) -> None:
        """
        Create a new note with metadata.
        
        Args:
            path: Path for new note
            content: Optional initial content
            metadata: Optional metadata for the note
        """
        try:
            full_path = self.vault_path / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Add frontmatter if metadata provided
            if metadata:
                content = f"---\n{yaml.dump(metadata)}---\n\n{content}"
                
            async with self._note_lock:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                    
            # Clear cache for this path
            self.get_note.cache_clear()
            
        except Exception as e:
            logger.error(f"Failed to create note {path}: {e}")
            raise
            
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

    async def list_resources(self) -> List[types.Resource]:
        """List available resources in the vault."""
        resources = []
        
        try:
            # Recursively find all files in vault
            for file_path in self.vault_path.rglob("*"):
                if file_path.is_file():
                    # Get path relative to vault root
                    rel_path = file_path.relative_to(self.vault_path)
                    
                    # Create resource URI using file:// scheme
                    uri = self._sanitize_path_for_uri(str(rel_path))
                    
                    # Determine MIME type based on extension
                    mime_type = self._get_mime_type(file_path)
                    
                    resources.append(types.Resource(
                        uri=uri,
                        name=file_path.name,
                        mimeType=mime_type
                    ))
                    
            return resources
            
        except Exception as e:
            logger.error(f"Error listing vault resources: {e}")
            raise

    async def read_resource(self, uri: str) -> types.ResourceContents:  # Changed from ResourceContent to ResourceContents
        """Read content of a specific resource."""
        try:
            # Strip file:// scheme and decode path
            if uri.startswith("file://"):
                path = uri[7:]
                
            # Decode the path components
            decoded_parts = [
                self._decode_path_component(part) 
                for part in path.split('/')
            ]
            path = '/'.join(decoded_parts)
            
            # Resolve full path 
            full_path = self.vault_path / path
            
            if not full_path.exists():
                raise FileNotFoundError(f"Resource not found: {uri}")
                
            # Read file content
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            return types.ResourceContents(  # Changed from ResourceContent to ResourceContents
                uri=uri,
                text=content,
                mimeType=self._get_mime_type(full_path)
            )
            
        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            raise

    def _get_mime_type(self, path: Path) -> str:
        """Determine MIME type based on file extension."""
        ext = path.suffix.lower()
        
        mime_types = {
            '.md': 'text/markdown',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.yaml': 'application/x-yaml',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg', 
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.pdf': 'application/pdf'
        }
        
        return mime_types.get(ext, 'application/octet-stream')

    def _sanitize_path_for_uri(self, path: str) -> str:
        """Convert a filesystem path to a valid URI."""
        try:
            # Replace backslashes with forward slashes
            path = path.replace('\\', '/')
            
            # Split and encode each component
            components = [self._encode_path_component(p) for p in path.split('/') if p]
            
            # Join with forward slashes and add file:// prefix
            return 'file://' + '/'.join(components)
            
        except Exception as e:
            logger.error(f"Error creating URI from path '{path}': {e}")
            # Fallback to basic sanitization
            simple_path = re.sub(r'[^\w/-]', '-', path.replace('\\', '/'))
            return f"file://{simple_path}"

    def _replace_emoji(self, text: str) -> str:
        """Replace emoji and special characters with text equivalents."""
        # Common emoji mappings
        emoji_map = {
            '📝': 'note',
            '📖': 'book',
            '📚': 'books',
            '🗂️': 'folder',
            '📁': 'folder',
            '📄': 'file',
            '✨': 'star',
            '🔍': 'search',
            '⚡': 'lightning',
            '💡': 'idea'
        }
        
        # Replace known emojis first
        for emoji, replacement in emoji_map.items():
            text = text.replace(emoji, replacement)
        
        # Replace any remaining emoji/special characters with their description or remove them
        text = ''.join(
            char if unicodedata.category(char)[0] != 'So' else '-'
            for char in unicodedata.normalize('NFKD', text)
        )
        
        # Clean up any repeated dashes and strip
        text = re.sub(r'-+', '-', text)
        return text.strip('-')

    # Bidirectional emoji mappings with descriptive names
    EMOJI_MAP: Dict[str, Tuple[str, str]] = {
        '📝': ('note', 'n'),
        '📖': ('book', 'b'),
        '📚': ('books', 'bk'),
        '🗂️': ('folder', 'f'),
        '📁': ('folder', 'f'),
        '📄': ('file', 'f'),
        '✨': ('star', 's'),
        '🔍': ('search', 'sr'),
        '⚡': ('lightning', 'l'),
        '💡': ('idea', 'i'),
        '📌': ('pin', 'p'),
        '🔗': ('link', 'lk'),
        '📎': ('attach', 'at'),
        '🏷️': ('tag', 't'),
        '📅': ('date', 'd'),
        '⭐': ('star', 's'),
        '❗': ('important', 'imp'),
        '✅': ('done', 'dn'),
        '🎯': ('target', 'tg'),
        '💭': ('thought', 'th')
    }

    def _encode_path_component(self, component: str) -> str:
        """Convert a path component to a URL-safe format."""
        try:
            # Normalize unicode characters
            normalized = unicodedata.normalize('NFKD', component)
            
            # URL encode the entire component
            encoded = quote(normalized, safe='')
            
            # Clean up the encoding
            encoded = encoded.replace('%20', '-')  # Replace spaces with dashes
            encoded = re.sub(r'%[0-9A-F]{2}', '-', encoded)  # Replace other percent-encoded chars
            encoded = re.sub(r'-+', '-', encoded)  # Collapse multiple dashes
            
            return encoded.strip('-')
            
        except Exception as e:
            logger.error(f"Error encoding component '{component}': {e}")
            # Last resort fallback
            return re.sub(r'[^\w-]', '-', component)

    def _decode_path_component(self, component: str) -> str:
        """Convert a URL-safe path component back to its original form."""
        # Find all short codes and replace with emojis
        def replace_code(match):
            code = match.group(1)
            for emoji, (_, short_code) in self.EMOJI_MAP.items():
                if short_code == code:
                    return emoji
            return match.group(0)
            
        decoded = re.sub(r'\[(\w+)\]', replace_code, component)
        return decoded