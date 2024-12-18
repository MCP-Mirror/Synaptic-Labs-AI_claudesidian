"""
Search functionality for Obsidian vault.
Provides fuzzy searching capabilities with configurable matching strategies.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, AsyncGenerator
from fuzzywuzzy import fuzz
import heapq

@dataclass
class SearchResult:
    """
    Represents a single search result with its metadata.
    """
    file_path: Path
    score: float
    title: str
    preview: str
    match_context: str = ""

    def to_dict(self) -> dict:
        """Convert the search result to a dictionary format."""
        return {
            "path": str(self.file_path),
            "score": self.score,
            "title": self.title,
            "preview": self.preview,
            "match_context": self.match_context
        }

class SearchEngine:
    """
    Core search engine that handles fuzzy searching through the vault.
    Supports both filename and content searching with configurable parameters.
    """
    
    def __init__(self, vault_path: Path, max_preview_length: int = 200):
        """
        Initialize the search engine.
        
        Args:
            vault_path (Path): Root path of the Obsidian vault
            max_preview_length (int): Maximum length of content previews
        """
        self.vault_path = vault_path
        self.max_preview_length = max_preview_length
        self._file_cache = {}  # Future: Implement LRU cache

    async def search(self, 
                    query: str, 
                    threshold: float = 60.0,
                    max_results: int = 10,
                    search_contents: bool = True) -> List[SearchResult]:
        """
        Perform a fuzzy search through the vault.
        
        Args:
            query (str): Search query
            threshold (float): Minimum similarity score (0-100)
            max_results (int): Maximum number of results to return
            search_contents (bool): Whether to search file contents
            
        Returns:
            List[SearchResult]: Sorted list of search results
        """
        results = []
        async for result in self._search_files(query, threshold, search_contents):
            heapq.heappush(results, (-result.score, result))
            if len(results) > max_results:
                heapq.heappop(results)
                
        return [result for _, result in sorted(results, reverse=True)]

    async def _search_files(self, 
                          query: str, 
                          threshold: float,
                          search_contents: bool) -> AsyncGenerator[SearchResult, None]:
        """
        Generator that yields search results as they're found.
        
        Args:
            query (str): Search query
            threshold (float): Minimum similarity score
            search_contents (bool): Whether to search file contents
        """
        search_tasks = []
        
        for file_path in self.vault_path.rglob("*.md"):
            # Skip hidden files and directories
            if any(part.startswith('.') for part in file_path.parts):
                continue
                
            task = asyncio.create_task(
                self._process_file(file_path, query, threshold, search_contents)
            )
            search_tasks.append(task)
            
            # Process in batches to avoid memory overload
            if len(search_tasks) >= 50:
                for result in await self._gather_results(search_tasks):
                    if result:
                        yield result
                search_tasks = []
        
        # Process remaining files
        if search_tasks:
            for result in await self._gather_results(search_tasks):
                if result:
                    yield result

    async def _gather_results(self, tasks: List[asyncio.Task]) -> List[Optional[SearchResult]]:
        """
        Gather results from multiple search tasks.
        
        Args:
            tasks (List[asyncio.Task]): List of search tasks
            
        Returns:
            List[Optional[SearchResult]]: List of search results
        """
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in results if isinstance(r, SearchResult)]
        except Exception as e:
            print(f"Error gathering results: {e}")
            return []

    async def _process_file(self, 
                          file_path: Path, 
                          query: str, 
                          threshold: float,
                          search_contents: bool) -> Optional[SearchResult]:
        """
        Process a single file for matches.
        
        Args:
            file_path (Path): Path to the file
            query (str): Search query
            threshold (float): Minimum similarity score
            search_contents (bool): Whether to search file contents
            
        Returns:
            Optional[SearchResult]: Search result if match found
        """
        try:
            filename_score = fuzz.partial_ratio(query.lower(), file_path.stem.lower())
            content_score = 0
            preview = ""
            match_context = ""

            if search_contents:
                content = await self._read_file(file_path)
                if content:
                    content_score = self._score_content(query, content)
                    if content_score >= threshold:
                        preview, match_context = self._generate_preview(query, content)

            # Use maximum score between filename and content
            score = max(filename_score, content_score)
            
            if score >= threshold:
                return SearchResult(
                    file_path=file_path.relative_to(self.vault_path),
                    score=score,
                    title=file_path.stem,
                    preview=preview,
                    match_context=match_context
                )
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            
        return None

    async def _read_file(self, file_path: Path) -> Optional[str]:
        """
        Read file content with caching.
        
        Args:
            file_path (Path): Path to the file
            
        Returns:
            Optional[str]: File content if successful
        """
        try:
            if file_path in self._file_cache:
                return self._file_cache[file_path]
            
            content = await asyncio.to_thread(file_path.read_text, encoding='utf-8')
            self._file_cache[file_path] = content
            return content
            
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return None

    def _score_content(self, query: str, content: str) -> float:
        """
        Score content based on fuzzy matching.
        
        Args:
            query (str): Search query
            content (str): File content
            
        Returns:
            float: Match score
        """
        # Split content into chunks for better matching
        chunks = content.split('\n')
        return max(
            fuzz.partial_ratio(query.lower(), chunk.lower())
            for chunk in chunks
        )

    def _generate_preview(self, query: str, content: str) -> Tuple[str, str]:
        """
        Generate a preview of the matched content.
        
        Args:
            query (str): Search query
            content (str): File content
            
        Returns:
            Tuple[str, str]: (preview, match context)
        """
        lines = content.split('\n')
        best_score = 0
        best_line = 0
        
        # Find the best matching line
        for i, line in enumerate(lines):
            score = fuzz.partial_ratio(query.lower(), line.lower())
            if score > best_score:
                best_score = score
                best_line = i
        
        # Generate preview with context
        start = max(0, best_line - 2)
        end = min(len(lines), best_line + 3)
        context_lines = lines[start:end]
        
        preview = content[:self.max_preview_length] + "..." if len(content) > self.max_preview_length else content
        match_context = "\n".join(context_lines)
        
        return preview, match_context