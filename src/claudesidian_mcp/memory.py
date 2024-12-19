"""
Memory management module for handling memory creation, updates, and retrieval.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .vault import VaultManager

class MemoryManager:
    """Manages memory operations using the vault as a backing store."""
    
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
        """Create a new memory entry."""
        
        try:
            # Prepare metadata
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

            # Create the note with YAML frontmatter
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
            print(f"Error creating memory: {e}")
            
        return None

    async def strengthen_relationship(
        self,
        source_path: Path,
        target_path: Path,
        predicate: str
    ) -> bool:
        """Strengthen a relationship between two memories."""
        try:
            # Get both notes
            source_note = await self.vault.get_note(source_path)
            target_note = await self.vault.get_note(target_path)
            
            if not source_note or not target_note:
                return False

            # Extract current relationships
            relationships = source_note.metadata.yaml_frontmatter.get("Relationships", [])
            
            # Find or create relationship
            relationship_str = f"#{predicate} [[{target_note.title}]]"
            if relationship_str not in relationships:
                relationships.append(relationship_str)

            # Update the note with new relationships
            metadata = source_note.metadata.yaml_frontmatter
            metadata["Relationships"] = relationships
            metadata["Date_modified"] = datetime.now().isoformat()

            # Write back to file with updated metadata
            return await self.vault.update_note(
                path=source_path,
                content=source_note.content,
                mode="replace"
            )

        except Exception as e:
            print(f"Error strengthening relationship: {e}")
            return False

    async def search_relevant_memories(
        self,
        query: str,
        threshold: float = 60.0
    ) -> List[Dict[str, Any]]:
        """Search for relevant memories using fuzzy matching."""
        try:
            # Get all memory notes
            notes = await self.vault.get_all_notes()
            memories = []

            for note in notes:
                # Only process files in the memory folder
                if not str(note.path).startswith("memory/"):
                    continue

                # Calculate relevance (simple contains for now)
                if query.lower() in note.content.lower():
                    memories.append({
                        "title": note.title,
                        "path": str(note.path),
                        "preview": note.content[:200] + "..." if len(note.content) > 200 else note.content,
                        "metadata": note.metadata.yaml_frontmatter
                    })

            return sorted(memories, key=lambda x: len(x["preview"]), reverse=True)

        except Exception as e:
            print(f"Error searching memories: {e}")
            return []
