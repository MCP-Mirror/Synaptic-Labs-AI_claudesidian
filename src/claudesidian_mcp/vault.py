"""
Vault interface for Obsidian vault management.
Provides functionality to interact with and manage Obsidian vault files and metadata.
"""

import asyncio
import os
import sys  # Add sys import
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import time

@dataclass
class VaultMetadata:
    """
    Represents metadata for an Obsidian vault or note.
    """
    created: datetime
    modified: datetime
    tags: Set[str]
    links: Set[str]
    backlinks: Set[str]
    yaml_frontmatter: Dict[str, any]

@dataclass
class VaultNote:
    """
    Represents a single note in the Obsidian vault.
    """
    path: Path
    title: str
    content: str
    metadata: VaultMetadata

class VaultManager:
    """
    Manages interactions with an Obsidian vault.
    Handles file operations, metadata extraction, and link management.
    """
    
    def __init__(self, vault_path: Path):
        """
        Initialize the vault manager.
        
        Args:
            vault_path (Path): Root path of the Obsidian vault
        """
        self.vault_path = vault_path
        self._metadata_cache: Dict[Path, VaultMetadata] = {}
        self._link_pattern = re.compile(r'\[\[(.*?)\]\]')
        self._tag_pattern = re.compile(r'#([a-zA-Z0-9_-]+)')
        self._yaml_pattern = re.compile(r'^---\n(.*?)\n---', re.DOTALL)
        self._note_cache = {}
        self._note_list_cache = None
        self._note_list_cache_time = 0
        self._cache_ttl = 30  # Cache TTL in seconds

    async def get_note(self, path: Path) -> Optional[VaultNote]:
        """
        Retrieve a note from the vault.
        
        Args:
            path (Path): Path to the note relative to vault root
            
        Returns:
            Optional[VaultNote]: The note if found
        """
        absolute_path = self.vault_path / path
        if not absolute_path.exists() or not absolute_path.is_file():
            return None
            
        try:
            content = await self._read_file(absolute_path)
            metadata = await self._get_metadata(absolute_path, content)
            
            return VaultNote(
                path=path,
                title=path.stem,
                content=content,
                metadata=metadata
            )
        except Exception as e:
            print(f"Error reading note {path}: {e}")
            return None

    async def create_note(self, path: Path, content: str, metadata: Optional[Dict] = None) -> Optional[VaultNote]:
        """
        Create a new note in the vault.
        
        Args:
            path (Path): Path for the new note
            content (str): Note content
            metadata (Optional[Dict]): YAML frontmatter metadata
            
        Returns:
            Optional[VaultNote]: The created note if successful
        """
        absolute_path = self.vault_path / path
        
        try:
            # Ensure parent directories exist
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Add YAML frontmatter if provided
            if metadata:
                yaml_content = "---\n"
                for key, value in metadata.items():
                    yaml_content += f"{key}: {value}\n"
                yaml_content += "---\n\n"
                content = yaml_content + content
            
            # Write the file
            await self._write_file(absolute_path, content)
            
            # Return the new note
            return await self.get_note(path)
            
        except Exception as e:
            print(f"Error creating note {path}: {e}")
            return None

    async def update_note(self, path: Path, content: str, mode: str = 'append', heading: Optional[str] = None) -> bool:
        """Update an existing note's content."""
        absolute_path = self.vault_path / path
        if not absolute_path.exists():
            print(f"Note not found at path: {absolute_path}", file=sys.stderr)
            return False
            
        try:
            # Read existing content
            existing_content = await self._read_file(absolute_path)
            if existing_content is None:
                print(f"Could not read existing content from: {absolute_path}", file=sys.stderr)
                return False

            # Prepare new content
            if heading:
                pattern = rf"(#+\s*{re.escape(heading)}.*\n)"
                match = re.search(pattern, existing_content, re.IGNORECASE)
                if match:
                    # Insert under heading with proper spacing
                    insert_pos = match.end()
                    new_content = (
                        existing_content[:insert_pos] + 
                        "\n" + content + "\n" + 
                        existing_content[insert_pos:]
                    )
                else:
                    # Append new heading and content
                    new_content = f"{existing_content}\n\n## {heading}\n{content}\n"
            else:
                # Handle append/prepend modes
                if mode == 'append':
                    new_content = f"{existing_content}\n{content}"
                elif mode == 'prepend':
                    new_content = f"{content}\n{existing_content}"
                else:
                    new_content = content

            # Write the updated content
            await self._write_file(absolute_path, new_content)
            
            # Invalidate caches
            self.invalidate_cache(path)
            if path in self._note_cache:
                del self._note_cache[path]
                
            print(f"Successfully updated note: {path}", file=sys.stderr)
            return True
            
        except Exception as e:
            print(f"Error updating note {path}: {e}", file=sys.stderr)
            return False

    async def delete_note(self, path: Path) -> bool:
        """
        Delete a note from the vault.
        
        Args:
            path (Path): Path to the note
            
        Returns:
            bool: True if deletion was successful
        """
        absolute_path = self.vault_path / path
        try:
            if absolute_path.exists():
                absolute_path.unlink()
                if path in self._metadata_cache:
                    del self._metadata_cache[path]
                return True
            return False
        except Exception as e:
            print(f"Error deleting note {path}: {e}")
            return False

    async def get_all_notes(self) -> List[VaultNote]:
        """
        Get all notes with caching.
        """
        current_time = time.time()
        
        # Return cached results if still valid
        if (self._note_list_cache is not None and 
            current_time - self._note_list_cache_time < self._cache_ttl):
            return self._note_list_cache

        notes = []
        try:
            # Process files in parallel
            async def process_file(file_path: Path) -> Optional[VaultNote]:
                if any(part.startswith('.') for part in file_path.parts):
                    return None
                    
                relative_path = file_path.relative_to(self.vault_path)
                return await self.get_note(relative_path)

            # Create tasks for all markdown files
            tasks = []
            for file_path in self.vault_path.rglob("*.md"):
                tasks.append(asyncio.create_task(process_file(file_path)))

            # Gather results
            results = await asyncio.gather(*tasks)
            notes = [note for note in results if note is not None]
            
            # Update cache
            self._note_list_cache = notes
            self._note_list_cache_time = current_time
                    
        except Exception as e:
            print(f"Error listing notes: {e}")
            
        return notes

    async def _get_metadata(self, path: Path, content: str) -> VaultMetadata:
        """
        Extract metadata from a note.
        
        Args:
            path (Path): Path to the note
            content (str): Note content
            
        Returns:
            VaultMetadata: Extracted metadata
        """
        if path in self._metadata_cache:
            return self._metadata_cache[path]
            
        try:
            # Extract creation and modification times
            stats = path.stat()
            created = datetime.fromtimestamp(stats.st_ctime)
            modified = datetime.fromtimestamp(stats.st_mtime)
            
            # Extract YAML frontmatter
            yaml_match = self._yaml_pattern.match(content)
            yaml_frontmatter = {}
            if yaml_match:
                # Simple YAML parsing (could be enhanced with PyYAML)
                yaml_content = yaml_match.group(1)
                for line in yaml_content.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        yaml_frontmatter[key.strip()] = value.strip()
            
            # Extract tags and links
            tags = set(self._tag_pattern.findall(content))
            links = set(self._link_pattern.findall(content))
            
            # Calculate backlinks (could be optimized with an index)
            backlinks = set()
            for other_path in self.vault_path.rglob("*.md"):
                if other_path == path:
                    continue
                    
                other_content = other_path.read_text(encoding='utf-8')
                if path.stem in self._link_pattern.findall(other_content):
                    backlinks.add(other_path.stem)
            
            metadata = VaultMetadata(
                created=created,
                modified=modified,
                tags=tags,
                links=links,
                backlinks=backlinks,
                yaml_frontmatter=yaml_frontmatter
            )
            
            self._metadata_cache[path] = metadata
            return metadata
            
        except Exception as e:
            print(f"Error extracting metadata for {path}: {e}")
            return VaultMetadata(
                created=datetime.now(),
                modified=datetime.now(),
                tags=set(),
                links=set(),
                backlinks=set(),
                yaml_frontmatter={}
            )

    async def _read_file(self, path: Path) -> str:
        """
        Read file content with caching.
        """
        if path in self._note_cache:
            return self._note_cache[path]
            
        content = await asyncio.to_thread(path.read_text, encoding='utf-8')
        self._note_cache[path] = content
        return content

    async def _write_file(self, path: Path, content: str) -> None:
        """
        Write file content asynchronously.
        
        Args:
            path (Path): Path to the file
            content (str): Content to write
        """
        await asyncio.to_thread(path.write_text, content, encoding='utf-8')

    def invalidate_cache(self, path: Optional[Path] = None) -> None:
        """
        Invalidate metadata cache for a specific path or entire cache.
        
        Args:
            path (Optional[Path]): Path to invalidate, or None for entire cache
        """
        if path is None:
            self._metadata_cache.clear()
        elif path in self._metadata_cache:
            del self._metadata_cache[path]

from pathlib import Path
from typing import Optional
import re

class Vault:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path

    def create_note(self, note_name: str, content: str = "", folder: Optional[Path] = None) -> Path:
        # If no folder specified, find the best folder
        if folder is None:
            folder = self._find_best_folder(note_name)
        note_path = folder / f"{note_name}.md"
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding='utf-8')
        return note_path

    def edit_note(self, note_path: Path, content: str, mode: str = 'append', heading: Optional[str] = None) -> None:
        existing_content = note_path.read_text(encoding='utf-8')
        if heading:
            # Find the heading and insert content under it
            pattern = rf"(#+\s*{re.escape(heading)}.*\n)"
            match = re.search(pattern, existing_content, re.IGNORECASE)
            if match:
                insert_pos = match.end()
                new_content = existing_content[:insert_pos] + content + '\n' + existing_content[insert_pos:]
                note_path.write_text(new_content, encoding='utf-8')
                return
        if mode == 'append':
            note_path.write_text(existing_content + '\n' + content, encoding='utf-8')
        elif mode == 'prepend':
            note_path.write_text(content + '\n' + existing_content, encoding='utf-8')

    def delete_note(self, note_path: Path) -> None:
        # Delete the note file
        note_path.unlink(missing_ok=True)

    def find_note_by_name(self, note_name: str) -> Optional[Path]:
        # Search for a note by name
        for note_path in self.vault_path.rglob(f"{note_name}.md"):
            return note_path
        return None

    def _find_best_folder(self, note_name: str) -> Path:
        # Implement logic to find the most suitable folder
        # For simplicity, return the root vault path
        return self.vault_path