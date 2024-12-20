"""
Memory management module optimized for speed.
Uses rapidfuzz for fuzzy matching instead of fuzzywuzzy, minimizes overhead.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz, process
import aiofiles

from .vault import VaultManager

class MemoryManager:
    """Manages memory operations using the vault as a backing store quickly and efficiently."""

    def __init__(self, vault: VaultManager):
        self.vault = vault
        self._memory_folder = Path("claudesidian/memory")
        self._index_path = self.vault.vault_path / "claudesidian" / "index.md"
        print("MemoryManager initialized", file=sys.stderr)

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

            memory_path = self._memory_folder / f"{title}.md"

            note = await self.vault.create_note(
                path=memory_path,
                content=content,
                metadata=metadata
            )

            if note:
                await self._update_index(title, description)
                return {
                    "title": note.title,
                    "path": str(note.path),
                    "metadata": note.metadata.yaml_frontmatter
                }
        except Exception as e:
            print(f"[MemoryManager] Error creating memory: {e}", file=sys.stderr)

        return None

    async def _update_index(self, title: str, description: str) -> None:
        """Update the index file with a new memory entry."""
        try:
            async with aiofiles.open(self._index_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                lines = content.splitlines()
                
                # Find the Memories section
                for i, line in enumerate(lines):
                    if line.strip() == "## Memories":
                        # Insert new entry after the header
                        lines.insert(i + 1, f"[[{title}]] - {description}")
                        break

            # Write back the updated content
            async with aiofiles.open(self._index_path, mode='w', encoding='utf-8') as f:
                await f.write('\n'.join(lines))
        except Exception as e:
            print(f"[MemoryManager] Error updating index: {e}", file=sys.stderr)

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
            print(f"[MemoryManager] Error strengthening relationship: {e}")
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
        1. Fetch all notes once.
        2. Filter memory notes quickly.
        3. Use rapidfuzz.process.extract to get matches above threshold.
        """
        try:
            notes = await self.vault.get_all_notes()
            # Filter memory notes once
            memory_notes = [n for n in notes if "memory/" in str(n.path)]
            # Create a dict for quick lookup by title
            memory_map = {n.title: n for n in memory_notes}

            # Extract keys and run a single fuzzy search
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

            # Sort by title for consistency
            return sorted(relevant_memories, key=lambda x: x["title"])
        except Exception as e:
            print(f"[MemoryManager] Error searching memories: {e}")
            return []

    async def create_memory_from_results(self, results: Any) -> None:
        """
        Conclude the interaction by storing the results into memory.
        """
        # Implementation to create memory notes from results
        # ...code to process results and save to memory...
