#!/bin/bash
# ============================================================
# Pro-Tinder EC2 Deployment Script
# Run on a fresh Ubuntu EC2 instance
# Usage: chmod +x deploy.sh && ./deploy.sh
# ============================================================

set -e

echo "=== Pro-Tinder EC2 Deployment ==="

# 1. Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker $USER
    echo "Docker installed. You may need to log out and back in for group changes."
fi

# 2. Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env from template..."
    cp .env.example .env
    echo "================================================================"
    echo "IMPORTANT: Edit .env with your actual API keys before starting!"
    echo "  nano .env"
    echo "Required keys: OPENAI_API_KEY, RAPIDAPI_KEY"
    echo "================================================================"
    exit 0
fi

# 3. Build and start all services
echo "Building and starting all services..."
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "=== Deployment Complete ==="
echo "Frontend:  http://$(curl -s ifconfig.me)"
echo "Health:    http://$(curl -s ifconfig.me)/api/health"
echo ""
echo "Useful commands:"
echo "  docker compose -f docker-compose.prod.yml logs -f        # View logs"
echo "  docker compose -f docker-compose.prod.yml restart backend # Restart backend"
echo "  docker compose -f docker-compose.prod.yml down            # Stop all"
