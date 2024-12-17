"""Type definitions for core functionality."""

from typing import TypedDict, List, Optional, Dict, Any, Union
from pathlib import Path
from enum import Enum
from datetime import datetime
import logging  # Added import

logger = logging.getLogger(__name__)  # Defined logger

class VaultConfig(TypedDict, total=False):
    """Obsidian vault configuration."""
    name: str
    attachments_path: str
    daily_notes_path: str
    templates_path: str
    theme: str
    plugins: Dict[str, Any]
    css_snippets: List[str]
    hotkeys: Dict[str, str]
    graph_settings: Dict[str, Any]
    workspace: Dict[str, Any]

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

class Tag(TypedDict):
    """Represents a tag in a note."""
    name: str            # Tag name without #
    position: Dict[str, int]  # Position in document

class Heading(TypedDict):
    """Represents a markdown heading in a note."""
    level: int           # Heading level (1-6)
    text: str           # Heading text
    position: Dict[str, int]  # Position in document

class NoteMetadata(TypedDict):
    """Full metadata for a note."""
    path: Path           # Path relative to vault root
    frontmatter: 'Frontmatter'  # Note frontmatter
    links: List[ObsidianLink]  # Internal links
    tags: List[Tag]     # Tags in content
    headings: List[Heading]  # Section headings
    wordcount: int      # Total word count
    backlinks: List[ObsidianLink]  # Links to this note
    checkboxes: List[Dict[str, Any]]  # Task checkboxes
    last_modified: datetime  # Last modified timestamp
    created: datetime    # Creation timestamp
    size: int           # File size in bytes

class VaultError(Exception):
    """Base exception for vault operations."""
    pass

class NoteNotFoundError(VaultError):
    """Raised when a note cannot be found."""
    pass

class VaultConfigError(VaultError):
    """Raised when there's an issue with vault configuration."""
    pass

class InvalidFrontmatterError(VaultError):
    """Raised when frontmatter is invalid."""
    pass

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
    type: str          # Note type
    id: str            # Unique identifier
    weight: float      # For ordering/importance
    parent: str        # Parent note path
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
            try:
                self[key] = value
            except ValueError as ve:
                logger.warning(f"Invalid type for field '{key}': {ve}")  # Uses defined logger
                self._data[key] = value  # Store invalid value without type enforcement
    
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

    def _validate_type(self, value: Any, expected_type: Any) -> bool:
        """
        Validate value against expected type.
        
        Args:
            value: Value to validate
            expected_type: Expected type annotation
        
        Returns:
            True if valid, False otherwise
        """
        from typing import get_origin, get_args
        import datetime
        
        # Handle None values
        if value is None:
            return True
            
        # Handle List type
        if get_origin(expected_type) == list:
            if not isinstance(value, list):
                return False
            element_type = get_args(expected_type)[0]
            return all(isinstance(x, element_type) for x in value)
            
        # Handle datetime specifically
        if expected_type == datetime.datetime:
            if isinstance(value, str):
                try:
                    datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                    return True
                except ValueError:
                    return False
            return isinstance(value, datetime.datetime)
            
        # Handle Union types
        if get_origin(expected_type) == Union:
            return any(self._validate_type(value, t) for t in get_args(expected_type))
            
        # Handle basic types
        if expected_type in (str, int, float, bool):
            return isinstance(value, expected_type)
            
        return True  # Allow unknown types to pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return self._data.copy()

__all__ = [
    'LinkType',
    'ObsidianLink',
    'Tag',
    'Heading',
    'NoteMetadata',
    'VaultConfig',
    'Frontmatter',
    'KnownFrontmatter',
    'VaultError',
    'VaultConfigError',
    'NoteNotFoundError',
    'InvalidFrontmatterError'
]
