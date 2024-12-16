# File: claudesidian/core/__init__.py

"""
Core module for Obsidian vault operations.
Provides base types and functionality for vault management.
"""

from pathlib import Path
from typing import TypedDict, List, Optional, Union, Dict, Any
from datetime import datetime
from enum import Enum

# Type Definitions
class LinkType(Enum):
    """Types of links that can exist in Obsidian."""
    WIKI = "wiki"           # [[Wiki Links]]
    MARKDOWN = "markdown"   # [Markdown](links)
    EMBED = "embed"        # ![[Embedded content]]
    TRANSCLUDE = "transclude"  # Reading content from another note

class ObsidianLink(TypedDict):
    """Represents an Obsidian internal link."""
    path: str              # Path to target
    alias: Optional[str]   # Optional display text
    type: LinkType        # Type of link
    position: Dict[str, int]  # Position in document {line, col}

class Heading(TypedDict):
    """Represents a markdown heading in a note."""
    text: str             # Heading text
    level: int           # Heading level (1-6)
    position: Dict[str, int]  # Position in document

class Tag(TypedDict):
    """Represents a tag in a note."""
    name: str            # Tag name without #
    position: Dict[str, int]  # Position in document

class KnownFrontmatter(TypedDict, total=False):
    """
    Known frontmatter fields that we specifically handle.
    All fields are optional (total=False).
    """
    title: str           # Note title
    aliases: List[str]   # Alternative names
    tags: List[str]      # List of tags
    created: datetime    # Creation date
    modified: datetime   # Last modified date
    status: str         # Note status
    type: str           # Note type
    id: str             # Unique identifier
    weight: float       # For ordering/importance
    parent: str         # Parent note path
    children: List[str]  # Child note paths

class Frontmatter:
    """
    Flexible frontmatter handler that supports both known and custom fields.
    Provides type checking for known fields while allowing any custom fields.
    """
    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = {}
        self._known_fields = set(KnownFrontmatter.__annotations__.keys())
        
        # Process all fields
        for key, value in data.items():
            self[key] = value
    
    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access to fields."""
        return self._data.get(key)
    
    def __setitem__(self, key: str, value: Any) -> None:
        """
        Set frontmatter field with type validation for known fields.
        Custom fields are stored as-is.
        """
        if key in self._known_fields:
            # Validate known fields
            expected_type = KnownFrontmatter.__annotations__[key]
            if not self._validate_type(value, expected_type):
                raise ValueError(f"Invalid type for {key}. Expected {expected_type}")
        
        self._data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get field with default value."""
        return self._data.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to regular dictionary."""
        return self._data.copy()
    
    @staticmethod
    def _validate_type(value: Any, expected_type: Any) -> bool:
        """
        Validate value against expected type.
        Handles complex types like List[str].
        """
        if expected_type == List[str]:
            return (
                isinstance(value, list) and 
                all(isinstance(x, str) for x in value)
            )
        if expected_type == datetime:
            # Handle various datetime formats
            if isinstance(value, str):
                try:
                    # Try parsing the string to datetime
                    datetime.fromisoformat(value.replace('Z', '+00:00'))
                    return True
                except ValueError:
                    return False
            return isinstance(value, datetime)
            
        return isinstance(value, expected_type)
    
    def __contains__(self, key: str) -> bool:
        return key in self._data
        
    def keys(self):
        return self._data.keys()
        
    def values(self):
        return self._data.values()
        
    def items(self):
        return self._data.items()
        
    def validate_schema(self, schema: Dict[str, Any]) -> bool:
        """
        Optionally validate against a user-provided schema.
        Useful for maintaining consistency in notes.
        """
        try:
            for key, expected_type in schema.items():
                if key in self._data:
                    if not self._validate_type(self._data[key], expected_type):
                        return False
            return True
        except Exception:
            return False

class NoteMetadata(TypedDict):
    """Full metadata for a note."""
    path: Path           # Path relative to vault root
    frontmatter: Frontmatter  # Note frontmatter
    links: List[ObsidianLink]  # Internal links
    tags: List[Tag]     # Tags in content
    headings: List[Heading]  # Section headings
    wordcount: int      # Total word count
    backlinks: List[ObsidianLink]  # Links to this note
    checkboxes: List[Dict[str, Any]]  # Task checkboxes
    last_modified: datetime  # Last modified timestamp
    created: datetime    # Creation timestamp
    size: int           # File size in bytes

class VaultConfig(TypedDict, total=False):
    """Obsidian vault configuration."""
    name: str           # Vault name
    attachments_path: str  # Attachments folder
    daily_notes_path: str  # Daily notes location
    templates_path: str   # Templates folder
    theme: str          # Current theme
    plugins: Dict[str, Any]  # Plugin settings
    css_snippets: List[str]  # Custom CSS snippets
    hotkeys: Dict[str, str]  # Custom hotkey bindings
    graph_settings: Dict[str, Any]  # Graph view settings
    workspace: Dict[str, Any]  # Workspace layout

# Exceptions
class VaultError(Exception):
    """Base exception for vault operations."""
    pass

class NoteNotFoundError(VaultError):
    """Raised when a note cannot be found."""
    pass

class InvalidFrontmatterError(VaultError):
    """Raised when frontmatter is invalid."""
    pass

class LinkResolutionError(VaultError):
    """Raised when a link cannot be resolved."""
    pass

class VaultConfigError(VaultError):
    """Raised when there's an issue with vault configuration."""
    pass

class ValidationError(VaultError):
    """Raised when validation fails."""
    pass

# Export main components
from .vault import VaultManager
from .notes import NoteManager
from .frontmatter import FrontmatterManager

__all__ = [
    # Main classes
    'VaultManager',
    'NoteManager',
    'FrontmatterManager',
    'Frontmatter',
    
    # Types
    'LinkType',
    'ObsidianLink',
    'Heading',
    'Tag',
    'KnownFrontmatter',
    'NoteMetadata',
    'VaultConfig',
    
    # Exceptions
    'VaultError',
    'NoteNotFoundError',
    'InvalidFrontmatterError',
    'LinkResolutionError',
    'VaultConfigError',
    'ValidationError'
]

# Version info
__version__ = "0.1.0"