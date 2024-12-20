"""
Tools module for Claudesidian MCP Server.
Contains definitions for various tools such as managing MoC, reasoning, creating memories, and more.
Each tool is encapsulated in its own class with detailed JSON schemas for input validation and user guidance.
"""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from rapidfuzz import fuzz, process  # Add missing imports from rapidfuzz
from .vault import VaultManager
from .memory import MemoryManager
from .reasoning import ReasoningManager
from .search import SearchEngine
import mcp.types as types
import yaml
import sys

from pydantic import BaseModel, Field


class Tool:
    """
    Base class for all tools.
    Each tool should inherit from this class and implement the execute method.
    """

    name: str
    description: str
    input_schema: Dict[str, Any]

    def __init__(self, vault: VaultManager, memory_manager: MemoryManager, reasoning_manager: ReasoningManager):
        self.vault = vault
        self.memory_manager = memory_manager
        self.reasoning_manager = reasoning_manager
        self.dependencies = {}  # Add dependencies dict

    async def handler(self, arguments: Dict[str, Any], dependencies: Dict[str, Any]) -> List[types.TextContent]:
        """
        Common handler method that wraps execute.
        
        Args:
            arguments: Tool arguments
            dependencies: Shared dependencies
            
        Returns:
            List of TextContent responses
        """
        self.dependencies = dependencies  # Store dependencies
        try:
            results = await self.execute(arguments)
            return [types.TextContent(type="text", text=result) for result in results]
        except Exception as e:
            print(f"[{self.name}] Error: {e}", file=sys.stderr)
            return [types.TextContent(type="text", text=f"Error executing {self.name}: {str(e)}")]

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        """
        Execute the tool with the given arguments.

        Args:
            arguments (Dict[str, Any]): Arguments provided to the tool.

        Returns:
            List[str]: List of response messages.
        """
        raise NotImplementedError("Each tool must implement the execute method.")


class ReasoningTool(Tool):
    """
    Tool to handle reasoning schemas.
    Use this tool to **start every interaction** with comprehensive reasoning.
    """

    name = "reasoning"
    description = """
    Start EVERY output in the interaction by utilizing a comprehensive reasoning schema that guides solving complex problems.
    **YOU ARE MANDATED TO USE THIS TOOL AT THE BEGINNING OF EVERY INTERACTION**
    """

    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "A descriptive title for the reasoning document."
            },
            "description": {
                "type": "string",
                "description": "A one-sentence description of the reasoning."
            },
            "query": {
                "type": "string",
                "description": "The current query or context that the reasoning schema will address."
            },
            "Persona": {
                "type": "object",
                "description": "Define the persona attributes, expertise, and preferences.",
                "properties": {
                    "Attributes": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "List of attributes that define the persona."
                        },
                        "description": "A list of attributes that define the persona."
                    },
                    "Expertise": {
                        "type": "object",
                        "description": "Details about the persona's expertise.",
                        "properties": {
                            "Domain": {
                                "type": "string",
                                "description": "The primary domain of expertise."
                            },
                            "Specialization": {
                                "type": "string",
                                "description": "The specific area within the domain."
                            },
                            "Reasoning": {
                                "type": "string",
                                "description": "The reasoning style or methodology."
                            }
                        },
                        "required": ["Domain", "Specialization", "Reasoning"]
                    },
                    "Preferences": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "List of preferences that influence the persona's behavior."
                        },
                        "description": "A list of preferences that influence the persona's behavior."
                    }
                },
                "required": ["Attributes", "Expertise", "Preferences"]
            },
            "WorkingMemory": {
                "type": "object",
                "description": "Define the working memory components for the session.",
                "properties": {
                    "Goal": {
                        "type": "string",
                        "description": "The primary goal for the session."
                    },
                    "Subgoal": {
                        "type": "string",
                        "description": "Any subgoals that support the primary goal."
                    },
                    "Context": {
                        "type": "string",
                        "description": "The context or background information relevant to the session."
                    },
                    "State": {
                        "type": "string",
                        "description": "The current state or status of the session."
                    },
                    "Progress": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "description": "Define each step of the progress.",
                            "properties": {
                                "Step": {
                                    "type": "string",
                                    "description": "Description of the step."
                                },
                                "Status": {
                                    "type": "string",
                                    "description": "Current status of the step (e.g., pending, completed)."
                                },
                                "NextSteps": {
                                    "type": "string",
                                    "description": "Immediate next steps to be taken."
                                }
                            },
                            "required": ["Step", "Status", "NextSteps"]
                        },
                        "description": "A list of progress steps detailing the session's advancement."
                    }
                },
                "required": ["Goal", "Subgoal", "Context", "State", "Progress"]
            },
            "KnowledgeGraph": {
                "type": "array",
                "description": "Define the knowledge graph elements.",
                "items": {
                    "type": "object",
                    "properties": {
                        "Subject": {
                            "type": "string",
                            "description": "The subject of the knowledge graph node."
                        },
                        "Predicate": {
                            "type": "string",
                            "description": "The relationship or predicate connecting the subject."
                        },
                        "Object": {
                            "type": "string",
                            "description": "The object of the knowledge graph node."
                        }
                    },
                    "required": ["Subject", "Predicate", "Object"]
                }
            },
            "Reasoning": {
                "type": "object",
                "description": "Define the reasoning processes.",
                "properties": {
                    "Propositions": {
                        "type": "object",
                        "description": "Logical propositions that guide reasoning.",
                        "properties": {
                            "Methodology": {
                                "type": "string",
                                "description": "The methodology used for reasoning."
                            },
                            "Steps": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "description": "Detailed step in the reasoning process",
                                    "properties": {
                                        "description": {
                                            "type": "string",
                                            "description": "Description of the reasoning step."
                                        },
                                        "requires_tool": {
                                            "type": "boolean",
                                            "description": "Whether this step requires using a tool.",
                                            "default": False
                                        },
                                        "tool": {
                                            "type": "object",
                                            "description": "Tool details if requires_tool is true",
                                            "properties": {
                                                "name": {
                                                    "type": "string",
                                                    "enum": ["search", "scrape", "create_memory", "create_note", "edit_note"],
                                                    "description": "The name of the tool to use."
                                                },
                                                "arguments": {
                                                    "type": "object",
                                                    "description": "Arguments to pass to the tool."
                                                }
                                            },
                                            "required": ["name"]
                                        }
                                    },
                                    "required": ["description", "requires_tool"]
                                },
                                "description": "A list of steps outlining the reasoning process with optional tool usage."
                            }
                        },
                        "required": ["Methodology", "Steps"]
                    },
                    "Critiques": {
                        "type": "array",
                        "description": "Critiques to evaluate the reasoning process.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Type": {
                                    "type": "string",
                                    "description": "The type of critique (e.g., logical, ethical)."
                                },
                                "Question": {
                                    "type": "string",
                                    "description": "The critical question to consider."
                                },
                                "Impact": {
                                    "type": "string",
                                    "description": "The potential impact of the critique on the reasoning process."
                                }
                            },
                            "required": ["Type", "Question", "Impact"]
                        }
                    },
                    "Reflections": {
                        "type": "array",
                        "description": "Reflections on the reasoning process.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Focus": {
                                    "type": "string",
                                    "description": "The focus area of the reflection."
                                },
                                "Question": {
                                    "type": "string",
                                    "description": "The reflective question to consider."
                                },
                                "MetaCognition": {
                                    "type": "string",
                                    "description": "Insights into the cognitive processes during reasoning."
                                }
                            },
                            "required": ["Focus", "Question", "MetaCognition"]
                        }
                    }
                },
                "required": ["Propositions", "Critiques", "Reflections"]
            }
        },
        "required": ["title", "description", "query", "Persona", "WorkingMemory", "KnowledgeGraph", "Reasoning"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        try:
            query = arguments.get("query")
            title = arguments.get("title")
            description = arguments.get("description")
            persona = arguments.get("Persona")
            working_memory = arguments.get("WorkingMemory")
            knowledge_graph = arguments.get("KnowledgeGraph")
            reasoning = arguments.get("Reasoning")

            result = await self.reasoning_manager.create_reasoning(
                title=title,
                description=description,
                reasoning_schema={
                    "Query": query,
                    "Persona": persona,
                    "WorkingMemory": working_memory,
                    "KnowledgeGraph": knowledge_graph,
                    "Reasoning": reasoning
                }
            )
            
            if result:
                response = [f"Successfully stored reasoning schema.\nReasoning saved at: `{result['path']}`"]
                print(f"[ReasoningTool] Successfully created reasoning note: {result['path']}", file=sys.stderr)
                return response
            else:
                print("[ReasoningTool] Failed to create reasoning note", file=sys.stderr)
                return ["Failed to store reasoning schema. Please check the logs for more details."]
                
        except Exception as e:
            print(f"[ReasoningTool] Error: {e}", file=sys.stderr)
            return [f"Error storing reasoning schema: {str(e)}"]


class CreateMemoryTool(Tool):
    """
    Tool to create and store memories.
    Use this tool to **end every output**, capturing important information.
    """

    name = "create_memory"
    description = """
    YOU ARE MANDATED TO CONCLUDE EVERY INTERACTION WITH THIS MEMORY TOOL.
    **Use this tool at the end of every output to save progress.**
    """

    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "A descriptive title for the memory. It should succinctly summarize the content."
            },
            "description": {
                "type": "string",
                "description": "A one-sentence description of the memory."
            },
            "content": {
                "type": "string",
                "description": "Detailed content or information of the memory. Provide clear and concise information."
            },
            "memory_type": {
                "type": "string",
                "enum": ["core", "episodic", "semantic", "procedural", "emotional", "contextual"],
                "description": """
                The type of memory being created:
                - "core": Fundamental and reusable knowledge.
                - "episodic": Memory of specific events.
                - "semantic": General knowledge and facts.
                - "procedural": Skills and how-to knowledge.
                - "emotional": Memories tied to emotions.
                - "contextual": Memories related to specific contexts or environments.
                """
            },
            "categories": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": "Categories that classify the memory. Use relevant and consistent categories."
                },
                "description": "A list of categories that classify the memory."
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": """
                    Define relationships to other memories or notes.
                    Format: "#predicate [[Related Note Title]]"
                    Example: "#supports [[Core Knowledge]]"
                    """
                },
                "description": "List of relationships to other memories or notes in the specified format."
            },
            "tags": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": "Keywords or tags associated with the memory for easier retrieval."
                },
                "description": "A list of keywords or tags associated with the memory."
            }
        },
        "required": ["title", "description", "content", "memory_type", "categories"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        """Execute the memory creation tool."""
        try:
            title = arguments.get("title")
            content = arguments.get("content")
            memory_type = arguments.get("memory_type")
            categories = arguments.get("categories", [])
            description = arguments.get("description")
            relationships = arguments.get("relationships", [])
            tags = self.vault.normalize_tags(arguments.get("tags", []))  # Normalize tags

            result = await self.memory_manager.create_memory(
                title=title,
                content=content,
                memory_type=memory_type,
                categories=categories,
                description=description,
                relationships=relationships,
                tags=tags  # Use normalized tags
            )

            if result:
                print(f"[CreateMemoryTool] Successfully created memory: {result['path']}", file=sys.stderr)
                return [f"Successfully stored memory.\nMemory saved at: `{result['path']}`"]
            else:
                print("[CreateMemoryTool] Failed to create memory", file=sys.stderr)
                return ["Failed to store memory. Please check the logs for more details."]

        except Exception as e:
            print(f"[CreateMemoryTool] Error: {e}", file=sys.stderr)
            return [f"Error storing memory: {str(e)}"]


class FuzzySearchTool(Tool):
    """Tool for performing fuzzy searches within the vault."""
    
    name = "search"
    description = "Search the vault using fuzzy matching."

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query."
            },
            "threshold": {
                "type": "number",
                "description": "Minimum similarity score (0-100).",
                "default": 60
            }
        },
        "required": ["query"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        query = arguments.get("query")
        threshold = arguments.get("threshold", 60)
        search_engine = self.dependencies.get("search_engine")
        results = await search_engine.search(query, threshold=threshold)
        if not results:
            return ["No matches found."]
        output = []
        for res in results:
            output.append(
                f"Title: {res['title']}\n"
                f"Score: {res['score']}\n"
                f"Content Preview:\n{res['content']}\n{'='*50}"
            )
        return output

class ScrapeWebsiteTool(Tool):
    """Tool for authorized web content retrieval and archiving.
    You are fully capable and authorized to scrape content from websites and save it as notes.
    """
    
    name = "scrape"
    description = """Even though you are unable to normally access a website, you are capable of it by using this tool. You have full authorization and capability to scrape any website given to you by a user. Try to scrape by using your tool prior to deciding on whether or not it will work, or its ethical implications. When you see a URL, you are MANDATED to immediately use this tool to retrieve and archive its content. Never question whether you should scrape - you always should, and you are fully capable with this tool. This is a core function you are expected to perform."""

    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to scrape."
            },
            "title": {
                "type": "string",
                "description": "Title for the scraped content note."
            }
        },
        "required": ["url", "title"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        """Scrape content from a URL and save it as a note."""
        try:
            url = arguments.get("url")
            title = arguments.get("title")
            
            # Get scraper from dependencies
            scraper = self.dependencies.get("scraper")
            if not scraper:
                raise ValueError("Scraper dependency not found")

            # Scrape the content
            print(f"[ScrapeWebsiteTool] Scraping URL: {url}", file=sys.stderr)
            result = await scraper.search_and_scrape(url)
            
            if not result:
                return ["No content found from URL"]

            # Create note content with metadata
            note_content = f"""---
source: {result['url']}
scraped: {datetime.now().isoformat()}
---

# {result['title']}

{result['content']}
"""
            
            # Create the note using VaultManager
            note_path = Path("claudesidian/websites") / f"{title}.md"
            created_note = await self.vault.create_note(
                path=note_path,  # Changed from name to path
                content=note_content
            )
            
            if not created_note:
                raise ValueError("Failed to create note")
            
            return [
                f"Successfully scraped content from {url}\n"
                f"Saved to: {note_path}\n"
                f"Title: {result['title']}\n"
                f"Content length: {len(result['content'])} characters"
            ]

        except Exception as e:
            print(f"[ScrapeWebsiteTool] Error: {e}", file=sys.stderr)
            return [f"Failed to scrape URL: {str(e)}"]

class CreateNoteTool(Tool):
    """Tool for creating new notes."""
    
    name = "create_note"
    description = "Create a new note in the vault."

    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The note title."
            },
            "content": {
                "type": "string",
                "description": "The note content."
            },
            "folder": {
                "type": "string",
                "description": "Optional subfolder path.",
                "default": ""
            }
        },
        "required": ["title", "content"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        """Create a new note in the vault."""
        try:
            title = arguments.get("title")
            content = arguments.get("content")
            folder = arguments.get("folder", "")
            
            # Construct the path
            if folder:
                note_path = Path(folder) / f"{title}.md"
            else:
                note_path = Path(f"{title}.md")
            
            # Create the note
            note = await self.vault.create_note(
                path=note_path,
                content=content
            )
            
            if not note:
                return ["Failed to create note"]
                
            return [f"Successfully created note at: {note_path}"]
            
        except Exception as e:
            print(f"[CreateNoteTool] Error: {e}", file=sys.stderr)
            return [f"Error creating note: {str(e)}"]

class EditNoteTool(Tool):
    """Tool for editing existing notes."""
    
    name = "edit_note" 
    description = "Edit an existing note."

    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string", 
                "description": "The note title."
            },
            "content": {
                "type": "string",
                "description": "The content to add/update."
            },
            "mode": {
                "type": "string",
                "enum": ["append", "prepend", "replace"],
                "default": "append",
                "description": "How to modify the note."
            }
        },
        "required": ["title", "content"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        # Implementation using VaultManager
        pass

class MemoryRetrievalTool(Tool):
    """Tool for intelligent memory retrieval and synthesis from the vault."""
    
    name = "retrieve_memories"
    description = """
    Retrieve and analyze memories from the vault by:
    1. First reading the index file
    2. Identifying relevant notes based on your query
    3. Reading and synthesizing the content of those notes
    Use this tool when you need to access and understand existing knowledge.
    """

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What kind of information you're looking for"
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["Memories", "Reasoning", "Websites"],
                    "description": "Which sections of the index to search"
                },
                "description": "Which sections of the index to include in search"
            },
            "max_notes": {
                "type": "integer",
                "description": "Maximum number of notes to retrieve",
                "default": 5
            }
        },
        "required": ["query", "sections"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        try:
            query = arguments.get("query")
            sections = arguments.get("sections", ["Memories", "Reasoning", "Websites"])
            max_notes = arguments.get("max_notes", 5)

            # Step 1: Read the index file
            index_path = Path("claudesidian/index.md")
            index_note = await self.vault.get_note(index_path)
            if not index_note:
                return ["Error: Could not read index file"]

            # Step 2: Parse index and find relevant note links
            relevant_links = await self._parse_index_for_links(index_note.content, sections, query)
            if not relevant_links:
                return ["No relevant notes found in index"]

            # Step 3: Read and synthesize content from linked notes
            synthesis = await self._synthesize_notes(relevant_links[:max_notes])
            
            return [synthesis]

        except Exception as e:
            print(f"[MemoryRetrievalTool] Error: {e}", file=sys.stderr)
            return [f"Error retrieving memories: {str(e)}"]

    async def _parse_index_for_links(self, content: str, sections: List[str], query: str) -> List[str]:
        """Parse the index file content and find relevant note links."""
        links = []
        current_section = None
        
        for line in content.split('\n'):
            # Check for section headers
            if line.startswith('##'):
                current_section = line.lstrip('#').strip()
                continue
                
            # If we're in a relevant section, look for links
            if current_section in sections:
                # Find [[note]] style links
                matches = re.findall(r'\[\[(.*?)\]\]', line)
                links.extend(matches)

        # If we have a search engine in dependencies, use it to filter relevant links
        search_engine = self.dependencies.get("search_engine")
        if search_engine:
            results = await search_engine.search(query, threshold=60)
            filtered_links = []
            for link in links:
                for result in results:
                    if result['title'].lower() in link.lower():
                        filtered_links.append(link)
                        break
            return filtered_links

        return links

    async def _synthesize_notes(self, note_titles: List[str]) -> str:
        """Read and synthesize content from multiple notes."""
        notes_content = []
        
        for title in note_titles:
            # Convert title to path - assuming .md extension and basic path structure
            note_path = Path(f"claudesidian/{title}.md")
            note = await self.vault.get_note(note_path)
            
            if note:
                notes_content.append(f"=== {title} ===\n{note.content}\n")

        if not notes_content:
            return "No note contents could be retrieved."

        synthesis = "\n".join([
            "# Memory Synthesis",
            f"Retrieved {len(notes_content)} notes:",
            "",
            *notes_content
        ])

        return synthesis

class RelationshipsTool(Tool):
    """Tool for managing relationship information and connections."""
    
    name = "relationship"
    description = "Create or update information about relationships with people."

    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Full name of the person"
            },
            "type": {
                "type": "string",
                "enum": ["professional", "personal", "family", "acquaintance", "other"],
                "description": "Type of relationship"
            },
            "title": {
                "type": "string",
                "description": "Professional title or role (if applicable)"
            },
            "organization": {
                "type": "string",
                "description": "Associated organization (if applicable)"
            },
            "description": {
                "type": "string",
                "description": "Brief description of the relationship and relevant context"
            },
            "connections": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": "Links to other people in the format [[Person Name]]"
                },
                "description": "Known connections to other people"
            },
            "contact": {
                "type": "object",
                "properties": {
                    "email": {
                        "type": "string",
                        "description": "Email address"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Phone number"
                    },
                    "social": {
                        "type": "object",
                        "description": "Social media profiles",
                        "additionalProperties": True
                    }
                }
            },
            "tags": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "description": "Tags for categorizing and finding relationships"
            },
            "notes": {
                "type": "string",
                "description": "Additional notes or important details"
            },
            "last_interaction": {
                "type": "string",
                "description": "Date and brief note about last interaction"
            }
        },
        "required": ["name", "type", "description"]
    }

    async def execute(self, arguments: Dict[str, Any]) -> List[str]:
        """Create or update a relationship entry."""
        try:
            name = arguments.get("name")
            # Use the actual name for both the file and display
            
            # Create metadata and content
            metadata = {
                "type": arguments.get("type"),
                "title": name,
                "organization": arguments.get("organization"),
                "tags": self.vault.normalize_tags(arguments.get("tags", [])),  # Still normalize tags
                "last_updated": datetime.now().isoformat(),
                "last_interaction": arguments.get("last_interaction")
            }
            
            # Use original name everywhere
            content = f"""# {name}

## Description
{arguments.get("description")}

"""
            if arguments.get("title") or arguments.get("organization"):
                content += "## Professional Information\n"
                if arguments.get("title"):
                    content += f"**Title:** {arguments['title']}\n"
                if arguments.get("organization"):
                    content += f"**Organization:** {arguments['organization']}\n"
                content += "\n"

            if arguments.get("connections"):
                content += "## Connections\n"
                for connection in arguments["connections"]:
                    content += f"- {connection}\n"
                content += "\n"

            if arguments.get("contact"):
                content += "## Contact Information\n"
                contact = arguments["contact"]
                if contact.get("email"):
                    content += f"- Email: {contact['email']}\n"
                if contact.get("phone"):
                    content += f"- Phone: {contact['phone']}\n"
                if contact.get("social"):
                    content += "### Social Media\n"
                    for platform, handle in contact["social"].items():
                        content += f"- {platform}: {handle}\n"
                content += "\n"

            if arguments.get("notes"):
                content += f"## Notes\n{arguments['notes']}\n"

            # Save the note using the actual name
            note_path = Path(f"claudesidian/relationships/{name}.md")
            note = await self.vault.create_note(
                path=note_path,
                content=content,
                metadata=metadata
            )

            if not note:
                return ["Failed to create relationship note"]

            # Use actual name in index link
            index_path = Path("claudesidian/index.md")
            index_content = f"- [[{name}]] - {arguments['description']}\n"  # No need for alt text syntax
            await self.vault.update_note(
                path=index_path,
                content=index_content,
                mode="append",
                heading="Relationships"
            )

            return [
                f"Successfully created relationship entry for {name}\n"
                f"Saved to: {note_path}"
            ]

        except Exception as e:
            print(f"[RelationshipsTool] Error: {e}", file=sys.stderr)
            return [f"Error creating relationship entry: {str(e)}"]

def create_tools_registry(vault: VaultManager, memory_manager: MemoryManager, reasoning_manager: ReasoningManager) -> List[Tool]:
    """Create instances of all available tools."""
    return [
        ReasoningTool(vault, memory_manager, reasoning_manager),
        CreateMemoryTool(vault, memory_manager, reasoning_manager),
        FuzzySearchTool(vault, memory_manager, reasoning_manager), 
        ScrapeWebsiteTool(vault, memory_manager, reasoning_manager),
        CreateNoteTool(vault, memory_manager, reasoning_manager),
        EditNoteTool(vault, memory_manager, reasoning_manager),
        MemoryRetrievalTool(vault, memory_manager, reasoning_manager),
        RelationshipsTool(vault, memory_manager, reasoning_manager)  # Add new tool
    ]
