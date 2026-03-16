#!/bin/bash
# ============================================================
# Pro-Tinder — Full EC2 Deployment Script (Ubuntu 22.04+)
#
# What this does:
#   1. Asks for EC2 public IP + API keys
#   2. Auto-generates .env with all values
#   3. Installs Docker
#   4. Rebuilds and spins up the ENTIRE stack via docker-compose.prod.yml
#
# Prerequisites:
#   - Ubuntu 22.04+ EC2 instance
#   - Security Group: allow HTTP (80), Custom TCP (8001), SSH (22)
#
# Usage:
#   git clone https://github.com/SaiLokeshManchineella/Linkedin_Matcher.git
#   cd Linkedin_Matcher
#   chmod +x deploy.sh
#   ./deploy.sh
# ============================================================

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[✔]${NC} $1"; }
info() { echo -e "${CYAN}[→]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✘]${NC} $1"; }

echo ""
echo "============================================"
echo "   Pro-Tinder — EC2 Deployment Script"
echo "============================================"
echo ""

# ---- Step 1: Collect user inputs ----

read -p "$(echo -e ${CYAN}Enter the Public IP of this EC2 instance: ${NC})" PUBLIC_IP
if [ -z "$PUBLIC_IP" ]; then
    err "Public IP cannot be empty. Exiting."
    exit 1
fi

read -p "$(echo -e ${CYAN}Enter your OPENAI_API_KEY: ${NC})" OPENAI_KEY
if [ -z "$OPENAI_KEY" ]; then
    err "OPENAI_API_KEY cannot be empty. Exiting."
    exit 1
fi

read -p "$(echo -e ${CYAN}Enter your RAPIDAPI_KEY: ${NC})" RAPID_KEY
if [ -z "$RAPID_KEY" ]; then
    err "RAPIDAPI_KEY cannot be empty. Exiting."
    exit 1
fi

echo ""
log "Inputs collected. Starting deployment..."
echo ""

# ---- Step 2: Generate .env files ----

info "Generating .env files..."

cat > .env << ENVEOF
# Infrastructure
QDRANT_HTTP_PORT=6333
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
NEO4J_AUTH=neo4j/password123

# Backend / AI
OPENAI_API_KEY=${OPENAI_KEY}
RAPIDAPI_KEY=${RAPID_KEY}
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSIONS=768
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=pro_tinder_clusters
QDRANT_SIMILARITY_THRESHOLD=0.75
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# Application
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8001
# The frontend build stage requires Vite API URL to be empty so it dynamically routes through Nginx
VITE_API_BASE_URL=
ENVEOF

log ".env files created with Public IP: ${PUBLIC_IP}"

# ---- Step 3: System update ----

info "Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

info "Installing git, curl..."
sudo apt-get install -y git curl

# ---- Step 4: Install Docker ----

if ! command -v docker &> /dev/null; then
    info "Installing Docker..."
    sudo apt-get install -y ca-certificates gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    sudo usermod -aG docker $USER
    log "Docker installed."
else
    log "Docker already installed."
fi

# ---- Step 5: Stop any existing containers ----

info "Stopping existing Docker containers (if any)..."
sudo docker compose -f docker-compose.prod.yml down 2>/dev/null || true

# ---- Step 6: Start the Full Stack (via docker-compose.prod.yml) ----

info "Building and starting all containers..."
sudo docker compose -f docker-compose.prod.yml up -d --build

info "Waiting 15 seconds for containers to initialize..."
sleep 15

# Verify containers are running
if sudo docker ps | grep -q "pro-tinder-backend"; then
    log "Backend is running."
else
    err "Backend failed to start! Check: sudo docker logs pro-tinder-backend"
fi

if sudo docker ps | grep -q "pro-tinder-frontend"; then
    log "Frontend is running."
else
    err "Frontend failed to start! Check: sudo docker logs pro-tinder-frontend"
fi

# ---- Done! ----

echo ""
echo "============================================"
echo -e "${GREEN}   ✔ DEPLOYMENT COMPLETE!${NC}"
echo "============================================"
echo ""
echo -e "  ${CYAN}Frontend:${NC}  http://${PUBLIC_IP}"
echo -e "  ${CYAN}Backend:${NC}   http://${PUBLIC_IP}:8001"
echo -e "  ${CYAN}Health:${NC}    http://${PUBLIC_IP}:8001/health"
echo -e "  ${CYAN}Neo4j UI:${NC}  http://${PUBLIC_IP}:7474"
echo ""
echo "  Logs:"
echo "    All Services: sudo docker compose -f docker-compose.prod.yml logs -f"
echo ""
echo "  Manage:"
echo "    sudo docker compose -f docker-compose.prod.yml restart frontend  # Restart frontend"
echo "    sudo docker compose -f docker-compose.prod.yml down              # Stop the entire stack"
echo ""
echo -e "  ${YELLOW}Security Group: Make sure ports 80, 8001, 22 are open!${NC}"
echo ""
