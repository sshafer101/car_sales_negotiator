# Car Sales Negotiator

Deterministic car sales discovery + negotiation simulator.

Primary purpose: showcase `persona_engine` determinism.
Same seed -> same buyer persona -> consistent buyer behavior.
This makes replay, coaching, and A/B testing possible.

## What this MVP proves

- Seed replay: run the same seed twice and get the same buyer constraints and negotiation style
- Seed sharing: share a seed with another rep and you both get the same buyer
- Seed assignment: managers can assign a seed pack to reps for fair training
- Run storage: each run is saved as JSON for replay, scoring, and reporting

## Quick start

### 1) Create env + install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
pip install streamlit openai
```

### 2) Configure OpenAI key

Option A: environment variable

```bash
export OPENAI_API_KEY="YOUR_KEY"
```

Option B: Streamlit secrets (recommended)

Create `.streamlit/secrets.toml`:

```toml
OPENAI_API_KEY = "YOUR_KEY"
```

Do not commit this file.

### 3) Run the app

```bash
streamlit run app/Home.py
```

Streamlit prints a local URL (example: http://localhost:8501).

## Demo script

### Determinism demo (seed replay)

1) Go to Run Sim
2) Set:
   - Seed: 18422
   - Mode: flavor (LLM)
   - Model: gpt-5.2
3) Send 3 to 6 seller messages
4) Note the buyer behavior and the displayed `buyer_profile_hash`
5) Start a new run with the same seed and repeat
6) The buyer profile hash and buyer behavior should match

### Variety demo

Run a few different seeds and compare styles and constraints:

- 18422
- 1024
- 9001

### Export scoring summary

- Use the Export area to download the run JSON
- Use Replay to view prior runs and compare scores

## Modes

- strict: rule-based buyer replies, no LLM
- freeplay: LLM buyer replies, no reference style
- flavor: LLM buyer replies plus reference style excerpts from prior runs

## Data pack

The buyer constraints and behavior are generated from JSON packs in:

`data/car_sales_pack/`

This keeps the simulator deterministic and easy to extend.

## Repo hygiene

Recommended `.gitignore` entries:

```gitignore
.venv/
__pycache__/
*.pyc

.streamlit/secrets.toml

runs/
exports/

.DS_Store
```

## Troubleshooting

### Streamlit pages not found

`st.page_link()` paths must be relative to the entrypoint directory (`app`).
Use:

- `pages/0_Login.py`
- `pages/1_Run_Sim.py`
- `pages/2_Replay.py`

Not `app/pages/...`

### 429 insufficient_quota

Your API key has no available credits or billing is not enabled for that project.

### 400 unsupported parameter temperature

Some models reject `temperature`. This project avoids passing it for GPT-5 family models.
