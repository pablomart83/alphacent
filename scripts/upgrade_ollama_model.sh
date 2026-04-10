#!/bin/bash
# Script to upgrade Ollama model for better strategy generation

set -e

echo "=========================================="
echo "Ollama Model Upgrade Script"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if ollama is installed
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}Error: Ollama is not installed${NC}"
    echo "Please install Ollama from: https://ollama.ai"
    exit 1
fi

# Check current models
echo "Current installed models:"
ollama list
echo ""

# Show recommendations
echo "=========================================="
echo "Recommended Models for Strategy Generation"
echo "=========================================="
echo ""
echo -e "${GREEN}🥇 Best Choice: Qwen 2.5 Coder 7B${NC}"
echo "   - Size: ~4.7 GB"
echo "   - Best for JSON/structured output"
echo "   - Command: ollama pull qwen2.5-coder:7b"
echo ""
echo -e "${GREEN}🥈 Good Balance: Llama 3.2 3B${NC}"
echo "   - Size: ~2 GB"
echo "   - 3x better than 1B"
echo "   - Command: ollama pull llama3.2:3b"
echo ""
echo -e "${GREEN}🥉 Best Quality: Llama 3.1 8B${NC}"
echo "   - Size: ~4.7 GB"
echo "   - Excellent quality"
echo "   - Command: ollama pull llama3.1:8b"
echo ""

# Ask user which model to install
echo "Which model would you like to install?"
echo "1) qwen2.5-coder:7b (Recommended - Best for JSON)"
echo "2) llama3.2:3b (Quick upgrade - Good balance)"
echo "3) llama3.1:8b (Best quality)"
echo "4) mistral:7b (Alternative)"
echo "5) Skip installation"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1)
        MODEL="qwen2.5-coder:7b"
        ;;
    2)
        MODEL="llama3.2:3b"
        ;;
    3)
        MODEL="llama3.1:8b"
        ;;
    4)
        MODEL="mistral:7b"
        ;;
    5)
        echo "Skipping installation"
        exit 0
        ;;
    *)
        echo -e "${RED}Invalid choice${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${YELLOW}Pulling model: $MODEL${NC}"
echo "This may take a few minutes depending on your internet connection..."
echo ""

# Pull the model
if ollama pull "$MODEL"; then
    echo ""
    echo -e "${GREEN}✓ Successfully pulled $MODEL${NC}"
    echo ""
    
    # Update environment variable
    echo "To use this model, set the environment variable:"
    echo ""
    echo -e "${YELLOW}export OLLAMA_MODEL=\"$MODEL\"${NC}"
    echo ""
    echo "Or add to your ~/.bashrc or ~/.zshrc:"
    echo -e "${YELLOW}echo 'export OLLAMA_MODEL=\"$MODEL\"' >> ~/.bashrc${NC}"
    echo ""
    
    # Ask if user wants to test
    read -p "Would you like to test the model now? [y/N]: " test_choice
    if [[ $test_choice =~ ^[Yy]$ ]]; then
        echo ""
        echo "Testing model with bootstrap command..."
        echo ""
        OLLAMA_MODEL="$MODEL" python -m src.cli.bootstrap_strategies --strategy-types momentum
    fi
    
    echo ""
    echo -e "${GREEN}✓ Model upgrade complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Set OLLAMA_MODEL environment variable (see above)"
    echo "2. Run: python -m src.cli.bootstrap_strategies --auto-activate --min-sharpe 0.5"
    echo ""
else
    echo ""
    echo -e "${RED}✗ Failed to pull model${NC}"
    exit 1
fi
