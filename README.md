# Renamr

A Python GUI application that extracts character names from text files using an LLM and allows batch renaming/replacement.

## Features

- Load `.txt` files with automatic encoding detection
- Extract character names using OpenAI-compatible LLM APIs
- Auto-route to Ollama native chat API when endpoint port is `11434`
- Review and edit name mappings in a two-column table
- Replace only edited names and export to `*_processed.txt`
- Persistent LLM and prompt configuration

## Requirements

- Python 3.11+
- PySide6
- OpenAI-compatible API access (including local Ollama)

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd Renamr

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

## Usage

```bash
# Run the application
Renamr

# Or run directly
python -m txt_process.main
```

### Workflow

1. Click "Select File" to choose a `.txt` file
2. Configure LLM settings via "Settings" button (first time only)
3. Click "Extract Names" to extract character names from the text
4. Edit replacement names in the table (second column)
5. Click "Replace & Export" to generate the processed file

## Configuration

Settings are stored in your user config directory:
- macOS: `~/Library/Application Support/Renamr/config.json`
- Linux: `~/.config/Renamr/config.json`
- Windows: `%APPDATA%\Renamr\config.json`

API keys are stored securely via the system keychain (keyring).

### Using local Ollama

1. Make sure Ollama is running locally.
2. Open Settings:
   - Base URL: `http://localhost:11434` (or `http://localhost:11434/v1`)
   - API Key: leave empty
   - Model: your local model name (e.g. `llama3.1`)
3. When the configured endpoint uses port `11434`, the app automatically uses Ollama's native protocol and calls `/api/chat`.

## Development

```bash
# Run tests
pytest

# Format code
black txt_process tests

# Lint
ruff check txt_process tests
```

## License

MIT
