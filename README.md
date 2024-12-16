# claudesidian
An MCP server for your second brain.

claudesidian/
├── pyproject.toml                 # Project metadata and dependencies
├── README.md                      # Project documentation
├── claudesidian/
│   ├── __init__.py               # Package initialization
│   ├── server.py                 # Main MCP server implementation
│   ├── config.py                 # Configuration management
│   │
│   ├── core/                     # Core vault operations
│   │   ├── __init__.py
│   │   ├── vault.py             # Obsidian vault management
│   │   ├── notes.py             # Note CRUD operations
│   │   └── frontmatter.py       # Frontmatter parsing/generation
│   │
│   ├── web/                      # Web scraping capabilities
│   │   ├── __init__.py
│   │   ├── scraper.py           # Puppeteer integration for scraping
│   │   ├── parser.py            # HTML/content parsing
│   │   └── converter.py         # Web content to note conversion
│   │
│   ├── memory/                   # Memory system implementation
│   │   ├── __init__.py
│   │   ├── manager.py           # Main memory system manager
│   │   ├── graph.py             # Knowledge graph implementation
│   │   ├── relationships.py     # Relationship management
│   │   ├── decay.py            # Memory decay system
│   │   └── moc.py              # Maps of Content generation
│   │
│   ├── types/                    # Type definitions
│   │   ├── __init__.py
│   │   ├── memory.py            # Memory-related types
│   │   ├── web.py              # Web-related types
│   │   └── vault.py            # Vault-related types
│   │
│   └── utils/                    # Shared utilities
│       ├── __init__.py
│       ├── async_helpers.py     # Async utility functions
│       ├── text.py             # Text processing utilities
│       └── paths.py            # Path manipulation utilities
│