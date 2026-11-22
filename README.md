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

## Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/professor-hunter.git
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

## Project Structure
```text
professor-hunter/
├── app.py              # Main Streamlit user interface
├── agent.py            # Claude AI classification and orchestration logic
├── tools.py            # Web scraping, NSF API, and Semantic Scholar integrations
├── requirements.txt    # Python dependencies
├── .env                # Environment variables (API keys)
└── README.md           # Project documentation
```

---
*Built under the guidance of Professor Xifeng Yan at UCSB.*
