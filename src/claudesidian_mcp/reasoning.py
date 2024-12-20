# src/claudesidian_mcp/reasoning.py

"""
Reasoning module for handling saving and retrieving reasoning schemas.
Stores reasoning documents in the reasoning folder.
"""

import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
import aiofiles

from .vault import VaultManager

class ReasoningManager:
    """Manages saving and retrieving reasoning schemas in the vault."""

    def __init__(self, vault: VaultManager):
        self.vault = vault
        self._reasoning_folder = Path("claudesidian/reasoning")
        self._index_path = self.vault.vault_path / "claudesidian" / "index.md"
        print("ReasoningManager initialized", file=sys.stderr)

    async def create_reasoning(
        self,
        title: str,
        description: str,
        reasoning_schema: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new reasoning document with minimal frontmatter and structured content.
        """
        try:
            print(f"[Reasoning] Creating new reasoning document", file=sys.stderr)
            await self.vault.ensure_folder(self.vault.vault_path / self._reasoning_folder)

            filename = f"{int(time.time())}_{title}.md"
            reasoning_path = self._reasoning_folder / filename

            # Extract minimal frontmatter data
            frontmatter = {
                "title": title,
                "description": description,
                "query": reasoning_schema.get("Query", "")
            }

            # Convert the rest of the schema to formatted markdown content
            content = self._format_reasoning_content(reasoning_schema)

            # Combine frontmatter and content
            yaml_frontmatter = yaml.dump(frontmatter, default_flow_style=False)
            full_content = f"---\n{yaml_frontmatter}---\n\n{content}"

            note = await self.vault.create_note(
                path=reasoning_path,
                content=full_content
            )

            if note:
                await self._update_index(title, description)
                relative_path = reasoning_path.as_posix()
                return {
                    "title": note.title,
                    "path": relative_path,
                    "content": full_content
                }

            print(f"[Reasoning] Failed to save reasoning document", file=sys.stderr)
            return None

        except Exception as e:
            print(f"[Reasoning] Error saving reasoning: {e}", file=sys.stderr)
            return None

    def _format_reasoning_content(self, schema: Dict[str, Any]) -> str:
        """Format reasoning schema into markdown content."""
        sections = []

        # Persona Section
        if "Persona" in schema:
            persona = schema["Persona"]
            sections.append("# Persona\n")
            
            if "Attributes" in persona:
                sections.append("## Attributes")
                sections.extend(f"- {attr}" for attr in persona["Attributes"])
                sections.append("")
            
            if "Expertise" in persona:
                sections.append("## Expertise")
                exp = persona["Expertise"]
                sections.extend([
                    f"- Domain: {exp.get('Domain', '')}",
                    f"- Specialization: {exp.get('Specialization', '')}",
                    f"- Reasoning: {exp.get('Reasoning', '')}",
                    ""
                ])
            
            if "Preferences" in persona:
                sections.append("## Preferences")
                sections.extend(f"- {pref}" for pref in persona["Preferences"])
                sections.append("")

        # Working Memory Section
        if "WorkingMemory" in schema:
            wm = schema["WorkingMemory"]
            sections.extend([
                "# Working Memory\n",
                f"**Goal**: {wm.get('Goal', '')}\n",
                f"**Subgoal**: {wm.get('Subgoal', '')}\n",
                f"**Context**: {wm.get('Context', '')}\n",
                f"**State**: {wm.get('State', '')}\n",
            ])
            
            if "Progress" in wm:
                sections.append("\n## Progress")
                for step in wm["Progress"]:
                    sections.extend([
                        f"### {step['Step']}",
                        f"Status: {step['Status']}",
                        f"Next Steps: {step['NextSteps']}",
                        ""
                    ])

        # Knowledge Graph Section
        if "KnowledgeGraph" in schema:
            sections.append("# Knowledge Graph\n")
            for node in schema["KnowledgeGraph"]:
                # Only convert predicate to snake_case, keep subject and object as is
                subject = node['Subject']  # Keep original form
                predicate = node['Predicate'].lower().replace(' ', '_')  # Convert predicate to snake_case
                obj = node['Object']  # Keep original form
                sections.append(f"- [[{subject}]] #{predicate} [[{obj}]]")
            sections.append("")

        # Reasoning Section
        if "Reasoning" in schema:
            r = schema["Reasoning"]
            sections.append("# Reasoning Process\n")
            
            if "Propositions" in r:
                sections.extend([
                    "## Propositions",
                    f"Methodology: {r['Propositions']['Methodology']}\n",
                    "### Steps"
                ])
                # Fix step numbering by using enumerate
                for i, step in enumerate(r['Propositions']['Steps'], 1):
                    sections.append(f"{i}. {step}")
                sections.append("")
            
            if "Critiques" in r:
                sections.append("## Critiques")
                for critique in r["Critiques"]:
                    sections.extend([
                        f"### {critique['Type']}",
                        f"Question: {critique['Question']}",
                        f"Impact: {critique['Impact']}",
                        ""
                    ])
            
            if "Reflections" in r:
                sections.append("## Reflections")
                for ref in r["Reflections"]:
                    sections.extend([
                        f"### {ref['Focus']}",
                        f"Question: {ref['Question']}",
                        f"MetaCognition: {ref['MetaCognition']}",
                        ""
                    ])

        return "\n".join(sections)

    async def _update_index(self, title: str, description: str) -> None:
        """Update the index file with a new reasoning entry."""
        try:
            async with aiofiles.open(self._index_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
                lines = content.splitlines()
                
                # Find the Reasoning section
                for i, line in enumerate(lines):
                    if line.strip() == "## Reasoning":
                        # Insert new entry after the header
                        lines.insert(i + 1, f"[[{title}]] - {description}")
                        break

            # Write back the updated content
            async with aiofiles.open(self._index_path, mode='w', encoding='utf-8') as f:
                await f.write('\n'.join(lines))
        except Exception as e:
            print(f"[ReasoningManager] Error updating index: {e}", file=sys.stderr)

    async def get_last_reasoning(self) -> Optional[Dict[str, Any]]:
        """Get the most recent reasoning document."""
        try:
            reasoning_folder = self._reasoning_folder
            full_path = self.vault.vault_path / reasoning_folder
            if not full_path.exists():
                return None

            files = list(full_path.glob("*.md"))
            if not files:
                return None

            latest_file = max(files, key=lambda x: x.stat().st_mtime)
            note = await self.vault.get_note(latest_file.relative_to(self.vault.vault_path))

            if note:
                return {
                    "title": note.title,
                    "path": str(note.path),
                    "content": note.content
                }

            return None

        except Exception as e:
            print(f"[Reasoning] Error getting last reasoning: {e}", file=sys.stderr)
            return None
