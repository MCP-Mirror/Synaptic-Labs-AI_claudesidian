# Claudesidian
An MCP server to have full control of your obsidian vault (and much more!)

Under Construction, open to contributions!

## Instructions
1. Find your claude_desktop_config (in the desktop app go to settings, developer, config, open it).
2. Input the following into the config file.
```json
{
  "mcpServers": {
    "claudesidian_mcp": {
      "command": "claudesidian",
      "args": [
        "path/to/your/vault"
      ]
    }
  }
}
```
3. Clone the Repo.
4. Open up your terminal and type in `pip install e .` (don't forget the period).
5. After everything is built/installed type in `claudesidian "path/to/your/vault"` and hit enter.
6. Open the Claude Desktop app (or fully restart, by ending it as a task in your task manager), start a new chat, and ask it to do things like search, add, or edit notes in your vault.
