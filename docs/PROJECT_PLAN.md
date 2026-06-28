# System Architecture & Implementation Prompt: CareerEngine

You are an expert Principal AI Software Architect and Senior Systems Engineer. We are building a production-grade, privacy-first, highly efficient AI agentic platform called **CareerEngine** using the **Google Agent Development Kit (ADK) 2.0** framework. 

Your objective is to generate the complete codebase structural blueprint and core implementation scripts based on the detailed technical specifications below. Do not use placeholders or omit logic; write full, production-ready code blocks.

---

## Core Pillars
* Quality Without Compromise: Uses deep conversational probing to extract real metrics instead of fabricating data.
* Extreme Cost Efficiency: Powered by Google ADK 2.0 and Gemini 1.5 Flash for heavy lifting, utilizing Gemini 1.5 Pro strictly for complex reasoning gaps, maximizing the Google Free Tier limits.
* Device-Agnostic Operational Flow: Works seamlessly across lightweight interfaces (CLI/Termux on mobile devices/tablets) and web interfaces (Streamlit) using a unified cloud state layer.
* Zero-Knowledge Architecture: Implements a Bring Your Own Key (BYOK) model to offload LLM inference billing and eliminate data-sharing liabilities across tenants.

---

## Technical Stack Architecture
* Orchestration Framework: Google Agent Development Kit (ADK) 2.0 (Workflow Runtime Engine).
* Core LLM Processing: gemini-1.5-flash (Resume tailoring, parsing, and UI rendering) + gemini-1.5-pro (The "Grill Me" extraction logic).
* State & Persistence Layer: Google Cloud Firestore (NoSQL Document Store) structured for multi-tenancy via cryptographic key hashing.
* User Interfaces: * Web App: Streamlit (deployed via Google Cloud Run).
* Power-User CLI: Local Python execution script working inside terminal environments.
* Document Generation: Jinja2 Template Engine + Headless Chrome (via Api2Pdf or local PDF rendering tools).
* Infrastructure as Code (IaC): Terraform scripts for deployment isolation.

---

## 1. System Vision & Product Requirements
CareerEngine converts raw, multi-decade career histories into highly optimized, quantifiable, STAR-formatted portfolios and tailored resumes.
- **Tone:** A supportive, knowledgeable peer (Principal Engineer talking shop over coffee). Completely avoid robotic, clinical HR terms or explicit mentions of "the STAR framework" in user-facing turns.
- **Pacing Control (The Brake):** For users with extensive histories (e.g., 25+ years), the system must loop through career pillars one at a time. It enforces a strict checkpoint brake every 5 conversational turns to prevent user fatigue and runaway LLM looping. It summarizes progress and asks the user whether to pause or continue.
- **Asynchronous Loop (Option A):** A background routine processes applications sitting in an "applied" status for over 14 days and flags them as a "Pending Action" item directly on the user's Streamlit workspace dashboard.

---

## 2. Technical Stack & Infrastructure
- **Orchestration Framework:** Google Agent Development Kit (ADK) 2.0 (Workflow Runtime Engine).
- **LLM Selection:** `gemini-1.5-flash` for high-throughput processing (Parsing, UI tracking, Tailoring) and `gemini-1.5-pro` exclusively for the deep "Grill Me" metric extraction graph node.
- **State & Multi-Tenancy:** Google Cloud Firestore (Native Mode).
- **Security & Billing Paradigm:** Bring Your Own Key (BYOK). Multi-tenancy is completely isolated without heavy auth boilerplate by taking a SHA-256 cryptographic hash of the user's provided Gemini API key as their `tenant_id`.
- **Presentation Layer:** Streamlit (Frontend/Workspace) + Jinja2 (HTML/CSS Template Engine) + Headless Chrome Rendering (via custom ADK Tool Node) to output structurally sound, ATS-compliant PDFs.

---

## 3. Complete Directory Structure
Generate the files matching this explicit architecture:
```text
career-engine/
├── .env.example
├── main.py                 # Streamlit and CLI entry points
├── config.py               # Firestore and ADK Service initializations
├── schema.py               # Pydantic state representations
├── database/
│   └── firestore_session.py # Custom ADK DatabaseSessionService adapter
├── workflows/
│   ├── discovery_graph.py   # ADK Workflow graph definition
│   └── nodes.py             # Individual BaseNode execution logic
├── tools/
│   ├── pdf_renderer.py      # Jinja2 -> PDF compile tool
│   └── web_scraper.py       # Job Description parser
├── skills/
│   └── cloud_ops/
│       ├── SKILL.md
│       └── reference/
├── templates/
│    └── classic_resume.html   # Clean HTML template for Jinja2 injection
├── infrastructure/           # terraform code for hosting all infrastructure
└── evaluation/
    ├── test_config.json     # ADK Eval parameters
    └── user_simulator.py    # Automated multi-turn conversational testing
```
---
The /infrastructure Folder: This should contain your Terraform modules. You shouldn't just run commands; you should define your environment (e.g., prod/, dev/) so you can tear down or scale your entire career platform with a single command.
include a setup.sh or a well-documented README.md in that folder. You are using GCP Secret Manager. You need to ensure the Terraform scripts automatically grant the Cloud Run service account the roles/secretmanager.secretAccessor role. Without this, your app will fail at runtime when it tries to fetch the user's Gemini key.
Construct a comprehensive /infrastructure folder using Terraform to provision a Google Cloud Run service, a native Firestore instance, and an Artifact Registry. Include a Makefile in the root directory to automate the build-test-deploy lifecycle. The Streamlit interface should be treated as a lightweight frontend-for-agents, focusing on usability and rapid iteration, while maintaining a strict separation of concerns from the ADK 2.0 workflow runtime so we can swap it for a custom frontend later if needed.

Layer,Component,Purpose
Compute,Cloud Run,"Serverless, auto-scaling, perfect for event-driven agents."
Persistence,Firestore,"Stores agent state and resume metadata, isolated by tenant hash."
Secrets,Secret Manager,"Never hardcode API keys. Terraform should provision secrets, and Cloud Run should inject them at runtime."
Networking,Load Balancer,"If you enable IAP, you need a Global Load Balancer to enforce the security perimeter."
Monitoring,Cloud Logging,"Crucial for debugging ""agent loops""—you need to see exactly where the agent is hanging in your graph."

---

## 4. Code Implementation Tasks

Please use pip+venv. Please generate the code for the following core files:

### Task 4.1: `config.py`

Implement the secure tenant isolation logic by hashing the user's API key.

```python
import hashlib
import os
from google.cloud import firestore

def get_tenant_id(user_api_key: str) -> str:
    if not user_api_key:
        raise ValueError("Gemini API Key is required.")
    return hashlib.sha256(user_api_key.encode('utf-8')).hexdigest()

def get_firestore_client():
    # Initializes and returns native Firestore client
    return firestore.Client()

```

### Task 4.2: `schema.py`

Define the structural graph data representations using Pydantic to maintain execution context.

```python
from pydantic import BaseModel
from typing import List, Dict, Optional

class StarStory(BaseModel):
    situation: Optional[str] = None
    task: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    metrics_validated: bool = False

class CareerEngineState(BaseModel):
    current_phase: str = "ingestion"  # ingestion, grilling, checkpoint, complete
    current_pillar: str = ""
    target_competencies: List[str] = []
    extracted_star_stories: Dict[str, StarStory] = {}
    active_gaps: List[str] = []
    question_count: int = 0

```

### Task 4.3: `workflows/discovery_graph.py`

Implement the ADK 2.0 Workflow definitions, conditional edges, and routing logic demonstrating the 5-turn pacing brake mechanism.
Ensure you explicitly instruct the agent that the checkpoint must act as a "Hydration Point." * The logic: When the agent hits the 5-turn brake, it shouldn't just ask "Continue?"—it should summarize the delta (what it learned in the last 5 turns) and ask the user to verify the high-level summary before committing it to the permanent master_resume.md. This forces a "Human-in-the-Loop" verification step that makes the resume 10x more accurate.

```python
from google.adk.workflow import Workflow
from schema import CareerEngineState

def discovery_router(state: CareerEngineState) -> str:
    if state.current_phase == "complete" or not state.active_gaps:
        return "finalize_master_resume"
    
    # 5-Turn Checkpoint Brake to avoid user fatigue
    if state.question_count > 0 and state.question_count % 5 == 0 and state.current_phase != "checkpoint":
        return "user_checkpoint_node"
        
    return "execute_grill_turn_node"

# Define the ADK 2.0 Workflow graph registration flow here...

```

### Task 4.4: `workflows/nodes.py`

Write the execution logic for `execute_grill_turn_node` using `gemini-1.5-pro` and the system prompt instructing it to act as an advanced peer engineer seeking metrics like architectural scale, latency improvements, blast radius, and efficiency deltas without sounding robotic.

### Task 4.5: Document Assembly

Show the utility function that maps the final validated JSON state into the Jinja2 context to populate an HTML layout, protecting against raw LLM markdown format breaking.

---
### Task 4.5: `tools/web_scraper.py`
Use a "Two-Step Scraping" approach:
1. Crawl: Fetch the raw HTML from the Job Description URL.
2. Clean & Abstract: Use Gemini 1.5 Flash to strip all site navigation, sidebars, and "company culture" fluff, reducing the JD to only the functional requirements and skills. This prevents "context pollution," where the agent gets distracted by the company's "mission statement" instead of focusing on the hard skills you need to highlight.
---

## 5. Testing & Verification Requirements

Provide a template script demonstrating how to run the ADK 2.0 `UserSimulator` to simulate an applicant providing vague answers, verifying that the agent pushes back to successfully extract numerical achievements.

Go ahead and generate the complete, production-grade files for this system.

Constraint: When generating the code, prioritize modularity. Ensure that the ADK 2.0 graph logic is strictly decoupled from the UI (Streamlit) and the Persistence (Firestore). Every node must be an atomic function that takes a CareerEngineState object and returns the updated state. Avoid any 'God Object' patterns.
