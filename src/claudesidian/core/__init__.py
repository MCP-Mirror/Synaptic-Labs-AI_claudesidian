# File: claudesidian/core/__init__.py

"""Core components for Claudesidian."""

from .types import (
    VaultConfig,
    VaultError,
    NoteNotFoundError,
    VaultConfigError,
    LinkType,
    ObsidianLink,
    Tag,
    Heading,
    NoteMetadata,
    Frontmatter
)
from .vault import VaultManager
from .notes import NoteManager
from .frontmatter import FrontmatterParser

__all__ = [
    # Classes
    'VaultManager',
    'NoteManager',
    'Frontmatter',
    'FrontmatterParser',
    
    # Types
    'VaultConfig',
    'LinkType',
    'ObsidianLink',
    'Tag',
    'Heading',
    'NoteMetadata',
    
    # Exceptions
    'VaultError',
    'NoteNotFoundError',
    'VaultConfigError',
    'InvalidFrontmatterError'
]