# Renamr

A Python GUI application that extracts character names from text files using an LLM and allows batch renaming/replacement.

## Features

- Load `.txt` **and `.epub`** files with automatic encoding detection
- Extract character names using OpenAI-compatible LLM APIs
- Auto-route to Ollama native chat API when endpoint port is `11434`
- Review and edit name mappings in a two-column table
- Replace only edited names and export to `*_processed.txt` or `*_processed.epub`
- For EPUB: the output preserves the book's structure (chapters, CSS, images, TOC); only text nodes inside XHTML/NCX are rewritten
- Persistent LLM and prompt configuration

### EPUB notes

- **Scope.** Replacements touch every XHTML `<body>`/`<title>` text node and every NCX `<text>` node (so EPUB 2 tables of contents stay in sync). Non-text assets (CSS, images, fonts, audio) pass through byte-for-byte.
- **Inline-span coalescing.** Adjacent text nodes inside the same `<span>`/`<em>`/`<i>`/... parent are matched as one string, so names split by packaging artifacts like `<span>张</span><span>三</span>` are still replaced. Coalescing is skipped whenever the adjacent parents differ in tag or attributes, to avoid destroying inline styling.
- **Known limitations.** Names split across ruby (`<ruby>`/`<rt>`) annotations are not matched. `alt=`, `aria-label=`, and `title=` attributes are NOT rewritten. DRM-protected or font-obfuscated EPUBs are detected and rejected rather than silently produced as unreadable output.
- **Normalize Layout** is txt-only — the button hides itself when an EPUB is loaded.

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

1. Click "Select File" to choose a `.txt` or `.epub` file
2. Configure LLM settings via "Settings" button (first time only)
3. Click "Extract Names" to extract character names from the text
4. Edit replacement names in the table (second column)
5. Click "Replace & Export" to generate the processed file (same format as the input)

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
