# File: claudesidian/core/notes.py

"""
Note management for Claudesidian.
Handles note operations, content parsing, and metadata management.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime
import logging
import yaml

from . import (
    NoteMetadata, ObsidianLink, LinkType, Tag, Heading, 
    Frontmatter, NoteNotFoundError, InvalidFrontmatterError
)

logger = logging.getLogger(__name__)

class NoteManager:
    """
    Manages individual notes within an Obsidian vault.
    Handles content parsing, metadata extraction, and note operations.
    """
    
    # Regex patterns for parsing
    FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
    WIKILINK_RE = re.compile(r"\[\[(.*?)(?:\|(.*?))?\]\]")
    MDLINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    EMBED_RE = re.compile(r"!\[\[(.*?)(?:\|(.*?))?\]\]")
    TAG_RE = re.compile(r"#([a-zA-Z0-9_/-]+)")
    HEADING_RE = re.compile(r"^(#+)\s+(.+)$", re.MULTILINE)
    CHECKBOX_RE = re.compile(r"^(?:\s*[-*+]|\d+\.)\s+\[([ xX])\]\s+(.+)$", re.MULTILINE)

    def __init__(self, vault_manager):
        """
        Initialize note manager.
        
        Args:
            vault_manager: VaultManager instance
        """
        self.vault = vault_manager
        self._cache: Dict[Path, NoteMetadata] = {}
        
        # Register for vault events
        self.vault.on('note_modified', self._handle_note_modified)
        self.vault.on('note_created', self._handle_note_created)
        self.vault.on('note_deleted', self._handle_note_deleted)

    async def get_note(self, path: Path) -> Tuple[str, NoteMetadata]:
        """
        Get note content and metadata.
        
        Args:
            path: Path to note
            
        Returns:
            Tuple of (content, metadata)
        """
        full_path = self.vault.vault_path / path
        if not full_path.exists():
            raise NoteNotFoundError(f"Note not found: {path}")
            
        # Check cache first
        if path in self._cache:
            metadata = self._cache[path]
            if full_path.stat().st_mtime == metadata.get('last_modified'):
                # Cache is still valid
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return content, metadata
                
        # Read and parse note
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        metadata = await self.parse_note(content, path)
        self._cache[path] = metadata
        
        return content, metadata

    async def update_note(self, path: Path, 
                         content: Optional[str] = None,
                         frontmatter: Optional[Dict[str, Any]] = None,
                         append: bool = False) -> None:
        """
        Update a note's content and/or frontmatter.
        
        Args:
            path: Path to note
            content: New content (if None, keep existing)
            frontmatter: New frontmatter (if None, keep existing)
            append: If True, append content instead of replacing
        """
        full_path = self.vault.vault_path / path
        if not full_path.exists():
            raise NoteNotFoundError(f"Note not found: {path}")
            
        # Read existing content
        with open(full_path, 'r', encoding='utf-8') as f:
            existing_content = f.read()
            
        # Parse existing frontmatter
        existing_fm = None
        fm_match = self.FRONTMATTER_RE.match(existing_content)
        if fm_match:
            try:
                existing_fm = yaml.safe_load(fm_match.group(1))
                main_content = existing_content[fm_match.end():]
            except yaml.YAMLError as e:
                raise InvalidFrontmatterError(f"Invalid frontmatter: {e}")
        else:
            main_content = existing_content
            
        # Build new content
        new_content = ""
        
        # Handle frontmatter
        if frontmatter is not None:
            # Merge with existing if any
            if existing_fm:
                merged_fm = {**existing_fm, **frontmatter}
            else:
                merged_fm = frontmatter
                
            # Add frontmatter
            new_content += "---\n"
            new_content += yaml.dump(merged_fm, allow_unicode=True)
            new_content += "---\n\n"
            
        elif existing_fm:
            # Keep existing frontmatter
            new_content += "---\n"
            new_content += yaml.dump(existing_fm, allow_unicode=True)
            new_content += "---\n\n"
            
        # Handle content
        if content is not None:
            if append:
                new_content += main_content + "\n\n" + content
            else:
                new_content += content
        else:
            new_content += main_content
            
        # Write updated note
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

    async def parse_note(self, content: str, path: Path) -> NoteMetadata:
        """
        Parse note content to extract metadata.
        
        Args:
            content: Note content
            path: Note path
            
        Returns:
            NoteMetadata object
        """
        # Extract frontmatter
        frontmatter = {}
        fm_match = self.FRONTMATTER_RE.match(content)
        if fm_match:
            try:
                frontmatter = yaml.safe_load(fm_match.group(1))
                content = content[fm_match.end():]
            except yaml.YAMLError as e:
                logger.warning(f"Invalid frontmatter in {path}: {e}")
                
        # Extract links
        links = []
        
        # Wiki links [[target|alias]]
        for match in self.WIKILINK_RE.finditer(content):
            target = match.group(1)
            alias = match.group(2)
            links.append({
                'path': target,
                'alias': alias,
                'type': LinkType.WIKI,
                'position': {'line': content.count('\n', 0, match.start())}
            })
            
        # Markdown links [alias](target)
        for match in self.MDLINK_RE.finditer(content):
            alias = match.group(1)
            target = match.group(2)
            if not target.startswith(('http://', 'https://')):
                links.append({
                    'path': target,
                    'alias': alias,
                    'type': LinkType.MARKDOWN,
                    'position': {'line': content.count('\n', 0, match.start())}
                })
                
        # Embeds ![[target]]
        for match in self.EMBED_RE.finditer(content):
            target = match.group(1)
            alias = match.group(2)
            links.append({
                'path': target,
                'alias': alias,
                'type': LinkType.EMBED,
                'position': {'line': content.count('\n', 0, match.start())}
            })
            
        # Extract tags
        tags = []
        for match in self.TAG_RE.finditer(content):
            tags.append({
                'name': match.group(1),
                'position': {'line': content.count('\n', 0, match.start())}
            })
            
        # Extract headings
        headings = []
        for match in self.HEADING_RE.finditer(content):
            headings.append({
                'level': len(match.group(1)),
                'text': match.group(2).strip(),
                'position': {'line': content.count('\n', 0, match.start())}
            })
            
        # Extract checkboxes
        checkboxes = []
        for match in self.CHECKBOX_RE.finditer(content):
            checkboxes.append({
                'checked': match.group(1).lower() == 'x',
                'text': match.group(2),
                'position': {'line': content.count('\n', 0, match.start())}
            })
            
        # Get file stats
        full_path = self.vault.vault_path / path
        stats = full_path.stat()
        
        return {
            'path': path,
            'frontmatter': Frontmatter(frontmatter),
            'links': links,
            'tags': tags,
            'headings': headings,
            'checkboxes': checkboxes,
            'wordcount': len(content.split()),
            'backlinks': [],  # Filled in by vault manager
            'last_modified': datetime.fromtimestamp(stats.st_mtime),
            'created': datetime.fromtimestamp(stats.st_ctime),
            'size': stats.st_size
        }

    async def _handle_note_modified(self, path: Path) -> None:
        """Handle note modification event."""
        # Clear cache for modified note
        self._cache.pop(path, None)
        
    async def _handle_note_created(self, path: Path) -> None:
        """Handle note creation event."""
        # Nothing to do, will be cached on first access
        pass
        
    async def _handle_note_deleted(self, path: Path) -> None:
        """Handle note deletion event."""
        # Remove from cache
        self._cache.pop(path, None)

    async def close(self) -> None:
        """Clean up resources."""
        self._cache.clear()