"""
code_summary.py

This script generates a directory tree, collects selected code files,
sends the directory structure and code files to an LLM for analysis,
and compiles everything into a single Markdown file.
The final report includes a table of contents, directory structure,
LLM analysis, and code files. It also allows selective analysis based on
selected files or directories and includes a timestamp of when the report was generated.
Additionally, it manages the output directory and ensures it's excluded from git tracking.
"""

import os
import sys
import argparse
import fnmatch
import requests
import datetime
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Any
import questionary  # Replace PyInquirer import

# Load environment variables
load_dotenv()

# Configuration
CONFIG = {
    'output_dir': 'codeSummaryLogs',
    'excluded_dirs': [
        '.git',
        'node_modules',
        'dist',
        'build',
        'coverage',
        'logs',
        'tmp',
        '.vscode',
        '.svelte-kit',
        'outlines',
        'codeSummaryLogs',  # Ensure the output directory is excluded
        '.venv',  # Add virtual environment folder
        'venv'    # Also exclude common 'venv' folder name
    ],
    'excluded_files': [
        '.DS_Store',
        'Thumbs.db',
        'package-lock.json',
        'yarn.lock',
        'pnpm-lock.yaml',
        '.env',
        '.gitignore',
        '*.config.js',
        '*codesummary*'
    ],
    'api': {
        'url': 'https://openrouter.ai/api/v1/chat/completions',
        'key': os.getenv('OPENROUTER_API_KEY'),
        'site_url': os.getenv('YOUR_SITE_URL', ''),
        'site_name': os.getenv('YOUR_SITE_NAME', '')
    }
}

# Validate API Key
if not CONFIG['api']['key']:
    print('Error: OPENROUTER_API_KEY is not set in the .env file.', file=sys.stderr)
    sys.exit(1)

def get_formatted_date() -> str:
    """Format current date and time."""
    return datetime.datetime.now().isoformat().replace(':', '-').split('.')[0]

def ensure_output_directory():
    """Ensure the output directory exists."""
    dir_path = Path.cwd() / CONFIG['output_dir']
    try:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f'Output directory ready: {CONFIG["output_dir"]}')
    except Exception as e:
        print(f'Failed to create output directory: {e}', file=sys.stderr)
        sys.exit(1)

def display_help():
    """Display usage instructions."""
    help_text = """
Usage: python code_summary.py [options]

Options:
  --target, -t <path>       Specify files or directories to analyze. You can provide multiple targets by repeating the flag or separating them with commas.
  --interactive, -i        Launch interactive mode to select files/directories.
  --help, -h                Display this help message.

Examples:
  Analyze the entire project (default):
    python code_summary.py

  Analyze specific directories:
    python code_summary.py --target src/components --target src/utils

  Analyze specific files and directories:
    python code_summary.py -t src/components,src/utils/helpers.py,README.md

  Launch interactive selection:
    python code_summary.py --interactive
"""
    print(help_text)

def is_excluded(name: str, is_dir: bool) -> bool:
    """Check if a file or directory should be excluded."""
    if is_dir:
        return name in CONFIG['excluded_dirs'] or 'codesummary' in name.lower()
    else:
        for pattern in CONFIG['excluded_files']:
            if fnmatch.fnmatchcase(name, pattern):
                return True
        return False

def traverse_directory(dir_path: Path, depth: int = 0) -> List[Dict[str, Any]]:
    """
    Traverse the directory and collect files with depth information.

    :param dir_path: Directory path
    :param depth: Current depth level
    :return: List of file and directory objects with name, path, is_directory, and depth
    """
    results = []
    try:
        for item in dir_path.iterdir():
            if is_excluded(item.name, item.is_dir()):
                continue
            relative_path = str(item.relative_to(Path.cwd())).replace(os.sep, '/')
            results.append({
                'name': item.name,
                'path': relative_path,
                'is_directory': item.is_dir(),
                'depth': depth
            })
            if item.is_dir():
                results.extend(traverse_directory(item, depth + 1))
    except Exception as e:
        print(f'Error reading directory {dir_path}: {e}', file=sys.stderr)
    return results

def format_choices(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format choices with indentation based on depth."""
    choices = []
    items_by_path = {item['path']: item for item in items}
    
    for item in items:
        indent = '  ' * item['depth']
        if item['is_directory']:
            # Create a group header for directories
            icon = '📁'
            choices.append({
                'name': f"{indent}{icon} {item['name']}/",
                'value': item['path'],
                'checked': False
            })
            
            # Add nested files with different styling
            nested_files = [
                i for i in items 
                if (not i['is_directory'] and 
                    i['path'].startswith(item['path'] + '/'))
            ]
            
            if nested_files:
                nested_indent = indent + '  '
                for nested in nested_files:
                    rel_path = nested['path'][len(item['path'])+1:]
                    choices.append({
                        'name': f"{nested_indent}└─ 📄 {rel_path}",
                        'value': nested['path'],
                        'disabled': "Will be included with parent directory"  # This will show as greyed out
                    })
        else:
            # Only show files that aren't nested under an already-listed directory
            parent_dir = str(Path(item['path']).parent)
            if parent_dir == '.':  # Files in root directory
                icon = '📄'
                choices.append({
                    'name': f"{indent}{icon} {item['name']}", 
                    'value': item['path'],
                    'checked': False
                })
    
    return choices

def launch_interactive_selection(all_items: List[Dict[str, Any]]) -> List[str]:
    """Launch interactive selection using questionary checkbox."""
    print('Launching interactive selection mode...')
    choices = format_choices(all_items)
    
    try:
        selected = questionary.checkbox(
            'Select files and directories to include in the analysis (space to select, enter to confirm):',
            choices=[{'name': c['name'], 'value': c['value']} for c in choices]
        ).ask()
        
        if not selected:
            print('No items selected. Exiting.', file=sys.stderr)
            sys.exit(1)
        return selected
    except Exception as e:
        print(f'Error during selection: {e}', file=sys.stderr)
        sys.exit(1)

def process_selections(selected: List[str], all_items: List[Dict[str, Any]]) -> List[str]:
    """
    Process selected targets and include all nested files if a directory is selected.

    :param selected: List of selected file and directory paths
    :param all_items: Complete list of all file and directory objects
    :return: Final list of file paths to process
    """
    files_to_process = set()
    items_map = {item['path']: item for item in all_items}

    def add_directory_files(dir_path: str):
        """Helper function to recursively add all files in a directory."""
        for item in all_items:
            if item['path'].startswith(dir_path + '/'):  # Check if item is under this directory
                if item['is_directory']:
                    # Recursively process nested directories
                    add_directory_files(item['path'])
                else:
                    files_to_process.add(item['path'])

    for selected_path in selected:
        item = items_map.get(selected_path)
        if item:
            if item['is_directory']:
                # Add all files in this directory and its subdirectories
                add_directory_files(selected_path)
                # Also add any files directly in this directory
                for child in all_items:
                    if (not child['is_directory'] and 
                        child['path'].startswith(selected_path + '/') and 
                        '/' not in child['path'][len(selected_path)+1:]):
                        files_to_process.add(child['path'])
            else:
                files_to_process.add(selected_path)

    return sorted(list(files_to_process))  # Sort for consistent ordering

def read_file_content(file_path: Path, max_size: int = 1_000_000) -> str:
    """
    Read file content with size limitation.

    :param file_path: The path of the file to read
    :param max_size: Maximum allowed file size in bytes
    :return: The file content or None if exceeds size limit
    """
    try:
        if file_path.stat().st_size > max_size:
            print(f"Skipping {file_path} (exceeds size limit of {max_size} bytes).")
            return None
        with file_path.open('r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}", file=sys.stderr)
        return None

def collect_files(targets: List[str]) -> List[str]:
    """
    Collect files from selected targets.

    :param targets: List of file/directory paths
    :return: List of file paths
    """
    files_list = []
    for target in targets:
        resolved_path = Path.cwd() / target
        if not resolved_path.exists():
            print(f'Warning: Target path "{target}" does not exist or is inaccessible. Skipping.', file=sys.stderr)
            continue
        if resolved_path.is_dir():
            nested_files = get_all_files(resolved_path)
            files_list.extend(nested_files)
        elif resolved_path.is_file():
            files_list.append(str(resolved_path.relative_to(Path.cwd())).replace(os.sep, '/'))
    return files_list

def get_all_files(dir_path: Path) -> List[str]:
    """
    Recursively get all files in a directory.

    :param dir_path: Directory path
    :return: List of file paths
    """
    files_list = []
    try:
        for item in dir_path.rglob('*'):
            if item.is_file() and not is_excluded(item.name, False):
                relative_path = str(item.relative_to(Path.cwd())).replace(os.sep, '/')
                files_list.append(relative_path)
    except Exception as e:
        print(f'Error reading directory {dir_path}: {e}', file=sys.stderr)
    return files_list

def send_to_openrouter(prompt: str) -> str:
    """
    Send data to OpenRouter API.

    :param prompt: The prompt to send to the LLM
    :return: The LLM's response
    """
    headers = {
        'Authorization': f'Bearer {CONFIG["api"]["key"]}',
        'HTTP-Referer': CONFIG['api']['site_url'],
        'X-Title': CONFIG['api']['site_name'],
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'anthropic/claude-3.5-sonnet:beta',
        'messages': [{'role': 'user', 'content': prompt}]
    }

    try:
        response = requests.post(CONFIG['api']['url'], json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        if content:
            return content
        else:
            print('No response content from OpenRouter API.', file=sys.stderr)
            return ''
    except requests.RequestException as e:
        print(f'Error communicating with OpenRouter API: {e}', file=sys.stderr)
        return ''

def analyze_codebase(directory_tree: str, file_data: Dict[str, Dict[str, str]]) -> str:
    """
    Analyze the codebase using LLM.

    :param directory_tree: The directory tree as a string
    :param file_data: An object containing file paths and their content
    :return: The analysis content
    """
    print('Analyzing codebase with LLM...')
    if not file_data:
        print('No files available for analysis.', file=sys.stderr)
        return ''

    # Prepare prompt for LLM with an example
    file_sections = []
    for file, data in file_data.items():
        language = file.split('.')[-1] if '.' in file else 'plaintext'
        content_section = f"### {file}\n```{language}\n{data['content']}\n```"
        file_sections.append(content_section)
    files_content = "\n\n".join(file_sections)

    prompt = f"""
I have a codebase with the following directory structure:

{directory_tree.strip()}

Below are the files and their contents:

{files_content}

**Your Task:**

For each file provided:

1. **Explain in detail** what the code file does.
2. **Describe** how it interacts with other files that it is importing.
3. **Output a mermaid diagram** representing the interactions for each file. Use appropriate mermaid syntax (e.g., `graph TD`).

Please format your response for each file as follows:

### [File Path]

**Explanation:**

[Your detailed explanation here.]

**Interactions:**

[Description of how this file interacts with other files.]

**Mermaid Diagram:**

```mermaid
[Your mermaid diagram code here.]
```
Avoid including unnecessary code snippets in your explanations. Be clear and concise. """
    
    # Send prompt to OpenRouter
    analysis = send_to_openrouter(prompt)
    if analysis:
        return analysis
    else:
        print('Error: No analysis was received from OpenRouter.', file=sys.stderr)
        return ''

def generate_table_of_contents(sections: List[str]) -> str:
    """ Generate a table of contents based on the sections.
    :param sections: List of section names
    :return: The table of contents in Markdown format
    """
    toc = '# Table of Contents\n\n'
    for section in sections:
        anchor = section.lower().replace(' ', '-')
        toc += f'- [{section}](#{anchor})\n'
    toc += '\n'
    return toc

def add_folder_to_gitignore(folder_name: str):
    """ Add a folder to .gitignore.
    :param folder_name: The folder to add to .gitignore
    """
    gitignore_path = Path.cwd() / '.gitignore'
    folder_entry = f'{folder_name}/'
    
    try:
        if (gitignore_path.exists()):
            with gitignore_path.open('r', encoding='utf-8') as f:
                lines = f.read().splitlines()
        else:
            lines = []
    
        if folder_entry not in lines:
            with gitignore_path.open('a', encoding='utf-8') as f:
                f.write(f'\n{folder_entry}\n')
            print(f'Added "{folder_entry}" to .gitignore.')
        else:
            print(f'"{folder_entry}" is already present in .gitignore.')
    except Exception as e:
        print(f'Error updating .gitignore: {e}', file=sys.stderr)
    return

def generate_directory_tree(dir_path: Path, prefix: str = '') -> str:
    """ Generate directory tree using improved ASCII characters.
    :param dir_path: The directory path to start from
    :param prefix: The prefix for the current level
    :return: The formatted directory tree as a string
    """
    tree = ''
    try:
        items = sorted(
            [item for item in dir_path.iterdir() if not is_excluded(item.name, item.is_dir())],
            key=lambda x: (not x.is_dir(), x.name.lower())
        )
        for index, item in enumerate(items):
            connector = '└── ' if index == len(items) - 1 else '├── '
            tree += f'{prefix}{connector}{item.name}\n'
            if item.is_dir():
                extension = '    ' if index == len(items) - 1 else '│   '
                tree += generate_directory_tree(item, prefix + extension)
    except Exception as e:
        print(f'Error reading directory {dir_path}: {e}', file=sys.stderr)
    return tree

def is_directory(target: str) -> bool:
    """ Check if a path is a directory.
    :param target: Path to check
    :return: True if directory, False otherwise
    """
    return (Path.cwd() / target).is_dir()

def main():
    """Main execution function."""
    try:
        import questionary
    except ModuleNotFoundError as e:
        print(f"Missing module: {e.name}. Please install it by running 'pip install {e.name}'.", file=sys.stderr)
        sys.exit(1)
        
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--target', '-t', action='append', help='Specify files or directories to analyze. Separate multiple targets with commas.')
    parser.add_argument('--interactive', '-i', action='store_true', help='Launch interactive mode to select files/directories.')
    parser.add_argument('--help', '-h', action='store_true', help='Display help message.')
    args = parser.parse_args()
    
    if args.help:
        display_help()
        sys.exit(0)
    
    targets = []
    interactive = False
    
    if args.interactive:
        interactive = True
    elif args.target:
        for target_group in args.target:
            targets.extend([t.strip() for t in target_group.split(',') if t.strip()])
    else:
        # If no targets specified, launch interactive mode
        print('No targets specified. Launching interactive selection mode...')
        interactive = True
    
    # Traverse the directory and collect all selectable items
    print('Scanning directories...')
    all_items = traverse_directory(Path.cwd())
    
    selected_targets = []
    
    if interactive:
        selected_targets = launch_interactive_selection(all_items)
    else:
        selected_targets = targets
    
    # Ensure the output directory exists
    ensure_output_directory()
    
    # Add the output directory to .gitignore
    add_folder_to_gitignore(CONFIG['output_dir'])
    
    # Determine files to process
    files_to_process = []
    if selected_targets:
        print('Selected targets for analysis:', selected_targets)
        files_to_process = process_selections(selected_targets, all_items)
        if not files_to_process:
            print('No valid files found for the specified targets. Exiting.', file=sys.stderr)
            sys.exit(1)
    else:
        print('Analyzing the entire project.')
        files_to_process = collect_files(['.'])
    
    # Initialize the output file
    timestamp = get_formatted_date()
    output_file = Path(CONFIG['output_dir']) / f'CodeAnalysis_{timestamp}.md'
    try:
        output_file.touch(exist_ok=True)
        print(f'Initialized {output_file}')
    except Exception as e:
        print(f'Error initializing output file: {e}', file=sys.stderr)
        sys.exit(1)
    
    sections = {}
    
    # Generate directory tree based on selected targets
    print('Generating directory tree...')
    directory_tree = ''
    
    if len(selected_targets) == 1 and is_directory(selected_targets[0]):
        directory_tree = generate_directory_tree(Path.cwd() / selected_targets[0])
    else:
        for target in selected_targets:
            resolved_path = Path.cwd() / target
            if resolved_path.is_dir():
                directory_tree += generate_directory_tree(resolved_path)
            else:
                directory_tree += f"{resolved_path.name}\n"
    
    sections['Directory'] = f"```\n{directory_tree}\n```"
    print('Generated directory tree.')
    
    # Collect files and their contents
    print('Collecting files and their contents...')
    file_data = {}
    for file_path_str in files_to_process:
        file_path = Path.cwd() / file_path_str
        content = read_file_content(file_path)
        if content is not None:
            file_data[file_path_str] = {'content': content}
    
    # Analyze codebase using LLM
    print('Analyzing codebase...')
    analysis = analyze_codebase(directory_tree, file_data)
    sections['Analysis'] = analysis if analysis else 'No analysis was generated.'
    print('Completed analysis.')
    
    # Prepare Code Files section
    print('Preparing Code Files section...')
    code_files_content = ''
    for relative_path, data in file_data.items():
        code_files_content += f"## {relative_path}\n\n"
        file_extension = relative_path.split('.')[-1] if '.' in relative_path else 'plaintext'
        code_files_content += f'```{file_extension}\n{data["content"]}\n```\n\n'
    sections['Code Files'] = code_files_content
    print('Prepared Code Files section.')
    
    # Add timestamp to the report
    generation_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sections['Report Generated On'] = f"*Generated on {generation_time}*\n"
    print('Added timestamp to the report.')
    
    # Generate table of contents
    print('Generating table of contents...')
    toc = generate_table_of_contents(list(sections.keys()))
    print('Generated table of contents.')
    
    # Write all content to the output file
    print('Writing content to the output file...')
    final_content = toc
    for section_name in ['Report Generated On', 'Directory', 'Analysis', 'Code Files']:
        final_content += f"# {section_name}\n\n{sections[section_name]}\n\n"
    try:
        with output_file.open('w', encoding='utf-8') as f:
            f.write(final_content)
        print(f"File '{output_file}' has been successfully created.")
    except Exception as e:
        print(f'Error writing to output file: {e}', file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'An unexpected error occurred: {e}', file=sys.stderr)
        sys.exit(1)