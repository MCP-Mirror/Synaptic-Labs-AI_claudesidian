# File: claudesidian/web/parser.py

"""
Content parsing for web content.
Handles HTML parsing, content cleaning, and metadata extraction.
"""

import re
from typing import Dict, List, Optional, Set, Tuple, Any
from bs4 import BeautifulSoup, Tag
import trafilatura
from datetime import datetime
import json
from urllib.parse import urljoin, urlparse
import logging
from readability import Document

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
    
    def __init__(self, min_content_length: int = 100):
        """
        Initialize parser with configuration.
        
        Args:
            min_content_length: Minimum length for valid content
        """
        self.min_content_length = min_content_length
        
    async def parse(self, html: str, url: str) -> WebContent:
        """
        Parse HTML content using multiple strategies.
        
        Args:
            html: Raw HTML content
            url: Source URL for resolving links
            
        Returns:
            WebContent object with parsed content
        """
        try:
            # Create base content object
            content = WebContent(url)
            
            # Try multiple parsing strategies
            soup = BeautifulSoup(html, 'lxml')
            
            # Extract and clean metadata
            content.metadata = await self._extract_metadata(soup, url)
            
            # Extract main content using multiple methods
            content.content = await self._extract_content(html, soup, url)
            
            # Extract and process images
            content.images = await self._extract_images(soup, url)
            
            # Extract and process links
            content.links = await self._extract_links(soup, url)
            
            # Extract tables if any
            content.tables = await self._extract_tables(soup)
            
            # Extract code blocks if any
            content.code_blocks = await self._extract_code_blocks(soup)
            
            # Store raw HTML
            content.raw_html = html
            
            return content
            
        except Exception as e:
            raise ParsingError(f"Failed to parse content: {str(e)}")

    async def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Metadata:
        """Extract metadata from various sources in the HTML."""
        metadata = {
            'title': None,
            'description': None,
            'author': None,
            'date_published': None,
            'date_modified': None,
            'tags': [],
            'language': None,
            'site_name': None,
            'favicon': None,
            'og_data': {},
            'twitter_data': {},
            'schema_data': {}
        }
        
        # Extract OpenGraph metadata
        for meta in soup.find_all('meta', property=re.compile('^og:')):
            prop = meta.get('property', '')[3:]
            if prop:
                metadata['og_data'][prop] = meta.get('content')
                
        # Extract Twitter card metadata
        for meta in soup.find_all('meta', name=re.compile('^twitter:')):
            prop = meta.get('name', '')[8:]
            if prop:
                metadata['twitter_data'][prop] = meta.get('content')
                
        # Extract schema.org metadata
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict):
                    metadata['schema_data'] = data
                break
            except:
                continue
                
        # Extract basic metadata
        metadata['title'] = (
            metadata['og_data'].get('title') or
            soup.find('meta', {'name': 'title'})?.get('content') or
            soup.title.string if soup.title else None
        )
        
        metadata['description'] = (
            metadata['og_data'].get('description') or
            soup.find('meta', {'name': 'description'})?.get('content')
        )
        
        # Try to find author
        author = (
            soup.find('meta', {'name': 'author'})?.get('content') or
            soup.find('a', rel='author')?.text or
            soup.find(class_=re.compile('author|byline'))?.text
        )
        if author:
            metadata['author'] = author.strip()
            
        # Try to find dates
        pub_date = (
            soup.find('meta', {'property': 'article:published_time'})?.get('content') or
            soup.find('time', {'pubdate': True})?.get('datetime')
        )
        if pub_date:
            try:
                metadata['date_published'] = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
            except:
                pass
                
        # Extract language
        metadata['language'] = soup.html.get('lang', '').split('-')[0] or None
        
        # Extract favicon
        favicon = soup.find('link', rel=re.compile('icon'))
        if favicon and favicon.get('href'):
            metadata['favicon'] = urljoin(url, favicon['href'])
            
        return Metadata(**metadata)

    async def _extract_content(self, html: str, soup: BeautifulSoup, url: str) -> str:
        """
        Extract main content using multiple strategies.
        Falls back to next strategy if content seems invalid.
        """
        content = None
        
        # Try trafilatura first
        try:
            content = trafilatura.extract(html)
            if content and len(content) >= self.min_content_length:
                return content
        except:
            pass
            
        # Try readability
        try:
            doc = Document(html)
            content = doc.summary()
            if content and len(content) >= self.min_content_length:
                return content
        except:
            pass
            
        # Try finding content using common selectors
        for selector in self.CONTENT_ELEMENTS:
            element = soup.select_one(selector)
            if element:
                # Remove noise elements
                for noise in element.select(','.join(self.NOISE_ELEMENTS)):
                    noise.decompose()
                    
                content = element.get_text(separator='\n', strip=True)
                if len(content) >= self.min_content_length:
                    return content
                    
        # Fall back to cleaned body content
        body = soup.find('body')
        if body:
            for noise in body.select(','.join(self.NOISE_ELEMENTS)):
                noise.decompose()
            return body.get_text(separator='\n', strip=True)
            
        raise ParsingError("Could not extract meaningful content")

    async def _extract_images(self, soup: BeautifulSoup, url: str) -> List[WebImage]:
        """Extract and process images from the content."""
        images = []
        seen_urls = set()
        
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if not src or src in seen_urls:
                continue
                
            # Resolve relative URLs
            src = urljoin(url, src)
            seen_urls.add(src)
            
            image = WebImage(
                url=src,
                alt_text=img.get('alt', ''),
                title=img.get('title'),
                width=int(img.get('width', 0)) or None,
                height=int(img.get('height', 0)) or None
            )
            
            # Try to find caption
            figure = img.find_parent('figure')
            if figure:
                figcaption = figure.find('figcaption')
                if figcaption:
                    image.caption = figcaption.get_text(strip=True)
                    
            images.append(image)
            
        return images

    async def _extract_links(self, soup: BeautifulSoup, url: str) -> List[WebLink]:
        """Extract and process links from the content."""
        links = []
        seen_urls = set()
        base_domain = urlparse(url).netloc
        
        for a in soup.find_all('a', href=True):
            href = a.get('href', '').strip()
            if not href or href.startswith(('#', 'javascript:', 'mailto:')):
                continue
                
            # Resolve relative URLs
            href = urljoin(url, href)
            if href in seen_urls:
                continue
                
            seen_urls.add(href)
            parsed = urlparse(href)
            
            link = WebLink(
                url=href,
                text=a.get_text(strip=True),
                title=a.get('title'),
                rel=a.get('rel', []),
                is_internal=parsed.netloc == base_domain,
                is_media=bool(re.search(r'\.(jpg|jpeg|png|gif|pdf|doc|docx|xls|xlsx)$', parsed.path, re.I))
            )
            
            links.append(link)
            
        return links

    async def _extract_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract and process tables from the content."""
        tables = []
        
        for table in soup.find_all('table'):
            # Process header row
            headers = []
            header_row = table.find('thead')?.find('tr') or table.find('tr')
            if header_row:
                headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
                
            # Process data rows
            rows = []
            for tr in table.find_all('tr')[1:] if headers else table.find_all('tr'):
                row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                if row:
                    rows.append(row)
                    
            if rows:
                tables.append({
                    'headers': headers,
                    'rows': rows,
                    'caption': table.find('caption')?.get_text(strip=True)
                })
                
        return tables

    async def _extract_code_blocks(self, soup: BeautifulSoup) -> List[Dict[str, str]]:
        """Extract and process code blocks from the content."""
        code_blocks = []
        
        # Check for preformatted code blocks
        for pre in soup.find_all('pre'):
            code = pre.find('code')
            if code:
                language = None
                for class_ in code.get('class', []):
                    if class_.startswith(('language-', 'lang-')):
                        language = class_.split('-')[1]
                        break
                        
                code_blocks.append({
                    'language': language,
                    'code': code.get_text(strip=True)
                })
            else:
                code_blocks.append({
                    'language': None,
                    'code': pre.get_text(strip=True)
                })
                
        return code_blocks