# 🎓 Professor Hunter
> AI-powered tool to find funded STEM professors for graduate school applications

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)
![Claude AI](https://img.shields.io/badge/Claude%20AI-000000?style=for-the-badge&logo=anthropic&logoColor=white)
![NSF API](https://img.shields.io/badge/NSF%20API-0033A0?style=for-the-badge&logo=data&logoColor=white)

## What it does
Professor Hunter is an intelligent agent designed to help prospective STEM graduate students find the right academic advisors. Instead of manually scouring university websites, this tool takes your specific research interests (e.g., "AI hardware", "chip design", "robotics") and autonomously discovers active faculty members. It cross-references them against real-world funding databases and publication records, ultimately presenting you with a highly curated, personalized list of potential advisors.

## How it works
The architecture relies on a multi-layered discovery and verification pipeline:
- **DuckDuckGo** discovers professors across any STEM field dynamically based on your search query.
- **NSF Awards API** verifies active funding and grant amounts, ensuring the professors have the resources to support graduate students.
- **Semantic Scholar** fetches recent publications and citation counts to validate active research output.
- **Claude AI** processes search results to extract clean data, verifies institutional `.edu` email addresses, and classifies professors into Reach, Target, or Safety tiers based on university competitiveness.
- **Results are displayed** with verified emails, recent papers, active grants, and personalized outreach advice tailored to your query.

## Tech Stack
- **Frontend & UI:** [Streamlit](https://streamlit.io/)
- **Core Logic:** Python
- **AI / LLM:** Anthropic Claude (Haiku for extraction, Sonnet for classification)
- **Search & Discovery:** DuckDuckGo Search (DDGS)
- **Academic Databases:** NSF Awards API, Semantic Scholar API

## Features
- 🔍 **Searches any STEM field dynamically**
- 💰 **Verifies real NSF grant funding**
- 📚 **Gets real recent papers with citation counts**
- 📧 **Finds verified .edu email addresses** (automatically filtering out personal/junk emails)
- 📊 **Classifies schools as Reach/Target/Safety**
- ⏳ **Live progress updates during search**

## Performance
In three timed runs, Professor Hunter surfaced 15-20 funded STEM professors in 6-7 minutes each. Finding and vetting one by hand takes me about an hour (my estimate), so the tool takes under 30 seconds per professor. Discovery and first-pass screening are automated; you still read the papers yourself.

Measured over 3 runs on the live app.

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Bjay4910/professor-hunter.git
   cd professor-hunter
   ```

2. **Set up a virtual environment (recommended):**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   Create a `.env` file in the root directory and add your Anthropic API key:
   ```env
   ANTHROPIC_API_KEY=your_api_key_here
   ```

## Usage

Run the Streamlit application:
```bash
streamlit run app.py
```

**Example Searches:**
- "Find AI hardware professors at Georgia Tech"
- "Find funded robotics professors at MIT"
- "Find ML professors at safety schools"
- "Find chip design professors at Target schools"

## Usage limits

Every search makes paid Claude API calls on the host's key, so four controls keep spending bounded.

**1. Per-search budget.** Every Claude call goes through one place (`llm_budget.py`), including:
- Haiku extraction, verification and email lookup in `tools.py`
- the final Sonnet classification in `agent.py`
- every retry: the SDK's automatic retries are turned off, and retries are made and counted by the app.

A search stops making Claude calls once it hits either the call limit or the output-token limit. The Haiku steps always leave room for one full Sonnet call, so the final step isn't starved. Actual token usage is logged at the end of each search. This budget applies to every search, including ones run with your own key.

**2. Per-visitor limit.** Each browser session gets 5 free searches. Reloading the page starts a new session.

**3. Global daily cap.** All visitors together get 100 free searches per UTC day. The count is kept in the app's memory, so it resets when the app restarts and isn't shared between multiple app processes.

**4. Bring your own key (optional).** Open the sidebar and paste your own Anthropic API key. Searches with your key are billed to you and skip limits 2 and 3. The key is only passed to the API client for your searches. It is never written to disk or logged, and it is never shown on the page; it is also removed from any error message before display.

### Environment variables

| Variable | Default | What it controls |
|---|---|---|
| `ANTHROPIC_API_KEY` | — (required) | The host's shared key for free searches |
| `SESSION_SEARCH_LIMIT` | `5` | Free searches per browser session |
| `DAILY_SEARCH_LIMIT` | `100` | Free searches per UTC day, across all visitors |
| `LLM_MAX_CALLS_PER_RUN` | `80` | Max Claude request attempts per search, retries included |
| `LLM_MAX_OUTPUT_TOKENS_PER_RUN` | `40000` | Max total `max_tokens` set aside per search |
| `LLM_MAX_RETRIES` | `1` | Retries per call on rate-limit, 5xx or connection errors |

Run the mocked tests (no network or paid calls) with:
```bash
python -m unittest test_limits -v
```

## Project Structure
```text
professor-hunter/
├── app.py              # Main Streamlit user interface
├── agent.py            # Claude AI classification and orchestration logic
├── tools.py            # Web scraping, NSF API, and Semantic Scholar integrations
├── llm_budget.py       # Per-search budget; the only place Claude is called
├── usage_limits.py     # Per-visitor limit, daily cap, own-key checks
├── test_limits.py      # Mocked tests for the budget and limits
├── requirements.txt    # Python dependencies
├── .env                # Environment variables (API keys)
└── README.md           # Project documentation
```

---
*Built under the guidance of Professor Xifeng Yan at UCSB.*
