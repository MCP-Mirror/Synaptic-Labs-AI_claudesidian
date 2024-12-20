"""
Memory management module optimized for speed.
Uses rapidfuzz for fuzzy matching instead of fuzzywuzzy, minimizes overhead.
"""

import sys
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz, process

from .vault import VaultManager

class MemoryManager:
    """Manages memory operations using the vault as a backing store quickly and efficiently."""

    def __init__(self, vault: VaultManager):
        self.vault = vault
        self._memory_folder = Path("memory")

    async def create_memory(
        self,
        title: str,
        content: str,
        memory_type: str,
        categories: List[str],
        description: str,
        relationships: List[str],
        tags: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new memory entry with YAML metadata and store it in the vault.
        Focus on quick I/O by using the already established vault methods.
        """
        try:
            metadata = {
                "Title": title,
                "Type": memory_type,
                "Category": categories,
                "Description": description,
                "Relationships": relationships,
                "Tags": tags,
                "Date_created": datetime.now().isoformat(),
                "Date_modified": datetime.now().isoformat()
            }

            note = await self.vault.create_note(
                path=self._memory_folder / f"{title}.md",
                content=content,
                metadata=metadata
            )

            if note:
                return {
                    "title": note.title,
                    "path": str(note.path),
                    "metadata": note.metadata.yaml_frontmatter
                }
        except Exception as e:
            print(f"[MemoryManager] Error creating memory: {e}", file=sys.stderr)

        return None

    async def strengthen_relationship(
        self,
        source_path: Path,
        target_path: Path,
        predicate: str
    ) -> bool:
        """
        Strengthen a relationship between two memories, updating YAML frontmatter quickly.
        """
        try:
            source_note, target_note = await asyncio.gather(
                self.vault.get_note(source_path),
                self.vault.get_note(target_path)
            )

            if not source_note or not target_note:
                return False

            relationships = source_note.metadata.yaml_frontmatter.get("Relationships", [])
            relationship_str = f"#{predicate} [[{target_note.title}]]"
            if relationship_str not in relationships:
                relationships.append(relationship_str)

            metadata = source_note.metadata.yaml_frontmatter
            metadata["Relationships"] = relationships
            metadata["Date_modified"] = datetime.now().isoformat()

            # Update the note. For speed, assume full replacement with new YAML is okay.
            return await self.vault.update_note(
                path=source_path,
                content=source_note.content,
                mode="replace"
            )
        except Exception as e:
            print(f"[MemoryManager] Error strengthening relationship: {e}", file=sys.stderr)
            return False

    async def search_relevant_memories(
        self,
        query: str,
        threshold: float = 60.0
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant memories using rapidfuzz for faster fuzzy matching.
        Minimizes loops and does direct lookups to speed up matching.

        Steps:
        1. Fetch all memory notes once.
        2. Use rapidfuzz.process.extract to get matches above threshold.
        """
        try:
            all_notes = await self.vault.get_all_notes()
            # Filter memory notes
            memory_notes = [n for n in all_notes if "memory/" in str(n.path)]
            # Create a dict for quick lookup by title
            memory_map = {n.title: n for n in memory_notes}

            # Extract titles and perform fuzzy matching
            titles = list(memory_map.keys())
            matches = process.extract(query, titles, scorer=fuzz.partial_ratio, limit=None)

            # Filter by threshold and build results
            relevant_memories = []
            for (title, score, _) in matches:
                if score >= threshold:
                    note = memory_map[title]
                    content = note.content
                    preview = content[:200] + "..." if len(content) > 200 else content
                    relevant_memories.append({
                        "title": title,
                        "path": str(note.path),
                        "preview": preview,
                        "metadata": note.metadata.yaml_frontmatter
                    })

            # Sort by score descending
            relevant_memories.sort(key=lambda x: x["metadata"].get("Date_modified", ""), reverse=True)
            return relevant_memories
        except Exception as e:
            print(f"[MemoryManager] Error searching memories: {e}", file=sys.stderr)
            return []

"""
Search module for efficient fuzzy searching within the Obsidian vault.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
from rapidfuzz import fuzz, process
import time

@dataclass
class SearchResult:
    """Represents a single search result."""
    title: str
    file_path: Path
    score: float
    preview: str

@dataclass
class IndexEntry:
    """Represents an indexed file."""
    title: str
    file_path: Path
    content: str
    last_modified: float

class SearchEngine:
    """Handles fuzzy searching within the Obsidian vault with indexing."""

    def __init__(self, vault: VaultManager):
        """Initialize search engine with vault path."""
        self.vault = vault
        self.index = []
        self._template_dirs = ['templates', '📜 templates']  # Directories to skip

    def _should_skip_file(self, path: Path) -> bool:
        """Check if file should be skipped during indexing."""
        path_str = str(path).lower()
        return any(tdir in path_str.lower() for tdir in self._template_dirs)

    async def build_index(self):
        """Build the search index by indexing all notes in the vault."""
        try:
            print("[Search] Building search index...", file=sys.stderr)
            notes = await self.vault.get_all_notes()
            indexed_count = 0
            skipped_count = 0
            self.index = []
            
            for note in notes:
                try:
                    if self._should_skip_file(note.path):
                        skipped_count += 1
                        continue
                        
                    self.index.append((note.title, note.content))
                    indexed_count += 1
                    
                except Exception as e:
                    skipped_count += 1
                    if not self._should_skip_file(note.path):
                        print(f"[Search] Error indexing '{note.path}': {e}", file=sys.stderr)
            
            print(f"[Search] Index built: {indexed_count} files indexed, {skipped_count} files skipped", file=sys.stderr)
        except Exception as e:
            print(f"[Search] Error building search index: {e}", file=sys.stderr)

    async def search(self, query: str, threshold: int = 60, max_results: int = 10) -> List[Dict[str, Any]]:
        titles = [title for (title, _) in self.index]
        matches = process.extract(query, titles, scorer=fuzz.partial_ratio, limit=max_results)
        results = []
        for (match_title, score, idx) in matches:
            if score >= threshold:
                content = self.index[idx][1]
                preview = content[:200] + "..." if len(content) > 200 else content
                results.append({
                    "title": match_title,
                    "score": score,
                    "content": preview
                })
        return results
