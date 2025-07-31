#!/bin/bash
# Build script for APIForge package

echo "🔨 Building APIForge package..."

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf build/ dist/ *.egg-info/

# Build the package
echo "Building package..."
python -m build

# Show build results
echo "✅ Build complete!"
echo "Build artifacts:"
ls -la dist/

echo ""
echo "📦 To install locally, run:"
echo "  pip install dist/apiforge-*.whl"
echo ""
echo "📤 To upload to PyPI, run:"
echo "  python -m twine upload dist/*"