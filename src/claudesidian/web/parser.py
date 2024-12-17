# File: claudesidian/web/parser.py

"""
Content parsing for web content.
Handles HTML parsing, content cleaning, and metadata extraction.
"""

import re
from typing import Dict, List, Optional, Set, Tuple, Any
from bs4 import BeautifulSoup, Tag
import json
from urllib.parse import urljoin, urlparse
import logging

# Add missing imports or replace with alternatives
try:
    trafilatura = None  # Placeholder for future use
except ImportError:
    trafilatura = None

try:    
    from readability import Document
except ImportError:
    Document = None

from . import (
    WebContent, WebImage, WebLink, Metadata,
    ParsingError
)

logger = logging.getLogger(__name__)

class ContentParser:
    """
    Parses web content using multiple strategies for best results.
    """
    
    # Elements that usually indicate main content
    CONTENT_ELEMENTS = {
        'article', 'main', 'div[role="main"]', '.post-content',
        '.article-content', '.entry-content', '.content', '#content'
    }
    
    # Elements to remove
    NOISE_ELEMENTS = {
        'script', 'style', 'nav', 'header', 'footer', 'iframe',
        'noscript', '[class*="menu"]', '[class*="sidebar"]',
        '[class*="related"]', '[class*="comment"]', '[class*="ad"]',
        '[id*="menu"]', '[id*="sidebar"]', '[id*="related"]',
        '[id*="comment"]', '[id*="ad"]'
    }

    # Add Obsidian-specific patterns
    OBSIDIAN_PATTERNS = {
        'wikilinks': r'\[\[(.*?)\]\]',
        'tags': r'#[A-Za-z0-9_-]+',
        'callouts': r'> \[!.*?\]',
        'math': r'\$\$(.*?)\$\$',
        'code_blocks': r'```[\s\S]*?```'
    }