# Installation Guide

## Prerequisites

- Python 3.9 or higher
- pip (Python package installer)
- Git (for installing from source)

## Installation Methods

### Method 1: From PyPI (Recommended - when published)

Once the package is published to PyPI:

```bash
pip install bridge-deals-ingest
```

### Method 2: From Source (Development)

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/bridge-deals-ingest.git
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

### Method 3: Install from GitHub directly

```bash
pip install git+https://github.com/yourusername/bridge-deals-ingest.git
```

## Verifying Installation

After installation, verify that the command-line tool is available:

```bash
bridge-ingest --help
```

You should see the help message with available options.

## Optional: Double-Dummy Solver Support

The package includes optional support for double-dummy analysis using DDS (Double Dummy Solver).

### Windows

The `dds.dll` file is included in the package. No additional setup is required.

### macOS/Linux

You need to compile or obtain the DDS library for your platform:

1. Download DDS source from: https://github.com/dds-bridge/dds
2. Follow the compilation instructions for your platform
3. Place the compiled library in the package directory

## Troubleshooting

### Import Errors

If you encounter import errors, ensure all dependencies are installed:

```bash
pip install -r requirements.txt
```

### Permission Issues

If you encounter permission issues on Windows, try:

```bash
pip install --user bridge-deals-ingest
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

Ensure you're using Python 3.9 or higher:

```bash
python --version
```

If you have multiple Python versions, you may need to use `python3` or `python3.9` explicitly.

## Uninstalling

To uninstall the package:

```bash
pip uninstall bridge-deals-ingest
```

## Updating

### From PyPI

```bash
pip install --upgrade bridge-deals-ingest
```

### From Source

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




