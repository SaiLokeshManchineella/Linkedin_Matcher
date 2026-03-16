# Pro-Tinder (GraphRAG Full Stack)

A professional DNA matchmaker that scrapes LinkedIn profiles, generates personalized behavioral questions via GPT-4o-mini, and finds similar professionals using a 3-source hybrid engine: Vector similarity (Qdrant) + Graph topic matching (Neo4j) + LinkedIn keyword search.

## Stack
- **Backend**: FastAPI (Python)
- **Vector DB**: Qdrant (cosine similarity, 768-dim embeddings)
- **Graph DB**: Neo4j 5.26 (APOC enabled)
- **AI**: OpenAI GPT-4o-mini (chat) + text-embedding-3-small (embeddings) via LangChain
- **LinkedIn Data**: RapidAPI `fresh-linkedin-profile-data`
- **Frontend**: React 18 + Vite + TailwindCSS + Framer Motion

## 1) Environment Setup

Create your runtime env file from the template:

```bash
cp .env.example .env
```

If you are on PowerShell:

```powershell
Copy-Item .env.example .env
```

Then update values in `.env` — **required keys**: `OPENAI_API_KEY` and `RAPIDAPI_KEY`.

Optional (frontend override): create `frontend/.env` with `VITE_API_BASE_URL=http://localhost:8001` if you want to override the default API URL.

## 2) Start Infrastructure

```bash
docker-compose up -d
```

Check containers:

```bash
docker-compose ps
```

Neo4j Browser: `http://localhost:7474`

## 3) Run Backend (FastAPI)

```bash
cd backend
python -m venv .venv
```

Activate the venv:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the server (from the `backend` directory):

```powershell
cd app
..\\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

Health check:

```bash
curl http://localhost:8001/health
```

## 4) Run Frontend (Vite)

```bash
cd frontend
npm install
npm run dev
```

Frontend opens at `http://localhost:5173`.

## 5) Stop Infrastructure

```bash
docker-compose down
```

To also remove volumes:

```bash
docker-compose down -v
```

## How It Works

### User Flow

1. **Paste a LinkedIn URL** → backend scrapes the profile (name, headline, skills, experience, education) and recent posts via RapidAPI
2. **AI generates 5 personalized behavioral questions** based on your specific role, skills, company, and recent posts — not generic templates
3. **Answer the questions** → backend extracts 5-8 professional interest topics and creates a 768-dimensional embedding vector from your profile + answers
4. **3-source matching engine finds similar professionals** (see below)
5. **AI generates a personalized reason** explaining WHY each matched person is relevant to you

### Matching Engine (3 Sources)

The system combines three different matching strategies to find up to 10 similar professionals:

#### Source 1: Qdrant (Vector Similarity)
- Your profile text + answers are embedded into a **768-dimensional vector** using OpenAI `text-embedding-3-small`
- This vector is stored in **Qdrant** (a vector database) alongside your profile metadata
- Qdrant performs **cosine similarity search** against all stored user vectors
- Only users with similarity **≥ 0.75** (configurable) are returned
- This finds people with semantically similar professional backgrounds, even if they use different words to describe similar skills

#### Source 2: Neo4j (Graph Topic Matching — GraphRAG)
- When you submit answers, the AI extracts topics like "Machine Learning", "Cloud Architecture", "React"
- These are stored as nodes in a **Neo4j graph**: `(User) -[:INTERESTED_IN]-> (Topic)`
- Users with identical topic sets share a **Category** node (deterministic hashing)
- The graph query **traverses shared Topic nodes** to find users who share the most interests:
  ```
  (You) --INTERESTED_IN--> (Topic: AI) <--INTERESTED_IN-- (Other User)
  ```
- Users are ranked by **number of shared topics** — someone sharing 5/6 of your topics ranks higher than someone sharing 2/6
- This catches matches that vector similarity might miss (e.g., same interests described in very different language)

#### Source 3: LinkedIn API (Keyword Search Backfill)
- If Sources 1 + 2 find fewer than 10 matches, the system searches **LinkedIn posts** using your extracted topics as keywords
- People who write posts about "Machine Learning, Cloud Architecture" are likely relevant professionals
- These are real LinkedIn users who haven't used the app — shown with a **LinkedIn** badge
- This ensures you always get meaningful matches, even when the app has few registered users

#### How They Combine
```
Qdrant (vector)  →  Neo4j (graph)  →  LinkedIn (API)
  High confidence      Medium confidence    Discovery
  Same embedding       Same topics          Same keywords
  App users only       App users only       All LinkedIn users
```

Results are **deduplicated** — if someone appears in both Qdrant and Neo4j results, the Qdrant match takes priority. Each match shows its source badge in the UI.

## Notes
- RapidAPI `fresh-linkedin-profile-data` response shape can vary. Adjust `backend/app/services/scraping.py` if the payload differs.
- The default Qdrant similarity threshold is `0.75` and can be tuned via `QDRANT_SIMILARITY_THRESHOLD` in `.env`.
- Returning users are recognized automatically — they skip questions and get **fresh matches** (not stale cached data).

## 6) Deploy to AWS EC2 (Production)

Prerequisites: an EC2 instance (Ubuntu 22.04+, t3.medium or larger recommended) with ports 80, 8001, and 22 open in the security group.

**SSH into your EC2 instance and run:**

```bash
# Clone the repo
git clone https://github.com/SaiLokeshManchineella/Linkedin_Matcher.git
cd Linkedin_Matcher

# Run the deploy script — it will ask for your EC2 public IP and API keys
chmod +x deploy.sh
./deploy.sh
```

The script will:
1. Ask for your **EC2 public IP**, **OPENAI_API_KEY**, and **RAPIDAPI_KEY**
2. Auto-generate `.env` with all values configured for production
3. Install Docker
4. Build and start the entire stack (Frontend, Backend, Qdrant, Neo4j) securely using `docker-compose.prod.yml`

The app frontend will be automatically accessible at `http://YOUR_EC2_PUBLIC_IP`.
The backend API and Swagger docs will be accessible at `http://YOUR_EC2_PUBLIC_IP:8001/docs`.

**EC2 Security Group rules needed:**
| Type | Port | Source |
|------|------|--------|
| HTTP | 80 | 0.0.0.0/0 |
| Custom TCP | 8001 | 0.0.0.0/0 |
| SSH | 22 | Your IP |

**Useful commands:**
```bash
# View logs for all services
sudo docker compose -f docker-compose.prod.yml logs -f

# View logs for a specific service (e.g., backend)
sudo docker compose -f docker-compose.prod.yml logs -f backend

# Restart the frontend
sudo docker compose -f docker-compose.prod.yml restart frontend

# Take down the entire stack
sudo docker compose -f docker-compose.prod.yml down
```
