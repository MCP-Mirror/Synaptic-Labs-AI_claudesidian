# File: claudesidian/utils/path_resolver.py

"""
Smart path resolution for Claudesidian.
Handles intelligent path finding and resolution based on context and patterns.
"""

import os
import re
from datetime import datetime
from typing import List, Optional, Dict, Set, Tuple
from pathlib import Path
import logging
from functools import lru_cache

from fuzzywuzzy import fuzz
import yaml

logger = logging.getLogger(__name__)

class PathResolver:
    """
    Smart path resolution for vault operations.
    Uses context and patterns to find the most appropriate paths.
    """
    
    # Common patterns for different note types
    DAILY_NOTES_PATTERNS = [
        "Daily Notes",
        "Dailies",
        "Journal",
        "Periodic/Daily",
        r"\d{4}/Daily",
        "Daily/*"
    ]
    
    PROJECT_PATTERNS = [
        "Projects",
        "Project Notes",
        r"\d{4}/Projects"
    ]
    
    COMMON_NOTE_TYPES = {
        "project": "Projects",
        "meeting": "Meetings",
        "person": "People",
        "concept": "Concepts",
        "book": "Books",
        "article": "Articles",
        "research": "Research"
    }
    
    def __init__(self, vault_root: str):
        """
        Initialize with vault root path.
        
        Args:
            vault_root: Root path of the Obsidian vault
        """
        self.vault_root = Path(vault_root)
        self.cache_ttl = 300  # 5 minutes
        self._last_scan = 0
        self._path_cache: Dict[str, Path] = {}
        self._folder_content_cache: Dict[str, Set[str]] = {}
        
    async def find_best_location(self, title: str, content: str = "", 
                               note_type: Optional[str] = None, 
                               tags: Optional[List[str]] = None,
                               context: Optional[Dict] = None) -> Tuple[Path, float]:
        """
        Find the best location for a new note based on multiple factors.
        
        Args:
            title: Note title
            content: Note content
            note_type: Optional type of note
            tags: Optional list of tags
            context: Additional context dictionary
            
        Returns:
            Tuple of (best_path, confidence_score)
        """
        context = context or {}
        best_location = None
        best_score = 0
        confidence = 0.0
        
        # Check for existing similar notes first
        similar_note = await self.find_similar_note(title, content)
        if similar_note:
            return similar_note.parent, 0.8
            
        # If note type is specified, check type-specific locations
        if note_type and note_type.lower() in self.COMMON_NOTE_TYPES:
            type_path = self.vault_root / self.COMMON_NOTE_TYPES[note_type.lower()]
            if type_path.exists():
                return type_path, 0.9
                
        # Scan existing folders for best match
        for folder in self._scan_folders():
            score = await self._calculate_location_score(
                folder, title, content, tags, context
            )
            if score > best_score:
                best_location = folder
                best_score = score
                
        # Calculate confidence based on score
        if best_score > 0:
            confidence = min(best_score / 100.0, 1.0)
            
        # If no good match found or low confidence, use default location
        if not best_location or confidence < 0.3:
            best_location = await self._get_default_location(title, content, note_type)
            confidence = 0.5  # Medium confidence for default location
            
        return best_location, confidence

    @lru_cache(maxsize=100)
    async def find_daily_notes_folder(self) -> Path:
        """
        Find the daily notes folder using common patterns and context.
        Uses caching to avoid repeated scans.
        
        Returns:
            Path to the daily notes folder
        """
        # Check cache first
        cached = self._path_cache.get('daily_notes')
        if cached and (datetime.now().timestamp() - self._last_scan) < self.cache_ttl:
            return cached
            
        best_match = None
        best_score = 0
        
        # Scan vault for potential daily notes folders
        for folder in self._scan_folders():
            folder_str = str(folder.relative_to(self.vault_root))
            score = await self._calculate_daily_folder_score(folder)
            
            if score > best_score:
                best_match = folder
                best_score = score
        
        if not best_match:
            # Create default daily notes folder
            best_match = self.vault_root / "Daily Notes"
            best_match.mkdir(parents=True, exist_ok=True)
            
        # Update cache
        self._path_cache['daily_notes'] = best_match
        self._last_scan = datetime.now().timestamp()
        
        return best_match

    async def find_similar_note(self, title: str, content: str = "") -> Optional[Path]:
        """
        Find existing note with similar title or content.
        
        Args:
            title: Note title to compare
            content: Optional content to compare
            
        Returns:
            Path to similar note if found, None otherwise
        """
        best_match = None
        best_score = 0
        
        for file in self.vault_root.rglob("*.md"):
            # Compare titles first
            file_title = file.stem
            title_score = fuzz.ratio(title.lower(), file_title.lower())
            
            if title_score > 85:  # High title similarity
                return file
                
            if content and title_score > 60:  # Medium title similarity, check content
                try:
                    with open(file, 'r') as f:
                        file_content = f.read()
                    content_score = fuzz.partial_ratio(content.lower(), file_content.lower())
                    
                    total_score = (title_score + content_score) / 2
                    if total_score > best_score:
                        best_match = file
                        best_score = total_score
                except Exception as e:
                    logger.warning(f"Error reading {file}: {e}")
                    continue
                    
        return best_match if best_score > 75 else None

    def get_todays_note_path(self) -> Path:
        """
        Get path for today's daily note.
        
        Returns:
            Path to today's note
        """
        daily_folder = self.find_daily_notes_folder()
        date_str = datetime.now().strftime("%Y-%m-%d")
        return daily_folder / f"{date_str}.md"

    async def suggest_locations(self, title: str, content: str = "",
                              note_type: Optional[str] = None,
                              limit: int = 3) -> List[Tuple[Path, float]]:
        """
        Suggest multiple possible locations for a note, ranked by confidence.
        
        Args:
            title: Note title
            content: Optional content
            note_type: Optional note type
            limit: Maximum number of suggestions
            
        Returns:
            List of (path, confidence) tuples
        """
        suggestions = []
        
        for folder in self._scan_folders():
            score = await self._calculate_location_score(folder, title, content)
            if score > 0:
                confidence = min(score / 100.0, 1.0)
                suggestions.append((folder, confidence))
                
        # Sort by confidence and return top N
        return sorted(suggestions, key=lambda x: x[1], reverse=True)[:limit]

    def _scan_folders(self) -> List[Path]:
        """
        Scan vault for folders, ignoring hidden directories.
        
        Returns:
            List of folder paths
        """
        folders = []
        for root, dirs, _ in os.walk(self.vault_root):
            # Skip hidden folders and attachment folders
            dirs[:] = [d for d in dirs if not d.startswith('.') and d != "attachments"]
            folders.extend(Path(root) / d for d in dirs)
        return folders

    async def _calculate_daily_folder_score(self, folder: Path) -> float:
        """
        Calculate how likely a folder is to be the daily notes folder.
        
        Args:
            folder: Path to evaluate
            
        Returns:
            Score indicating likelihood (0-100)
        """
        score = 0
        folder_str = str(folder.relative_to(self.vault_root))
        
        # Check name patterns
        if "daily" in folder_str.lower():
            score += 30
        if "journal" in folder_str.lower():
            score += 20
            
        # Check for existing daily notes
        existing_files = list(folder.glob("*.md"))
        date_pattern_files = sum(1 for f in existing_files 
                               if self._is_date_pattern(f.stem))
        if date_pattern_files > 0:
            score += min(50, date_pattern_files)
            
        # Check folder depth (prefer shallower)
        depth = len(folder_str.split(os.sep))
        score -= depth * 5
        
        return max(0, score)

    async def _calculate_location_score(self, folder: Path, title: str, 
                                     content: str = "", tags: Optional[List[str]] = None,
                                     context: Optional[Dict] = None) -> float:
        """
        Calculate how appropriate a folder is for a given note.
        
        Args:
            folder: Folder to evaluate
            title: Note title
            content: Optional note content
            tags: Optional list of tags
            context: Optional context dictionary
            
        Returns:
            Score indicating appropriateness (0-100)
        """
        score = 0
        folder_str = str(folder.relative_to(self.vault_root))
        context = context or {}
        tags = tags or []
        
        # Check folder name relevance
        folder_words = set(folder_str.lower().split())
        title_words = set(title.lower().split())
        score += len(folder_words & title_words) * 10
        
        # Cache folder contents
        if folder_str not in self._folder_content_cache:
            folder_content = set()
            for file in folder.glob("*.md"):
                try:
                    with open(file, 'r') as f:
                        folder_content.add(f.read().lower())
                except Exception:
                    continue
            self._folder_content_cache[folder_str] = folder_content
            
        # Check content similarity with existing notes
        if content:
            content_lower = content.lower()
            for existing_content in self._folder_content_cache[folder_str]:
                similarity = fuzz.partial_ratio(content_lower, existing_content)
                score += similarity * 0.2  # Weight content similarity less than other factors
                
        # Check tags
        if tags:
            for file in folder.glob("*.md"):
                try:
                    with open(file, 'r') as f:
                        head = ''.join(f.readline() for _ in range(10))
                        if '---' in head:  # Has frontmatter
                            front = yaml.safe_load(head.split('---')[1])
                            if front.get('tags'):
                                common_tags = set(front['tags']) & set(tags)
                                score += len(common_tags) * 15
                except Exception:
                    continue
                    
        # Consider context hints
        if context.get('folder_hint'):
            hint_score = fuzz.ratio(folder_str.lower(), context['folder_hint'].lower())
            score += hint_score * 0.3
            
        # Consider folder depth
        depth = len(folder_str.split(os.sep))
        score -= depth * 5  # Prefer shallower paths
        
        return max(0, score)

    async def _get_default_location(self, title: str, content: str = "",
                                  note_type: Optional[str] = None) -> Path:
        """
        Get default location for a note when no better match is found.
        
        Args:
            title: Note title
            content: Optional note content
            note_type: Optional note type
            
        Returns:
            Default path for the note
        """
        if note_type and note_type.lower() in self.COMMON_NOTE_TYPES:
            default_path = self.vault_root / self.COMMON_NOTE_TYPES[note_type.lower()]
        else:
            # Try to infer type from content and title
            inferred_type = await self._infer_note_type(title, content)
            if inferred_type in self.COMMON_NOTE_TYPES:
                default_path = self.vault_root / self.COMMON_NOTE_TYPES[inferred_type]
            else:
                default_path = self.vault_root / "Notes"
                
        default_path.mkdir(parents=True, exist_ok=True)
        return default_path

    @staticmethod
    def _is_date_pattern(text: str) -> bool:
        """
        Check if text matches a date pattern.
        
        Args:
            text: Text to check
            
        Returns:
            True if text matches a date pattern
        """
        patterns = [
            r"\d{4}-\d{2}-\d{2}",  # YYYY-MM-DD
            r"\d{2}-\d{2}-\d{4}",  # DD-MM-YYYY
            r"\d{4}\.\d{2}\.\d{2}",  # YYYY.MM.DD
            r"\d{2}\.\d{2}\.\d{4}"   # DD.MM.YYYY
        ]
        return any(re.match(pattern, text) for pattern in patterns)

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        Sanitize filename for filesystem compatibility.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '-')
            
        # Ensure .md extension
        if not filename.lower().endswith('.md'):
            filename += '.md'
            
        return filename

async def _infer_note_type(self, title: str, content: str = "") -> Optional[str]:
        """
        Try to infer note type from title and content.
        
        Uses various heuristics to determine the most likely type of note based on:
        - Title patterns
        - Content keywords
        - Structure patterns
        - Common formats

        Args:
            title: Note title
            content: Optional note content
            
        Returns:
            Inferred note type or None
        """
        title_lower = title.lower()
        content_lower = content.lower()
        
        # Project indicators
        project_keywords = {"project", "initiative", "development", "roadmap", "milestone", 
                          "sprint", "release", "implementation", "launch"}
        if any(word in title_lower for word in project_keywords):
            return "project"
            
        # Meeting indicators
        meeting_keywords = {"meeting", "sync", "discussion", "call", "review", 
                          "standup", "retrospective", "1:1", "one-on-one"}
        if any(word in title_lower for word in meeting_keywords):
            return "meeting"
            
        # Person indicators
        if re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+", title):  # Proper name format
            return "person"
            
        # Book indicators
        book_patterns = [
            r"^.*\bbook\b.*$",
            r"^.*\bnovel\b.*$",
            r".*\bby [A-Z][a-z]+ [A-Z][a-z]+.*",  # Author pattern
            r".*\([0-9]{4}\).*"  # Publication year pattern
        ]
        if any(re.match(pattern, title, re.IGNORECASE) for pattern in book_patterns):
            return "book"
            
        # Article indicators
        article_keywords = {"article", "blog post", "paper", "publication", "journal"}
        if any(word in title_lower for word in article_keywords):
            return "article"
            
        # Research indicators
        research_keywords = {"research", "study", "analysis", "investigation", 
                           "experiment", "findings", "methodology"}
        if any(word in title_lower for word in research_keywords) or \
           any(word in content_lower[:500] for word in research_keywords):  # Check first 500 chars
            return "research"
            
        # Concept indicators
        concept_patterns = [
            r"^What is .*",
            r"^How to .*",
            r"^Understanding .*",
            r"^([A-Z][a-z]+ )*[A-Z][a-z]+ Theory",
            r"^([A-Z][a-z]+ )*[A-Z][a-z]+ Concept",
        ]
        if any(re.match(pattern, title) for pattern in concept_patterns):
            return "concept"
            
        # Check content structure if available
        if content:
            # Look for frontmatter
            if content.startswith("---"):
                try:
                    frontmatter_end = content.index("---", 3)
                    frontmatter = yaml.safe_load(content[3:frontmatter_end])
                    if "type" in frontmatter:
                        return frontmatter["type"].lower()
                except:
                    pass
                    
            # Check for common content patterns
            if re.search(r"#+\s*Meeting Notes|Attendees|Action Items", content):
                return "meeting"
            if re.search(r"#+\s*Abstract|Introduction|Methodology|Conclusion", content):
                return "research"
            if re.search(r"#+\s*Chapter|Summary|Review|Rating", content):
                return "book"
                
        # Default to None if no clear type is found
        return None