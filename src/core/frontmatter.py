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

from . import Frontmatter, InvalidFrontmatterError
from ..utils.path_resolver import PathResolver

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
        fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not fm_match:
            return None
            
        try:
            data = yaml.safe_load(fm_match.group(1))
            if not isinstance(data, dict):
                raise InvalidFrontmatterError("Frontmatter must be a dictionary")
            return Frontmatter(data)
        except yaml.YAMLError as e:
            raise InvalidFrontmatterError(f"Invalid YAML in frontmatter: {e}")

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