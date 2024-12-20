"""
Vault interface for Obsidian vault management.
Provides functionality to interact with and manage Obsidian vault files and metadata.
"""

import asyncio
import sys
import re
import time
import yaml
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from concurrent.futures import ThreadPoolExecutor

from rapidfuzz import fuzz  # Updated import for rapidfuzz

@dataclass
class VaultMetadata:
    """
    Represents metadata for an Obsidian vault note.
    """
    created: datetime
    modified: datetime
    tags: Set[str]
    links: Set[str]
    backlinks: Set[str]
    yaml_frontmatter: Dict[str, Any]

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
    Handles file operations and metadata extraction.
    """

    def __init__(self, vault_path: Path):
        """
        Initialize the vault manager.

        Args:
            vault_path (Path): The root path of the Obsidian vault.
        """
        self.vault_path = vault_path
        self.claudesidian_root = vault_path / "claudesidian"
        self.core_memory_folder = self.claudesidian_root / "Core Memory"

        self._metadata_cache: Dict[Path, VaultMetadata] = {}
        self._note_cache: Dict[Path, str] = {}
        self._note_list_cache: Optional[List[VaultNote]] = None
        self._note_list_cache_time: float = 0
        self._cache_ttl = 30  # seconds

        self._executor = ThreadPoolExecutor(max_workers=4)

        # Patterns for extracting metadata from notes
        self._link_pattern = re.compile(r'\[\[(.*?)\]\]')
        self._tag_pattern = re.compile(r'#([a-zA-Z0-9_-]+)')
        self._yaml_pattern = re.compile(r'^---\n(.*?)\n---', re.DOTALL)
        self._raw_tag_pattern = re.compile(r'[^a-zA-Z0-9]+')  # New pattern for normalization

        self._folder_cache = {}
        print(f"VaultManager initialized with path: {vault_path}", file=sys.stderr)

    def normalize_tag(self, tag: str) -> str:
        """
        Convert any string into a valid snake_case tag.
        Examples:
            'winnie the pooh' -> 'winnie_the_pooh'
            'AI/ML tools' -> 'ai_ml_tools'
            'C++' -> 'cpp'
        """
        # Remove leading/trailing spaces and convert to lowercase
        tag = tag.strip().lower()
        
        # Special case replacements
        replacements = {
            'c++': 'cpp',
            'c#': 'csharp',
            '.net': 'dotnet'
            # Add more special cases as needed
        }
        if tag in replacements:
            return replacements[tag]
            
        # Replace non-alphanumeric characters with spaces, then split
        words = self._raw_tag_pattern.sub(' ', tag).split()
        
        # Join with underscores
        return '_'.join(word for word in words if word)

    def normalize_tags(self, tags: List[str]) -> List[str]:
        """Normalize a list of tags to snake_case format."""
        return [self.normalize_tag(tag) for tag in tags if tag]

    async def ensure_folder(self, path: Path) -> bool:
        """
        Ensure a folder exists, creating it if necessary.

        Args:
            path (Path): The folder path to ensure.

        Returns:
            bool: True if the folder exists or was created successfully.
        """
        try:
            path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            print(f"Error creating folder {path}: {e}", file=sys.stderr)
            return False

    async def create_note(self, path: Path, content: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[VaultNote]:
        """
        Create a new note with optional YAML frontmatter metadata.

        Args:
            path (Path): Relative path (under vault root) for the note.
            content (str): Note content.
            metadata (Dict[str,Any], optional): YAML frontmatter to prepend.

        Returns:
            Optional[VaultNote]: The created note, or None if creation failed.
        """
        print(f"[Vault] Creating note at path: {path}", file=sys.stderr)
        absolute_path = self.vault_path / path

        try:
            await self.ensure_folder(absolute_path.parent)
            
            if metadata:
                yaml_frontmatter = yaml.dump(metadata, default_flow_style=False)
                full_content = f"---\n{yaml_frontmatter}---\n{content}"
            else:
                full_content = content

            await self._write_file(absolute_path, full_content)
            note = await self.get_note(absolute_path.relative_to(self.vault_path))
            if note:
                print(f"[Vault] Successfully created note: {path}", file=sys.stderr)
                return note
            else:
                print(f"[Vault] Failed to create note: {path}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"Error creating note {path}: {e}", file=sys.stderr)
            return None

    async def update_note(self, path: Path, content: str, mode: str = 'append', heading: Optional[str] = None) -> bool:
        """
        Update an existing note. Supports appending/prepending content or inserting under a heading.

        Args:
            path (Path): Relative path of the note.
            content (str): Content to add.
            mode (str): One of 'append' or 'prepend'. Default is 'append'.
            heading (Optional[str]): If provided, try to insert under a given heading.

        Returns:
            bool: True if updated successfully, False otherwise.
        """
        print(f"[Vault] Updating note at path: {path} with mode: {mode}", file=sys.stderr)
        absolute_path = self.vault_path / path

        if not absolute_path.exists():
            print(f"Note not found at path: {absolute_path}", file=sys.stderr)
            return False

        try:
            existing_content = await self._read_file(absolute_path)
            if existing_content is None:
                print(f"Could not read existing content from: {absolute_path}", file=sys.stderr)
                return False

            if heading:
                # Escape quotes in heading
                escaped_heading = heading.replace('"', '\\"')
                pattern = rf"(#+\s*{re.escape(escaped_heading)}.*\n)"
                match = re.search(pattern, existing_content, re.IGNORECASE)
                if match:
                    insert_pos = match.end()
                    new_content = existing_content[:insert_pos] + "\n" + content + "\n" + existing_content[insert_pos:]
                else:
                    new_content = f"{existing_content}\n\n## {heading}\n{content}\n"
            else:
                if mode == 'append':
                    new_content = f"{existing_content}\n{content}"
                elif mode == 'prepend':
                    new_content = f"{content}\n{existing_content}"
                else:
                    # If there's another mode, just replace content entirely
                    new_content = content

            await self._write_file(absolute_path, new_content)
            self.invalidate_cache(absolute_path.relative_to(self.vault_path))
            if path in self._note_cache:
                del self._note_cache[path]

            print(f"Successfully updated note: {path}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Error updating note {path}: {e}", file=sys.stderr)
            return False

    async def get_note(self, path: Path) -> Optional[VaultNote]:
        """Retrieve a note from the vault."""
        try:
            absolute_path = self.vault_path / path
            if not absolute_path.exists() or not absolute_path.is_file():
                return None

            content = await self._read_file(absolute_path)
            if content is None:
                return None

            metadata = await self._get_metadata(absolute_path, content)
            note = VaultNote(
                path=path,
                title=path.stem,
                content=content,
                metadata=metadata
            )
            return note
        except Exception as e:
            print(f"[Vault] Error retrieving note at {path}: {e}", file=sys.stderr)
            return None

    async def get_all_notes(self) -> List[VaultNote]:
        """Get all markdown notes from the vault with progress indicator."""
        if (self._note_list_cache is not None and 
            time.time() - self._note_list_cache_time < self._cache_ttl):
            return self._note_list_cache

        print("[Vault] Indexing vault files...", file=sys.stderr)
        md_files = list(self.vault_path.rglob("*.md"))
        total_files = len(md_files)
        processed = 0
        last_progress = 0

        async def process_file(file_path: Path) -> Optional[VaultNote]:
            nonlocal processed, last_progress
            try:
                note = await self.get_note(file_path.relative_to(self.vault_path))
                processed += 1
                
                # Update progress bar every 5%
                progress = int((processed / total_files) * 100)
                if progress >= last_progress + 5:
                    print(f"\r[Vault] Indexing: [{('=' * (progress//5)).ljust(20)}] {progress}%", 
                          end='', file=sys.stderr)
                    last_progress = progress
                return note
            except Exception:
                processed += 1
                return None

        sem = asyncio.Semaphore(50)

        async def bounded_process(file_path: Path):
            async with sem:
                return await process_file(file_path)

        tasks = [bounded_process(f) for f in md_files]
        results = await asyncio.gather(*tasks)
        notes = [note for note in results if note is not None]

        print("\n[Vault] Indexing complete", file=sys.stderr)
        self._note_list_cache = notes
        self._note_list_cache_time = time.time()
        return notes

    async def get_notes_in_folder(self, folder_path: Path) -> List[VaultNote]:
        """Retrieve all notes within the specified folder."""
        notes = []
        folder_full_path = self.vault_path / folder_path
        for file_path in folder_full_path.rglob("*.md"):
            try:
                note = await self.get_note(file_path.relative_to(self.vault_path))
                if note:
                    notes.append(note)
            except Exception as e:
                continue
        return notes

    async def _get_metadata(self, path: Path, content: str) -> VaultMetadata:
        """Extract metadata while handling template files gracefully."""
        if path in self._metadata_cache:
            return self._metadata_cache[path]

        try:
            stats = path.stat()
            created = datetime.fromtimestamp(stats.st_ctime)
            modified = datetime.fromtimestamp(stats.st_mtime)

            yaml_frontmatter = {}
            yaml_match = self._yaml_pattern.match(content)
            if yaml_match:
                yaml_content = yaml_match.group(1)
                # Skip YAML parsing for template files
                if '{{' in yaml_content or '{%' in yaml_content:
                    yaml_frontmatter = {"_is_template": True}
                else:
                    try:
                        parsed = yaml.safe_load(yaml_content)
                        if isinstance(parsed, dict):
                            yaml_frontmatter = parsed
                    except yaml.YAMLError:
                        # If YAML parsing fails, store as raw content
                        yaml_frontmatter = {"_raw_frontmatter": yaml_content}

            tags = set(self._tag_pattern.findall(content))
            links = set(self._link_pattern.findall(content))
            backlinks = set()  # Skip backlinks for template files

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
            print(f"Error extracting metadata for {path}: {e}", file=sys.stderr)
            return VaultMetadata(
                created=datetime.now(),
                modified=datetime.now(),
                tags=set(),
                links=set(),
                backlinks=set(),
                yaml_frontmatter={}
            )

    def _fix_yaml_placeholders(self, yaml_content: str) -> str:
        """
        Attempt to fix YAML placeholders by quoting them.

        Args:
            yaml_content (str): The original YAML content.

        Returns:
            str: The fixed YAML content.
        """
        lines = yaml_content.split('\n')
        fixed_lines = []
        for line in lines:
            # Detect lines with placeholders like {{hashTags}}
            if re.search(r'\{\{.*?\}\}', line):
                # Quote the entire value
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key, value = parts
                    fixed_line = f"{key}: \"{value.strip()}\""
                    fixed_lines.append(fixed_line)
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        return '\n'.join(fixed_lines)  # Fixed the syntax error here

    async def _read_file(self, path: Path) -> Optional[str]:
        """
        Read file content with caching.

        Args:
            path (Path): The absolute path of the file.

        Returns:
            Optional[str]: The file content, or None on error.
        """
        if path in self._note_cache:
            return self._note_cache[path]

        loop = asyncio.get_event_loop()
        try:
            content = await loop.run_in_executor(
                self._executor,
                lambda: path.read_text(encoding='utf-8')
            )
            self._note_cache[path] = content
            return content
        except Exception as e:
            print(f"Error reading {path}: {e}", file=sys.stderr)
            return None

    async def _write_file(self, path: Path, content: str) -> None:
        """
        Write file content asynchronously.

        Args:
            path (Path): The absolute path to write.
            content (str): The content to write.
        """
        await asyncio.to_thread(path.write_text, content, encoding='utf-8')

    def invalidate_cache(self, path: Optional[Path] = None) -> None:
        """
        Invalidate metadata cache for a specific path or entire cache.

        Args:
            path (Optional[Path]): If provided, invalidate cache for that path. 
                                    Otherwise, clear entire cache.
        """
        if path is None:
            self._metadata_cache.clear()
            self._note_list_cache = None
        else:
            if path in self._metadata_cache:
                del self._metadata_cache[path]
            if self._note_list_cache:
                self._note_list_cache = [note for note in self._note_list_cache if note.path != path]

    async def cleanup(self):
        """
        Clean up resources before shutting down.
        """
        self._executor.shutdown(wait=False)
        print("[Vault] Executor shut down", file=sys.stderr)
