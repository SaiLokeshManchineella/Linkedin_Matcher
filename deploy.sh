#!/bin/bash
# ============================================================
# Pro-Tinder — Full EC2 Deployment Script (Ubuntu 22.04+)
#
# What this does:
#   1. Asks for EC2 public IP + API keys
#   2. Auto-generates .env with all values
#   3. Installs Docker, Node.js 20, Python3, PM2
#   4. Spins up Qdrant + Neo4j via Docker
#   5. Builds frontend + runs it via PM2 on port 3000
#   6. Installs Python deps + runs backend via nohup on port 8001
#   7. Redirects port 80 → 3000 so frontend is on http://IP
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
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=pro_tinder_clusters
QDRANT_SIMILARITY_THRESHOLD=0.75
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123

# Application
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8001
VITE_API_BASE_URL=http://${PUBLIC_IP}:8001
ENVEOF

cat > frontend/.env << FENVEOF
VITE_API_BASE_URL=http://${PUBLIC_IP}:8001
FENVEOF

log ".env files created with Public IP: ${PUBLIC_IP}"

# ---- Step 3: System update + core dependencies ----

info "Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

info "Installing Python3, pip, venv, git, curl..."
sudo apt-get install -y python3 python3-venv python3-pip git curl

# ---- Step 4: Install Node.js 20 (via NodeSource) ----

if ! command -v node &> /dev/null || [[ $(node -v | cut -d. -f1 | tr -d 'v') -lt 18 ]]; then
    info "Installing Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
else
    log "Node.js $(node -v) already installed."
fi

# ---- Step 5: Install PM2 globally ----

if ! command -v pm2 &> /dev/null; then
    info "Installing PM2..."
    sudo npm install -g pm2
else
    log "PM2 already installed."
fi

# ---- Step 6: Install Docker ----

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

# ---- Step 7: Start Qdrant + Neo4j containers ----

info "Starting Qdrant + Neo4j containers..."
sudo docker compose up -d

info "Waiting 15 seconds for containers to initialize..."
sleep 15

# Verify containers are running
if sudo docker ps | grep -q "pro-tinder-qdrant"; then
    log "Qdrant is running."
else
    err "Qdrant failed to start! Check: sudo docker logs pro-tinder-qdrant"
fi

if sudo docker ps | grep -q "pro-tinder-neo4j"; then
    log "Neo4j is running."
else
    err "Neo4j failed to start! Check: sudo docker logs pro-tinder-neo4j"
fi

# ---- Step 8: Backend setup ----

info "Setting up backend..."

cd backend

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
info "Installing Python requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# Kill any existing backend process
pkill -f "uvicorn main:app" 2>/dev/null || true

# Start backend with nohup
info "Starting backend with nohup on port 8001..."
cd app
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8001 > ../../backend.log 2>&1 &
BACKEND_PID=$!
cd ..

deactivate
cd ..

# Verify backend is running
sleep 5
if curl -s http://localhost:8001/health | grep -q "ok"; then
    log "Backend is running (PID: ${BACKEND_PID})."
else
    warn "Backend may still be starting. Check logs: tail -f backend/backend.log"
fi

# ---- Step 9: Frontend setup ----

info "Setting up frontend..."

cd frontend

# Install npm dependencies
info "Installing npm modules..."
npm install

# Build for production (VITE_API_BASE_URL is baked in at build time)
info "Building frontend for production..."
npm run build

# Stop any existing PM2 frontend process
pm2 delete pro-tinder-frontend 2>/dev/null || true

# Serve the built frontend via PM2
info "Starting frontend via PM2 on port 3000..."
pm2 serve dist/ 3000 --spa --name pro-tinder-frontend

# Save PM2 process list (survives reboot with pm2 startup)
pm2 save

cd ..

# ---- Step 10: Port 80 → 3000 redirect ----

info "Setting up port 80 → 3000 redirect..."
sudo iptables -t nat -D PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 3000 2>/dev/null || true
sudo iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 3000

log "Port 80 traffic redirected to frontend on port 3000."

# ---- Step 11: Setup PM2 to restart on reboot ----

info "Configuring PM2 startup on reboot..."
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u $USER --hp $HOME 2>/dev/null || true
pm2 save

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
echo "    Backend:   tail -f backend/backend.log"
echo "    Frontend:  pm2 logs pro-tinder-frontend"
echo "    Docker:    sudo docker compose logs -f"
echo ""
echo "  Manage:"
echo "    pm2 status                            # Check frontend"
echo "    pm2 restart pro-tinder-frontend       # Restart frontend"
echo "    pkill -f 'uvicorn main:app'           # Stop backend"
echo "    sudo docker compose down              # Stop Qdrant + Neo4j"
echo ""
echo -e "  ${YELLOW}Security Group: Make sure ports 80, 8001, 22 are open!${NC}"
echo ""
