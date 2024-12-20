# Claudesidian

A bridge between Claude and Obsidian using the MCP protocol.

## Installation

1. Ensure you have Python 3.9 or newer installed
2. Install the package:
   ```bash
   pip install claudesidian
   ```

## Configuration

1. Locate your Claude Desktop configuration file:
   - Windows: `%APPDATA%/Claude/claude_desktop_config.json`
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Linux: `~/.config/Claude/claude_desktop_config.json`

2. Add the following to your configuration file:
   ```json
   {
     "mcpServers": {
       "claudesidian": {
         "command": "claudesidian",
         "args": [
           "path/to/your/obsidian/vault"
         ]
       }
     }
   }
   ```
   Replace `path/to/your/obsidian/vault` with the actual path to your Obsidian vault.

3. **Optional:** If you've set up environment variables or additional configurations, ensure they are correctly referenced here.

## Usage

1. Start Claude Desktop
2. The connection to your Obsidian vault will be established automatically
3. You can now use Claude to interact with your vault

## Troubleshooting

If you encounter any issues:

1. Check that your vault path is correct and accessible
2. Ensure Python is in your system PATH
3. Try running `claudesidian --version` in your terminal to verify the installation
4. Check the Claude Desktop logs for any error messages
