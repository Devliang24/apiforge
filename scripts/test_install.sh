#!/bin/bash
# Test installation script for APIForge

echo "🧪 Testing APIForge installation..."

# Create a temporary virtual environment
echo "Creating temporary virtual environment..."
python -m venv test_env
source test_env/bin/activate

# Install the package
echo "Installing APIForge..."
pip install -e .

# Test the command
echo "Testing apiforge command..."
apiforge --help

# Test import
echo "Testing Python import..."
python -c "import apiforge; print(f'APIForge version: {apiforge.__version__}')"

# Cleanup
deactivate
rm -rf test_env

echo "✅ Installation test complete!"