# Publishing Guide

This guide explains how to publish the package to GitHub and PyPI.

## Prerequisites

Before publishing, ensure you have:

1. **GitHub Account**: Create one at https://github.com
2. **PyPI Account**: Register at https://pypi.org (for PyPI publishing)
3. **Git Installed**: Download from https://git-scm.com
4. **Python Build Tools**: Install with `pip install build twine`

## Part 1: Publishing to GitHub

### Step 1: Create a GitHub Repository

1. Go to https://github.com/new
2. Repository name: `bridge-deals-ingest` (or your preferred name)
3. Description: "A comprehensive tool for ingesting and analyzing bridge game data"
4. Choose Public or Private
5. Do NOT initialize with README (we already have one)
6. Click "Create repository"

### Step 2: Update URLs in Configuration

Edit `pyproject.toml` and replace `yourusername` with your GitHub username:

```toml
[project.urls]
Homepage = "https://github.com/YOUR_USERNAME/bridge-deals-ingest"
Repository = "https://github.com/YOUR_USERNAME/bridge-deals-ingest"
Issues = "https://github.com/YOUR_USERNAME/bridge-deals-ingest/issues"
```

Also update `pyproject.toml` author information:

```toml
authors = [
    {name = "Your Name", email = "your.email@example.com"}
]
```

### Step 3: Initialize Git and Push

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit: Package structure and documentation"

# Add remote (replace YOUR_USERNAME)
git remote add origin https://github.com/YOUR_USERNAME/bridge-deals-ingest.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### Step 4: Create a Release

1. Go to your repository on GitHub
2. Click "Releases" → "Create a new release"
3. Tag version: `v0.1.0`
4. Release title: `v0.1.0 - Initial Release`
5. Description: Copy from CHANGELOG.md
6. Click "Publish release"

### Step 5: Enable GitHub Actions

GitHub Actions will automatically run on pushes and pull requests:
- Go to "Actions" tab in your repository
- Enable workflows if prompted
- The CI/CD pipeline will run tests and build the package

## Part 2: Publishing to PyPI (Optional)

### Step 1: Test the Package Build

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build the package
python -m build

# Check the distribution
twine check dist/*
```

You should see:
```
Checking dist/bridge_deals_ingest-0.1.0-py3-none-any.whl: PASSED
Checking dist/bridge-deals-ingest-0.1.0.tar.gz: PASSED
```

### Step 2: Test on TestPyPI (Recommended)

TestPyPI is a separate instance of PyPI for testing.

1. Register at https://test.pypi.org
2. Generate API token at https://test.pypi.org/manage/account/token/
3. Upload to TestPyPI:

```bash
twine upload --repository testpypi dist/*
```

4. Test installation:

```bash
pip install --index-url https://test.pypi.org/simple/ bridge-deals-ingest
```

### Step 3: Publish to PyPI

1. Register at https://pypi.org (if not already)
2. Generate API token at https://pypi.org/manage/account/token/
3. Upload to PyPI:

```bash
twine upload dist/*
```

4. Verify installation:

```bash
pip install bridge-deals-ingest
```

### Step 4: Configure GitHub Actions for Automated Publishing

Create `.github/workflows/publish.yml`:

```yaml
name: Publish to PyPI

on:
  release:
    types: [published]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: twine upload dist/*
```

Then add your PyPI token as a GitHub secret:
1. Go to repository Settings → Secrets → Actions
2. Click "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: Your PyPI API token
5. Click "Add secret"

Now, whenever you create a GitHub release, it will automatically publish to PyPI!

## Part 3: Ongoing Maintenance

### Making Updates

1. **Make changes to code**
2. **Update version** in `pyproject.toml`
3. **Update CHANGELOG.md**
4. **Commit and push**:
   ```bash
   git add .
   git commit -m "Update: Description of changes"
   git push origin main
   ```
5. **Create new release on GitHub**
6. **Publish to PyPI** (manual or automatic via GitHub Actions)

### Version Numbering

Follow Semantic Versioning (semver.org):
- **Major** (1.0.0): Breaking changes
- **Minor** (0.1.0): New features, backward compatible
- **Patch** (0.1.1): Bug fixes, backward compatible

### Handling Issues

1. Users report issues via GitHub Issues
2. Reproduce and diagnose
3. Fix in a branch
4. Create pull request
5. Merge and release

## Best Practices

### Before Publishing

- [ ] All tests pass
- [ ] Documentation is complete
- [ ] CHANGELOG.md is updated
- [ ] Version number is updated
- [ ] No sensitive data in repository
- [ ] .gitignore is properly configured
- [ ] README examples work
- [ ] License is appropriate

### Security

- Never commit API tokens or passwords
- Use GitHub secrets for sensitive data
- Review dependencies for vulnerabilities
- Keep dependencies updated

### Documentation

- Keep README.md updated
- Add examples for new features
- Update CHANGELOG.md for all releases
- Respond to issues and PRs promptly

## Useful Commands

```bash
# Check package metadata
python -m build
twine check dist/*

# Install locally in development mode
pip install -e .

# Run tests
pytest

# Check code style
black .
ruff check .

# View package on PyPI
# https://pypi.org/project/bridge-deals-ingest/

# View repository stats
# https://github.com/YOUR_USERNAME/bridge-deals-ingest/pulse
```

## Troubleshooting

**Issue**: "Package already exists on PyPI"
- Can't reupload same version. Increment version number.

**Issue**: "Authentication failed"
- Check API token is correct
- Ensure token has upload permissions

**Issue**: "Invalid distribution"
- Run `twine check dist/*` for details
- Ensure all required fields in pyproject.toml

**Issue**: GitHub Actions failing
- Check Actions tab for error logs
- Ensure all secrets are configured
- Verify workflow YAML syntax

## Resources

- [PyPI Publishing Guide](https://packaging.python.org/tutorials/packaging-projects/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Semantic Versioning](https://semver.org/)
- [Twine Documentation](https://twine.readthedocs.io/)

## Support

For publishing issues:
- PyPI help: https://pypi.org/help/
- GitHub help: https://docs.github.com/
- Python packaging: https://packaging.python.org/

Good luck with your publication! 🚀






