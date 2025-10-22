# Contributing to Bridge Deals Ingest

Thank you for considering contributing to Bridge Deals Ingest! This document provides guidelines and instructions for contributing.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue on GitHub with:
- A clear, descriptive title
- Steps to reproduce the problem
- Expected behavior vs. actual behavior
- Your environment (OS, Python version, package versions)
- Sample data files if applicable (ensure no private information)

### Suggesting Enhancements

Enhancement suggestions are welcome! Please create an issue with:
- A clear description of the enhancement
- Why this enhancement would be useful
- Examples of how it would work

### Pull Requests

1. **Fork the Repository**
   ```bash
   git clone https://github.com/yourusername/bridge-deals-ingest.git
   cd bridge-deals-ingest
   ```

2. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Set Up Development Environment**
   ```bash
   # Create virtual environment
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   
   # Install in development mode with dev dependencies
   pip install -e ".[dev]"
   ```

4. **Make Your Changes**
   - Write clear, readable code
   - Follow existing code style
   - Add docstrings to functions and classes
   - Update documentation if needed

5. **Test Your Changes**
   ```bash
   # Run tests
   pytest
   
   # Check code formatting
   black .
   ruff check .
   ```

6. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "Add: Brief description of changes"
   ```
   
   Use conventional commit messages:
   - `Add:` for new features
   - `Fix:` for bug fixes
   - `Update:` for updates to existing functionality
   - `Docs:` for documentation changes
   - `Refactor:` for code refactoring
   - `Test:` for test additions/changes

7. **Push and Create Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```
   
   Then create a pull request on GitHub with:
   - Clear description of changes
   - Reference to any related issues
   - Screenshots if applicable

## Development Guidelines

### Code Style

- Follow PEP 8 guidelines
- Use type hints where possible
- Maximum line length: 120 characters
- Use meaningful variable and function names
- Add comments for complex logic

### Testing

- Add tests for new features
- Ensure existing tests pass
- Aim for good test coverage

### Documentation

- Update README.md if adding new features
- Add docstrings to public functions/classes
- Include usage examples where helpful

### File Format Parsers

If adding support for a new file format:

1. Create a new parser file: `format_parse.py`
2. Implement a function: `parse_format_file(file_path: Path) -> List[BoardRecord]`
3. Register the parser in `ingest.py`
4. Add tests for the new format
5. Update documentation

### Performance Considerations

- Use Polars for data operations when possible
- Profile code for performance bottlenecks
- Consider memory usage for large datasets
- Use parallel processing where beneficial

## Project Structure

```
ingest/
├── __init__.py          # Package initialization
├── driver.py            # CLI entry point
├── ingest.py           # File ingestion coordinator
├── *_parse.py          # Format-specific parsers
├── process_records.py  # Core processing logic
├── auction.py          # Auction processing
├── scoring.py          # Scoring calculations
├── common_objects.py   # Data structures
├── fuzzy.py           # Event deduplication
└── dds_wrapper.py     # Double-dummy solver wrapper
```

## Need Help?

Feel free to:
- Open an issue with questions
- Ask for clarification on existing issues
- Request guidance on implementation approaches

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Assume good intentions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.







