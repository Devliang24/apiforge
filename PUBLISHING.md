# Publishing APIForge to PyPI

This guide explains how to publish APIForge to PyPI (Python Package Index).

## Prerequisites

1. Install required tools:
```bash
pip install build twine
```

2. Create PyPI account:
   - Register at https://pypi.org/account/register/
   - Generate API token at https://pypi.org/manage/account/token/

3. Configure PyPI credentials:
```bash
# Create ~/.pypirc file
cat > ~/.pypirc << EOF
[pypi]
username = __token__
password = <your-pypi-token>
EOF
```

## Publishing Process

### 1. Update Version

Edit `apiforge/_version.py`:
```python
__version__ = "0.1.1"  # Increment version
```

### 2. Build Package

```bash
# Clean previous builds
rm -rf build/ dist/ *.egg-info/

# Build the package
python -m build
```

### 3. Test Installation Locally

```bash
# Create test environment
python -m venv test_env
source test_env/bin/activate  # On Windows: test_env\Scripts\activate

# Install from wheel
pip install dist/apiforge-*.whl

# Test the package
apiforge --help
python -c "import apiforge; print(apiforge.__version__)"

# Cleanup
deactivate
rm -rf test_env
```

### 4. Upload to Test PyPI (Optional)

```bash
# Upload to test.pypi.org
python -m twine upload --repository testpypi dist/*

# Test installation from Test PyPI
pip install --index-url https://test.pypi.org/simple/ apiforge
```

### 5. Upload to PyPI

```bash
# Upload to PyPI
python -m twine upload dist/*
```

### 6. Verify Installation

```bash
# Install from PyPI
pip install apiforge

# Test the installation
apiforge --help
```

## Post-Publishing

1. Create a GitHub release:
   - Tag the commit: `git tag v0.1.0`
   - Push tags: `git push origin --tags`
   - Create release on GitHub

2. Update README if needed

3. Announce the release

## Common Issues

- **Module not found**: Ensure all packages are included in `pyproject.toml`
- **Missing files**: Check `MANIFEST.in` includes all necessary files
- **Import errors**: Test locally before publishing
- **Version conflicts**: Always increment version number

## Version Numbering

Follow semantic versioning (MAJOR.MINOR.PATCH):
- MAJOR: Breaking changes
- MINOR: New features, backwards compatible
- PATCH: Bug fixes

## Automation

Consider using GitHub Actions for automated publishing:
```yaml
name: Publish to PyPI
on:
  release:
    types: [published]
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.x'
    - name: Install dependencies
      run: |
        pip install build twine
    - name: Build package
      run: python -m build
    - name: Publish to PyPI
      env:
        TWINE_USERNAME: __token__
        TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
      run: python -m twine upload dist/*
```