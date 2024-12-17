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

from .types import (
    Frontmatter, 
    InvalidFrontmatterError,
    NoteMetadata, 
    ObsidianLink, 
    LinkType, 
    Tag, 
    Heading,
    NoteNotFoundError  # Added import
)
from .frontmatter import FrontmatterParser

logger = logging.getLogger(__name__)

class SafeTemplateLoader(yaml.SafeLoader):
    """Custom YAML loader that handles both templates and markdown content safely."""
    
    @staticmethod
    def preserve_markdown(value):
        """Preserve markdown content in YAML values."""
        if isinstance(value, str):
            # Handle Obsidian-style links [[...]]
            if '[[' in value and ']]' in value:
                return str(value)
            # Handle markdown list items
            if value.startswith('- '):
                return str(value)
        return value

    def construct_scalar(self, node):
        """Override scalar construction to preserve markdown."""
        value = super().construct_scalar(node)
        return self.preserve_markdown(value)

class NoteFrontmatter:
    """Handle note frontmatter parsing with template and markdown support."""

    @staticmethod
    def _escape_quotes(text: str) -> str:
        """Handle nested quotes in YAML values."""
        # If text contains quotes, wrap it in block scalar
        if '"' in text or "'" in text:
            # Use literal block scalar for preserving quotes
            escaped = text.replace('\n', '\n  ')  # Indent content
            return f'|-\n  {escaped}'
        return f'"{text}"'

    @staticmethod
    def _preprocess_frontmatter(text: str) -> str:
        """Pre-process frontmatter text to handle complex values."""
        lines = text.split('\n')
        processed_lines = []
        in_list = False
        list_indent = 0
        current_key = None

        for line in lines:
            stripped = line.lstrip()
            if not stripped:
                processed_lines.append(line)
                continue

            # Handle list items
            if stripped.startswith('- '):
                in_list = True
                if not list_indent:
                    list_indent = len(line) - len(stripped)
                processed_lines.append(line)
                continue

            if in_list and len(line) - len(line.lstrip()) >= list_indent:
                processed_lines.append(line)
                continue

            in_list = False
            list_indent = 0

            # Handle key-value pairs
            if ':' in stripped and not stripped.startswith('-'):
                key, value = [x.strip() for x in stripped.split(':', 1)]
                current_key = key
                indent = len(line) - len(stripped)

                # Handle empty values
                if not value:
                    processed_lines.append(line)
                    continue

                # Handle values with special characters
                if any(c in value for c in '"\':#,[]{}'):
                    escaped_value = NoteFrontmatter._escape_quotes(value)
                    if '\n' in escaped_value:
                        # Multiline value
                        processed_lines.append(f"{' ' * indent}{key}:")
                        for v_line in escaped_value.split('\n'):
                            processed_lines.append(f"{' ' * (indent + 2)}{v_line}")
                    else:
                        processed_lines.append(f"{' ' * indent}{key}: {escaped_value}")
                else:
                    processed_lines.append(line)
            else:
                # Handle continuation of previous value
                if current_key and not stripped.startswith('-'):
                    indent = len(line) - len(stripped)
                    escaped_value = NoteFrontmatter._escape_quotes(stripped)
                    processed_lines[-1] = f"{' ' * indent}{current_key}: {escaped_value}"
                else:
                    processed_lines.append(line)

        return '\n'.join(processed_lines)

    @staticmethod
    def parse_frontmatter(content: str) -> Optional[Dict[str, Any]]:
        """Parse frontmatter while handling complex values."""
        try:
            match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not match:
                return None

            frontmatter_text = match.group(1)
            processed_text = NoteFrontmatter._preprocess_frontmatter(frontmatter_text)

            # Use safe_load to parse the processed YAML
            frontmatter = yaml.safe_load(processed_text)

            if not isinstance(frontmatter, dict):
                return {}

            # Clean and normalize values
            cleaned = {}
            for k, v in frontmatter.items():
                if isinstance(v, str):
                    # Preserve newlines in block scalars
                    if '\n' in v:
                        cleaned[k] = v
                    else:
                        cleaned[k] = v.strip()
                elif isinstance(v, list):
                    # Handle list values
                    cleaned[k] = [
                        item.strip() if isinstance(item, str) else item
                        for item in v
                    ]
                else:
                    cleaned[k] = v

            return cleaned

        except Exception as e:
            logger.warning(f"Error parsing frontmatter: {e}")
            return {}

    # ...existing code...

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
        """Parse note content to extract metadata."""
        # Extract frontmatter using new parser
        frontmatter = {}
        try:
            result = FrontmatterParser.parse(content)
            if result.errors:
                logger.debug(f"Frontmatter parsing issues in {path}: {result.errors}")
            frontmatter = result.data
            content = content[len(result.raw_text):] if result.raw_text else content
        except Exception as e:
            logger.warning(f"Failed to parse frontmatter in {path}: {e}")
            frontmatter = {}  # Fallback to empty frontmatter

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