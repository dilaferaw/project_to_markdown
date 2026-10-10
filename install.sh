#!/usr/bin/env bash
# ProjectToMarkdown – quick setup script (Linux / Debian-based)
set -e

echo "=== ProjectToMarkdown Installer ==="
echo ""

# 1. Detect package manager
if command -v apt &> /dev/null; then
    PKG_MGR="apt"
elif command -v dnf &> /dev/null; then
    PKG_MGR="dnf"
elif command -v pacman &> /dev/null; then
    PKG_MGR="pacman"
else
    echo "Could not detect package manager. Please install requirements manually."
    PKG_MGR=""
fi

# 2. Install system dependencies
echo "[1/3] Checking system dependencies..."
if [ "$PKG_MGR" = "apt" ]; then
    sudo apt update
    sudo apt install -y python3 tree
elif [ "$PKG_MGR" = "dnf" ]; then
    sudo dnf install -y python3 tree
elif [ "$PKG_MGR" = "pacman" ]; then
    sudo pacman -S --noconfirm python tree
fi
echo "   Done."

# 3. Install Python dependencies
echo "[2/3] Installing Python dependencies..."
if command -v pip3 &> /dev/null; then
    pip3 install --user tiktoken
elif command -v pip &> /dev/null; then
    pip install --user tiktoken
else
    echo "   pip not found – skipping tiktoken (token counting will use fallback)."
fi
echo "   Done."

# 4. Done
echo "[3/3] Setup complete!"
echo ""
echo "Run the app:"
echo "  cd $(dirname "$0")"
echo "  python3 main.py"
echo ""
echo "The app opens in your browser (use --no-browser to just print the URL)."

echo "" 
echo "Optional: run in Docker" 
echo "  git clone https://github.com/dilaferaw/project_to_markdown.git" 
echo "  cd project_to_markdown/docker" 
echo "  docker compose up --build -d   # open http://localhost:8765" 
