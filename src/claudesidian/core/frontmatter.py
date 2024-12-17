# File: claudesidian/core/frontmatter.py

"""
Frontmatter management for Claudesidian.
Handles frontmatter operations, templates, and schema validation.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import logging
import yaml
from copy import deepcopy

from .types import Frontmatter, InvalidFrontmatterError
from ..utils.path_resolver import PathResolver  # Fix the import path

logger = logging.getLogger(__name__)

class FrontmatterManager:
    """
    Manages frontmatter operations, templates, and validation.
    """
    
    def __init__(self, vault_manager, path_resolver: Optional[PathResolver] = None):
        """
        Initialize frontmatter manager.
        
        Args:
            vault_manager: VaultManager instance
            path_resolver: Optional PathResolver instance
        """
        self.vault = vault_manager
        self.path_resolver = path_resolver or PathResolver(self.vault.vault_path)
        
        # Cache for templates and schemas
        self._template_cache: Dict[str, Dict[str, Any]] = {}
        self._schema_cache: Dict[str, Dict[str, Any]] = {}
        
    async def parse(self, content: str) -> Optional[Frontmatter]:
        """
        Parse frontmatter from note content.
        
        Args:
            content: Note content
            
        Returns:
            Frontmatter object or None if no frontmatter
        """
        fm_block = FrontmatterParser.parse(content)
        if not fm_block.data:
            return None
        return Frontmatter(fm_block.data)

    async def generate(self, template_name: Optional[str] = None,
                      **kwargs) -> Frontmatter:
        """
        Generate frontmatter, optionally using a template.
        
        Args:
            template_name: Optional template name
            **kwargs: Values to include/override
            
        Returns:
            Frontmatter object
        """
        data = {}
        
        if template_name:
            # Load template
            template = await self._get_template(template_name)
            if template:
                data.update(deepcopy(template))
                
        # Add/override with provided values
        data.update(kwargs)
        
        # Add default timestamps if not present
        now = datetime.now().isoformat()
        if 'created' not in data:
            data['created'] = now
        if 'modified' not in data:
            data['modified'] = now
            
        return Frontmatter(data)

    async def validate(self, frontmatter: Frontmatter,
                      schema_name: Optional[str] = None) -> bool:
        """
        Validate frontmatter against a schema.
        
        Args:
            frontmatter: Frontmatter to validate
            schema_name: Optional schema name (if None, uses type-based schema)
            
        Returns:
            True if valid
        """
        # If no schema specified, try to use type-based schema
        if not schema_name and 'type' in frontmatter:
            schema_name = frontmatter['type']
            
        if not schema_name:
            return True  # No schema to validate against
            
        schema = await self._get_schema(schema_name)
        if not schema:
            return True  # No schema found
            
        return frontmatter.validate_schema(schema)

    async def update(self, frontmatter: Frontmatter,
                    updates: Dict[str, Any]) -> Frontmatter:
        """
        Update frontmatter with new values.
        
        Args:
            frontmatter: Original frontmatter
            updates: Values to update
            
        Returns:
            Updated Frontmatter object
        """
        # Create new frontmatter with updated values
        new_data = deepcopy(frontmatter._data)
        new_data.update(updates)
        
        # Always update modified timestamp
        new_data['modified'] = datetime.now().isoformat()
        
        return Frontmatter(new_data)

    async def get_template_names(self) -> List[str]:
        """
        Get list of available template names.
        
        Returns:
            List of template names
        """
        template_dir = self.vault.vault_path / ".obsidian" / "templates"
        if not template_dir.exists():
            return []
            
        templates = []
        for path in template_dir.glob("*.md"):
            name = path.stem
            if name not in self._template_cache:
                # Load template frontmatter
                async with open(path) as f:
                    content = f.read()
                template = await self.parse(content)
                if template:
                    self._template_cache[name] = template._data
            templates.append(name)
            
        return templates

    async def get_schemas(self) -> List[str]:
        """
        Get list of available schema names.
        
        Returns:
            List of schema names
        """
        schema_dir = self.vault.vault_path / ".obsidian" / "schemas"
        if not schema_dir.exists():
            return []
            
        schemas = []
        for path in schema_dir.glob("*.yaml"):
            name = path.stem
            if name not in self._schema_cache:
                # Load schema
                with open(path) as f:
                    self._schema_cache[name] = yaml.safe_load(f)
            schemas.append(name)
            
        return schemas

    async def _get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """Get template by name."""
        if name in self._template_cache:
            return self._template_cache[name]
            
        template_path = (self.vault.vault_path / ".obsidian" / 
                        "templates" / f"{name}.md")
        if not template_path.exists():
            return None
            
        # Load template
        with open(template_path) as f:
            content = f.read()
        template = await self.parse(content)
        
        if template:
            self._template_cache[name] = template._data
            return template._data
            
        return None

    async def _get_schema(self, name: str) -> Optional[Dict[str, Any]]:
        """Get schema by name."""
        if name in self._schema_cache:
            return self._schema_cache[name]
            
        schema_path = (self.vault.vault_path / ".obsidian" / 
                      "schemas" / f"{name}.yaml")
        if not schema_path.exists():
            return None
            
        # Load schema
        with open(schema_path) as f:
            schema = yaml.safe_load(f)
            self._schema_cache[name] = schema
            return schema

    def clear_caches(self) -> None:
        """Clear template and schema caches."""
        self._template_cache.clear()
        self._schema_cache.clear()

    async def create_schema(self, name: str, schema: Dict[str, Any]) -> None:
        """
        Create a new frontmatter schema.
        
        Args:
            name: Schema name
            schema: Schema definition
        """
        schema_dir = self.vault.vault_path / ".obsidian" / "schemas"
        schema_dir.mkdir(parents=True, exist_ok=True)
        
        schema_path = schema_dir / f"{name}.yaml"
        with open(schema_path, 'w') as f:
            yaml.dump(schema, f)
            
        # Update cache
        self._schema_cache[name] = schema

    async def create_template(self, name: str,
                            frontmatter: Dict[str, Any]) -> None:
        """
        Create a new frontmatter template.
        
        Args:
            name: Template name
            frontmatter: Template frontmatter
        """
        template_dir = self.vault.vault_path / ".obsidian" / "templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        
        template_path = template_dir / f"{name}.md"
        content = "---\n"
        content += yaml.dump(frontmatter)
        content += "---\n"
        
        with open(template_path, 'w') as f:
            f.write(content)
            
        # Update cache
        self._template_cache[name] = frontmatter

import re
import yaml
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class FrontmatterBlock:
    """Represents parsed frontmatter with original text."""
    raw_text: str
    data: Dict[str, Any]
    errors: List[str]

class FrontmatterPreprocessor:
    """Handles preprocessing of frontmatter before YAML parsing."""
    
    # Updated patterns to handle nested brackets and quotes
    PATTERNS = [
        # Handle extra closing brackets and quotes in wiki-links
        (r'\[\[(.*?)\]\](\]*)("*)', r'"[[\1]]"'),  # Convert [[link]]" or [[link]]] to "[[link]]"
        
        # Handle regular wiki-links
        (r'\[\[(.*?)\]\]', r'"[[\1]]"'),  # Basic wiki-link quoting
        
        # Clean up other syntax
        (r'::+', ':'),  # Multiple colons to single
        (r'(\s*:\s*$)', ': ""'),  # Empty values
        (r'(\w+:.*?):', r'\1\\:'),  # Escape colons in values
        
        # Quote values that need it
        (r'(\s*[^\s]+):\s*([^"\'].+)$', r'\1: "\2"'),  # Quote unquoted values
    ]

    @classmethod
    def preprocess(cls, text: str) -> str:
        """Apply all preprocessing rules."""
        lines = []
        in_list = False
        list_indent = 0

        for line in text.splitlines():
            processed = line
            
            # Handle list items
            if line.lstrip().startswith('- '):
                in_list = True
                if not list_indent:
                    list_indent = len(line) - len(line.lstrip())
                    
                # Clean up list item values
                processed = re.sub(r'^(\s*-\s*)(.+?)(\]*)("*)$', r'\1"\2"', processed)
                lines.append(processed)
                continue

            # Apply patterns
            for pattern, repl in cls.PATTERNS:
                processed = re.sub(pattern, repl, processed)

            lines.append(processed)

        return '\n'.join(lines)

class FrontmatterParser:
    """Main frontmatter parsing system."""
    
    @staticmethod
    def extract_frontmatter(content: str) -> Optional[Tuple[str, str]]:
        """Extract frontmatter block from content."""
        pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(pattern, content, re.DOTALL)
        if not match:
            return None
        return match.group(1), content[match.end():]
    
    @classmethod
    def parse(cls, content: str, strict: bool = False) -> FrontmatterBlock:
        """
        Parse frontmatter with fallback strategies.
        
        Args:
            content: Full document content
            strict: Whether to raise errors or collect them
            
        Returns:
            FrontmatterBlock with parsed data and any errors
        """
        errors = []
        extracted = cls.extract_frontmatter(content)
        
        if not extracted:
            return FrontmatterBlock("", {}, ["No frontmatter found"])
            
        frontmatter_text, _ = extracted
        original_text = frontmatter_text
        
        # Try increasingly aggressive parsing strategies
        strategies = [
            ('standard', lambda t: yaml.safe_load(t)),
            ('preprocessed', lambda t: yaml.safe_load(FrontmatterPreprocessor.preprocess(t))),
            ('quoted', lambda t: yaml.safe_load(cls._quote_all_values(t))),
            ('basic', cls._parse_basic_pairs)
        ]
        
        data = {}
        for name, strategy in strategies:
            try:
                data = strategy(frontmatter_text)
                if isinstance(data, dict):
                    return FrontmatterBlock(original_text, data, errors)
            except Exception as e:
                errors.append(f"Strategy {name} failed: {str(e)}")
                continue

        # After trying all strategies, handle the failure
        if strict:
            raise ValueError("All parsing strategies failed")
        else:
            logger.warning(f"All parsing strategies failed: {errors}")
            return FrontmatterBlock(original_text, {}, errors)

    # ...existing code...
    
    @staticmethod
    def _quote_all_values(text: str) -> str:
        """Quote all values in YAML."""
        lines = []
        for line in text.splitlines():
            if ':' in line:
                key, value = line.split(':', 1)
                value = value.strip()
                if value and not (value.startswith('"') or value.startswith("'")):
                    line = f'{key}: "{value}"'
            lines.append(line)
        return '\n'.join(lines)
    
    @staticmethod
    def _parse_basic_pairs(text: str) -> Dict[str, Any]:
        """Parse as simple key-value pairs."""
        data = {}
        current_key = None
        current_value = []
        
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
                
            # New key-value pair
            if ':' in line and not line.startswith('-'):
                if current_key and current_value:
                    data[current_key] = '\n'.join(current_value).strip()
                key, value = line.split(':', 1)
                current_key = key.strip()
                current_value = [value.strip()]
            # List item
            elif line.startswith('-'):
                if current_key:
                    if not isinstance(data.get(current_key), list):
                        data[current_key] = []
                    data[current_key].append(line[1:].trip())
            # Continuation of previous value
            elif current_key:
                current_value.append(line)
                
        # Add final key-value pair
        if current_key and current_value:
            data[current_key] = '\n'.join(current_value).strip()
            
        return data
            
        return data