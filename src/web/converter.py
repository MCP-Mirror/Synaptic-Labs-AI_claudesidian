# File: claudesidian/web/converter.py

"""
Content converter for transforming web content into Obsidian notes.
Handles HTML to Markdown conversion, image processing, and note organization.
"""

import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import html2text
from bs4 import BeautifulSoup
import yaml
from datetime import datetime
import hashlib
import aiohttp
import aiofiles
import logging
from urllib.parse import urljoin, urlparse, unquote

from . import (
    WebContent, WebImage, WebLink, ConversionError,
    ImageHandling
)

logger = logging.getLogger(__name__)

class ContentConverter:
    """
    Converts web content into Obsidian-compatible notes.
    """
    
    def __init__(self, vault_path: Path,
                 image_handling: ImageHandling = ImageHandling.DOWNLOAD,
                 attachment_folder: str = "attachments/web"):
        """
        Initialize converter with configuration.
        
        Args:
            vault_path: Path to Obsidian vault
            image_handling: How to handle images
            attachment_folder: Where to store downloaded files
        """
        self.vault_path = Path(vault_path)
        self.image_handling = image_handling
        self.attachment_folder = attachment_folder
        
        # Configure HTML to Markdown converter
        self.h2t = html2text.HTML2Text()
        self.h2t.body_width = 0  # No wrapping
        self.h2t.use_automatic_links = False
        self.h2t.mark_code = True
        self.h2t.default_image_alt = ""
        self.h2t.escape_snob = False
        self.h2t.unicode_snob = True
        self.h2t.images_to_alt = False

    async def convert(self, content: WebContent, note_path: Optional[Path] = None) -> Tuple[str, Path]:
        """
        Convert web content to an Obsidian note.
        
        Args:
            content: WebContent object to convert
            note_path: Optional specific path for note
            
        Returns:
            Tuple of (converted content, note path)
        """
        try:
            # Generate note path if not provided
            if not note_path:
                note_path = await self._generate_note_path(content)
                
            # Generate frontmatter
            frontmatter = await self._generate_frontmatter(content)
            
            # Convert main content
            markdown = await self._convert_content(content)
            
            # Process images
            if self.image_handling != ImageHandling.IGNORE:
                markdown = await self._process_images(content, markdown, note_path)
                
            # Process links
            markdown = await self._process_links(content, markdown)
            
            # Add frontmatter to content
            final_content = "---\n"
            final_content += yaml.dump(frontmatter, allow_unicode=True)
            final_content += "---\n\n"
            final_content += markdown
            
            return final_content, note_path
            
        except Exception as e:
            raise ConversionError(f"Failed to convert content: {str(e)}")

    async def _generate_note_path(self, content: WebContent) -> Path:
        """Generate appropriate path for the note."""
        # Use title if available, otherwise URL
        if content.metadata and content.metadata.title:
            title = content.metadata.title
        else:
            title = urlparse(content.url).path.split('/')[-1]
            title = unquote(title).replace('-', ' ').replace('_', ' ')
            
        # Clean filename
        safe_title = re.sub(r'[^\w\s-]', '', title)
        safe_title = re.sub(r'[-\s]+', '-', safe_title).strip('-')
        
        # Generate path
        date = datetime.now().strftime("%Y/%m")
        return Path(f"Web/{date}/{safe_title}.md")

    async def _generate_frontmatter(self, content: WebContent) -> Dict[str, Any]:
        """Generate frontmatter for the note."""
        frontmatter = {
            'title': content.metadata.title if content.metadata else None,
            'url': content.url,
            'date_saved': datetime.now().isoformat(),
            'type': 'web_page'
        }
        
        # Add metadata if available
        if content.metadata:
            if content.metadata.author:
                frontmatter['author'] = content.metadata.author
            if content.metadata.date_published:
                frontmatter['date_published'] = content.metadata.date_published
            if content.metadata.date_modified:
                frontmatter['date_modified'] = content.metadata.date_modified
            if content.metadata.tags:
                frontmatter['tags'] = content.metadata.tags
            if content.metadata.site_name:
                frontmatter['site'] = content.metadata.site_name
                
        # Clean up None values
        frontmatter = {k: v for k, v in frontmatter.items() if v is not None}
        
        return frontmatter

    async def _convert_content(self, content: WebContent) -> str:
        """Convert HTML content to Markdown."""
        # First pass with html2text
        markdown = self.h2t.handle(content.content)
        
        # Clean up common issues
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)  # Excess newlines
        markdown = re.sub(r'(?<!\n)\n(?!\n)', ' ', markdown)  # Single newlines
        markdown = re.sub(r'\[!\[([^\]]+)\]\([^\)]+\)\]\([^\)]+\)', r'![\1]', markdown)  # Nested images
        
        # Handle code blocks
        for block in content.code_blocks:
            placeholder = f"CODE_BLOCK_{hash(block['code'])}"
            language = f"```{block['language']}\n" if block['language'] else "```\n"
            markdown = markdown.replace(placeholder, f"{language}{block['code']}\n```\n")
            
        # Handle tables
        for table in content.tables:
            if table['headers']:
                table_md = "| " + " | ".join(table['headers']) + " |\n"
                table_md += "| " + " | ".join(['---'] * len(table['headers'])) + " |\n"
            else:
                table_md = ""
                
            for row in table['rows']:
                table_md += "| " + " | ".join(row) + " |\n"
                
            placeholder = f"TABLE_{hash(str(table))}"
            markdown = markdown.replace(placeholder, table_md)
            
        return markdown

    async def _process_images(self, content: WebContent, markdown: str, note_path: Path) -> str:
        """Process images based on handling strategy."""
        if self.image_handling == ImageHandling.IGNORE:
            return markdown
            
        for image in content.images:
            if self.image_handling == ImageHandling.DOWNLOAD:
                try:
                    local_path = await self._download_image(image, note_path)
                    # Update markdown to use local path
                    rel_path = local_path.relative_to(self.vault_path)
                    markdown = markdown.replace(
                        f"]({image.url})",
                        f"]({rel_path})"
                    )
                except Exception as e:
                    logger.warning(f"Failed to download image {image.url}: {e}")
                    
        return markdown

    async def _download_image(self, image: WebImage, note_path: Path) -> Path:
        """Download an image to the attachments folder."""
        # Generate filename
        url_hash = hashlib.md5(image.url.encode()).hexdigest()[:8]
        ext = Path(urlparse(image.url).path).suffix or '.jpg'
        filename = f"{url_hash}{ext}"
        
        # Determine save path
        save_dir = self.vault_path / self.attachment_folder / note_path.parent.name
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / filename
        
        # Download image
        async with aiohttp.ClientSession() as session:
            async with session.get(image.url) as response:
                if response.status == 200:
                    async with aiofiles.open(save_path, 'wb') as f:
                        await f.write(await response.read())
                        
        return save_path

    async def _process_links(self, content: WebContent, markdown: str) -> str:
        """Process and clean up links in the content."""
        # Convert external links to reference style
        links = {}
        def repl(match):
            url = match.group(2)
            text = match.group(1)
            if url not in links:
                links[url] = len(links) + 1
            return f"[{text}][{links[url]}]"
            
        markdown = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', repl, markdown)
        
        # Add reference definitions
        if links:
            markdown += "\n\n"
            for url, num in links.items():
                markdown += f"[{num}]: {url}\n"
                
        return markdown

    async def bulk_convert(self, contents: List[WebContent],
                         base_path: Optional[Path] = None) -> List[Tuple[str, Path]]:
        """
        Convert multiple web contents to notes.
        
        Args:
            contents: List of WebContent objects
            base_path: Optional base path for notes
            
        Returns:
            List of (content, path) tuples
        """
        results = []
        for content in contents:
            try:
                note_path = None
                if base_path:
                    # Generate unique path under base_path
                    safe_title = re.sub(r'[^\w\s-]', '', content.metadata.title or "untitled")
                    safe_title = re.sub(r'[-\s]+', '-', safe_title).strip('-')
                    note_path = base_path / f"{safe_title}.md"
                    
                converted, path = await self.convert(content, note_path)
                results.append((converted, path))
                
            except Exception as e:
                logger.error(f"Failed to convert content {content.url}: {e}")
                continue
                
        return results