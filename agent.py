import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

from tools import discover_professors

# Load environment variables from .env
load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def validate_query(query: str) -> tuple[bool, str]:
    if not query or len(query.strip()) < 10:
        return False, "Please enter a more detailed search query."
    if len(query) > 500:
        return False, "Your query is too long. Please keep it under 500 characters."
    stem_keywords = [
        "professor", "research", "ai", "hardware", "chip", "vlsi",
        "machine learning", "robotics", "computer", "engineering",
        "physics", "chemistry", "biology", "neuroscience",
        "data science", "electrical", "mechanical", "phd",
        "masters", "graduate", "university", "institute", "faculty"
    ]
    query_lower = query.lower()
    if not any(keyword in query_lower for keyword in stem_keywords):
        return False, "Please enter a STEM-related search. Example: 'find AI hardware professors at Purdue University'"
    return True, ""


def run_professor_agent(query: str, status_callback=None) -> str:
    system_prompt = (
        "You are a Professor Hunting Agent helping STEM graduate school applicants find potential advisors.\n\n"
        "You will be given a list of professors discovered via web search with their NSF funding data. "
        "Your ONLY tasks are:\n"
        "1. Classify EACH professor into Reach, Target, or Safety tier based on university admission competitiveness:\n"
        "   - Reach = highly competitive (MIT, Stanford, CMU, Georgia Tech, Purdue, UIUC, Michigan, Caltech, Cornell, Princeton)\n"
        "   - Target = moderately competitive (NC State, UT Austin, Texas A&M, University of Florida, ASU, Ohio State, Rutgers, UC Davis)\n"
        "   - Safety = less competitive but funded (University of New Mexico, Iowa State, Binghamton, University of Kentucky, "
        "University of Nevada, Mississippi State, University of Idaho, South Dakota State, University of Wyoming)\n"
        "2. If a university is not listed above, use your knowledge to classify it appropriately.\n"
        "3. Group results by tier: all Reach first, then Target, then Safety.\n"
        "4. Use the provided research_description and abstract to write Research Focus and Why Reach Out.\n"
        "5. Do NOT search for anything — all data is already provided.\n\n"
        "You MUST complete every professor entry fully before moving to the next. "
        "Never cut off a professor mid-entry. "
        "If you are running low on space, stop adding new professors but always complete the current one fully.\n\n"
        "Return ONLY clean formatted markdown — no JSON, no code blocks, no extra commentary.\n\n"
        "Format each professor exactly like this:\n\n"
        "---\n"
        "## [Professor Name]\n"
        "**Institution:** [University Name]\n"
        "**Tier:** 🔴 Reach / 🟡 Target / 🟢 Safety\n"
        "**Email:** [email or N/A]\n"
        "**Research Focus:** [2-3 sentence description based on their research]\n"
        "**Recent Papers:** [List 2-4 papers if known, otherwise write 'See faculty page']\n"
        "**NSF Grant:** [grant amount and brief description, or 'Not verified via NSF']\n"
        "**Why Reach Out:** [personalized 2-3 sentence reason tailored to the student's query]\n"
        "---"
    )

    # Step 1: Discover professors via Python (DuckDuckGo + NSF verification)
    professors = discover_professors(query, limit=50, status_callback=status_callback)

    if not professors:
        return "No professors found for your query. Please try a different search term."

    # Step 2: Build context prompt with all professor data
    context = f"Student Query: {query}\n\n"
    context += f"Here are {len(professors)} professors discovered for this field:\n\n"
    context += json.dumps(professors, indent=2)
    context += "\n\nPlease classify all of them and format the final markdown output as instructed."

    if status_callback:
        status_callback("🤖 Claude is analyzing and ranking professors...")
    print(f"📨 Sending {len(professors)} professors to Claude for classification...", flush=True)

    # Step 3: Single Claude call — no tool loop needed
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=system_prompt,
        messages=[{"role": "user", "content": context}]
    )

    final_text = ""
    for block in response.content:
        if block.type == "text":
            final_text += block.text

    if status_callback:
        status_callback("✅ Search complete!")
    print("✅ Claude classification complete.", flush=True)
    return final_text.strip() if final_text.strip() else "Search complete. Please try your query again."


if __name__ == "__main__":
    print("🎓 Welcome to Professor Hunter!")
    print("Find funded STEM professors for your graduate school applications.")
    print("=" * 60)
    query = input("What are you looking for? (e.g. 'find AI hardware professors at Georgia Tech'): ")

    is_valid, error_msg = validate_query(query)
    if is_valid:
        print(run_professor_agent(query))
    else:
        print(error_msg)
