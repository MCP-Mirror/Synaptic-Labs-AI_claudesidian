# File: claudesidian/web/__init__.py

"""
Web module for Claudesidian.
Handles web scraping, content parsing, and conversion to notes.
"""

from typing import TypedDict, Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
from dataclasses import dataclass

# Configuration Types
class ScrapingConfig(TypedDict, total=False):
    """Configuration for web scraping behavior."""
    max_wait_time: int         # Maximum seconds to wait for page load
    screenshot_enabled: bool   # Whether to capture screenshots
    js_enabled: bool          # Whether to execute JavaScript
    user_agent: str          # Custom user agent string
    timeout: int             # Request timeout in seconds
    max_redirects: int       # Maximum number of redirects to follow
    proxy: Optional[str]     # Proxy server to use
    cookies: Dict[str, str]  # Cookies to set
    headers: Dict[str, str]  # Additional headers

class ImageHandling(Enum):
    """How to handle images during scraping."""
    IGNORE = "ignore"         # Don't process images
    LINK = "link"            # Keep original URLs
    DOWNLOAD = "download"    # Download to vault
    SCREENSHOT = "screenshot" # Take screenshots of elements

class ContentPriority(Enum):
    """Priority for content extraction."""
    ARTICLE = "article"      # Prioritize article content
    MAIN = "main"           # Use main content area
    FULL = "full"           # Get full page content
    CUSTOM = "custom"       # Use custom selector

# Content Types
@dataclass
class Metadata:
    """Metadata extracted from web page."""
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    date_published: Optional[datetime] = None
    date_modified: Optional[datetime] = None
    tags: List[str] = None
    language: Optional[str] = None
    site_name: Optional[str] = None
    favicon: Optional[str] = None
    og_data: Dict[str, Any] = None
    twitter_data: Dict[str, Any] = None
    schema_data: Dict[str, Any] = None

@dataclass
class WebImage:
    """Represents an image from a web page."""
    url: str
    alt_text: Optional[str] = None
    title: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    caption: Optional[str] = None
    local_path: Optional[str] = None

@dataclass
class WebLink:
    """Represents a link from a web page."""
    url: str
    text: str
    title: Optional[str] = None
    rel: Optional[str] = None
    is_internal: bool = False
    is_media: bool = False

class WebContent:
    """Content extracted from a web page."""
    def __init__(self, url: str):
        self.url: str = url
        self.metadata: Metadata = None
        self.content: str = ""
        self.raw_html: str = ""
        self.text_content: str = ""
        self.images: List[WebImage] = []
        self.links: List[WebLink] = []
        self.tables: List[Dict[str, Any]] = []
        self.code_blocks: List[Dict[str, str]] = []
        self.headers: List[Dict[str, str]] = []
        self.screenshots: List[str] = []
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            'url': self.url,
            'metadata': self.metadata.__dict__ if self.metadata else None,
            'content': self.content,
            'images': [img.__dict__ for img in self.images],
            'links': [link.__dict__ for link in self.links],
            'tables': self.tables,
            'code_blocks': self.code_blocks,
            'headers': self.headers,
            'screenshots': self.screenshots
        }

# Search Types
@dataclass
class SearchResult:
    """Individual search result."""
    url: str
    title: str
    description: str
    score: float
    date: Optional[datetime] = None
    source: Optional[str] = None
    type: Optional[str] = None

@dataclass
class SearchResponse:
    """Complete search response."""
    query: str
    results: List[SearchResult]
    total_results: int
    page: int
    has_more: bool
    execution_time: float

# Exceptions
class WebError(Exception):
    """Base exception for web module."""
    pass

class ScrapingError(WebError):
    """Error during web scraping."""
    def __init__(self, message: str, url: str, status_code: Optional[int] = None):
        self.url = url
        self.status_code = status_code
        super().__init__(f"{message} (URL: {url}, Status: {status_code})")

class ParsingError(WebError):
    """Error during content parsing."""
    pass

class ConversionError(WebError):
    """Error during content conversion."""
    pass

class SearchError(WebError):
    """Error during web search."""
    pass

class RateLimitError(WebError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        message = f"Rate limit exceeded. Retry after {retry_after}s" if retry_after else "Rate limit exceeded"
        super().__init__(message)

# Export components
from .scraper import WebScraper
from .parser import ContentParser
from .converter import ContentConverter

__all__ = [
    # Main classes
    'WebScraper',
    'ContentParser',
    'ContentConverter',
    
    # Configuration
    'ScrapingConfig',
    'ImageHandling',
    'ContentPriority',
    
    # Content types
    'Metadata',
    'WebContent',
    'WebImage',
    'WebLink',
    'SearchResult',
    'SearchResponse',
    
    # Exceptions
    'WebError',
    'ScrapingError',
    'ParsingError',
    'ConversionError',
    'SearchError',
    'RateLimitError'
]

# Version info
__version__ = "0.1.0"