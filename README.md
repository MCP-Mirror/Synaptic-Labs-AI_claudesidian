# Claudesidian MCP Server

## Introduction

Welcome to the **Claudesidian MCP Server**! This project allows seamless interaction with your Obsidian vault through a robust server setup. Whether you're a beginner or an experienced user, follow these step-by-step instructions to get the server up and running.

## Prerequisites

Before setting up the server, ensure you have the following installed on your system:

- [Python 3.9+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- [Playwright](https://playwright.dev/docs/intro) (for web scraping capabilities)

## Installation Steps

1. **Clone the Repository via Your IDE**

   Open your preferred IDE (e.g., Visual Studio Code) and follow these steps to clone the repository:

   **Using Visual Studio Code:**

   - Open VS Code.
   - Click on the **Source Control** icon in the Activity Bar on the side.
   - Click on **Clone Repository**.
   - Enter the repository URL: `https://github.com/Synaptic-Labs-AI/claudesidian.git`.
   - Choose a local directory where you want to save the project.
   - After cloning, open the project folder in VS Code.

2. **Configure `claude_desktop_config.json`**

   Update the `claude_desktop_config.json` file with the correct paths:

   ```json
   {
     "mcpServers": {
       "claudesidian": {
         "command": "claudesidian",
         "args": [
           "PATH_TO_YOUR_OBSIDIAN_VAULT"
         ]
       }
     }
   }
   ```

   - Replace `PATH_TO_YOUR_OBSIDIAN_VAULT` with the actual path to your Obsidian vault directory.

3. **Install Dependencies**

Open up your terminal and run the following two commands.

   ```python
   pip install -e .
   ```

   ```python
   playwright install
   ```

5. **Run the Server**

   ```python
   claudesidian "PATH_TO_YOUR_OBSIDIAN_VAULT"
   ```

   - Replace `PATH_TO_YOUR_OBSIDIAN_VAULT` with the actual path to your Obsidian vault directory.

## Available Tools

- **Reasoning Tool**: Manages reasoning schemas to guide complex problem-solving processes.
- **CreateMemory Tool**: Stores important information as memories at the end of each interaction.
- **FuzzySearch Tool**: Performs fuzzy searches within the vault to find relevant notes quickly.
- **ScrapeWebsite Tool**: Scrapes authorized web content and archives it as notes in your vault.
- **CreateNote Tool**: Facilitates the creation of new notes within your Obsidian vault.
- **EditNote Tool**: Allows editing of existing notes in the vault.
- **MemoryRetrieval Tool**: Retrieves and synthesizes memories from the vault based on queries.
- **Relationships Tool**: Manages relationship information and connections between different notes or entities.

## Troubleshooting

If you encounter any issues:

1. Ensure that your terminal in the IDE is opened in the correct project directory before running install and run commands.
2. Check that your vault path is correct and accessible.
3. Ensure Python is in your system PATH.
4. Try running `claudesidian --version` in your terminal to verify the installation.
5. Check the Claude Desktop logs for any error messages. You can navigate to the logs directory at `C:/Users/<YourUsername>/AppData/Roaming/Claude/logs`.

### Contributions

We welcome contributions from the community! Here are ways you can help:

- **QA Testing**: Help us identify bugs and improve the server's stability.
- **Enhancements**: Suggest or implement new features to expand functionality.
- **Feedback**: Leave your comments and suggestions in the [discussion](https://github.com/Synaptic-Labs-AI/claudesidian/discussions) section to help guide future developments.
