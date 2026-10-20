# Installation Guide

## Prerequisites

- Python 3.10 or higher (3.11 or 3.12 recommended: endplay publishes ready-built packages for these)
- pip (Python package installer)
- Git (for installing from source)

## Installation Methods

### Method 1: From Source

1. **Clone the repository**
   ```bash
   git clone https://github.com/ureshvahalia/bridge-deals-ingest.git
   cd bridge-deals-ingest
   ```

2. **Create a virtual environment (recommended)**
   
   On Windows:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
   
   On macOS/Linux:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install the package**
   
   For regular use:
   ```bash
   pip install -e .
   ```
   
   For development (includes testing tools):
   ```bash
   pip install -e ".[dev]"
   ```

### Method 2: Install from GitHub directly

```bash
pip install git+https://github.com/ureshvahalia/bridge-deals-ingest.git
```

## Verifying Installation

After installation, verify that the command-line tool is available:

```bash
bridge-ingest --help
```

You should see the help message with available options.

## Double-Dummy Solver (endplay)

Double-dummy analysis (`-d`, `--reuse-dd`) uses DDS through the [endplay](https://pypi.org/project/endplay/)
package, which bundles DDS for Windows, macOS and Linux. It is installed automatically as a dependency;
nothing needs to be compiled or copied.

## Optional: PlayDD (play normalisation and play analysis)

PlayDD does card-by-card double-dummy analysis of the play. It is used to:

- Normalise `Play` into play order, including reordering PBN seat-column plays
- Run play analysis (`--play`, `--playonly`)
- Fix the play in an existing DB (`--normalizeplay`, `--repairplay`)

PlayDD is not yet publicly available; it is available on request (open an issue on this repository). It needs
Python 3.11 or 3.12. Once you have a copy, install it into the same environment:

```bash
pip install -e <path to PlayDD>
```

Without PlayDD, the ingest still runs, but `Play` is left as parsed, `PlayEncoding` is empty, and the play analysis
options fail.

## Troubleshooting

### Import Errors

If you encounter import errors, ensure all dependencies are installed:

```bash
pip install -r requirements.txt
```

### Permission Issues

If you encounter permission issues on Windows, try installing into a virtual environment (step 2 above), or:

```bash
pip install --user -e .
```

### Virtual Environment Issues

If you have issues with the virtual environment, try recreating it:

```bash
deactivate  # If already in a venv
rm -rf venv  # On Windows: rmdir /s venv
python -m venv venv
# Activate and reinstall
```

### Python Version Issues

Ensure you're using Python 3.10 or higher:

```bash
python --version
```

If you have multiple Python versions, you may need to use `python3` or `python3.11` explicitly. On Windows,
`py -3.11` selects a specific version.

## Uninstalling

To uninstall the package:

```bash
pip uninstall bridge-deals-ingest
```

## Updating

```bash
cd bridge-deals-ingest
git pull origin main
pip install -e . --upgrade
```

## Platform-Specific Notes

### Windows

- Use PowerShell or Command Prompt
- File paths use backslashes: `C:\data\tournament.pbn`
- Virtual environment activation: `venv\Scripts\activate`

### macOS

- May need to install Python via Homebrew: `brew install python@3.11`
- Virtual environment activation: `source venv/bin/activate`

### Linux

- May need to install Python development headers: `sudo apt-get install python3-dev`
- Virtual environment activation: `source venv/bin/activate`

## Next Steps

After installation, see the [README.md](README.md) for usage instructions and examples.
