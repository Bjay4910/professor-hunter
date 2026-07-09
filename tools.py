import os
import re
import json
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
from ddgs import DDGS
from anthropic import Anthropic

# Load environment variables from .env
load_dotenv()

def search_nsf_grants(keyword: str, institution: str = "", limit: int = 25) -> list:
    """
    Calls the NSF Awards API to search for grants.
    """
    try:
        url = "https://api.nsf.gov/services/v1/awards.json"
        
        def fetch_awards(kw, inst):
            search_term = f"{kw} {inst}".strip() if inst else kw
            params = {
                "keyword": search_term,
                "dateStart": "01/01/2022",
                "printFields": "id,title,piFirstName,piLastName,awardeeName,fundsObligatedAmt,startDate,expDate,abstractText"
            }
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("response", {}).get("award", [])
            
        awards = fetch_awards(keyword, institution)
        if not awards and institution:
            awards = fetch_awards(keyword, "")

        seen_ids = set()
        unique_awards = []
        for award in awards:
            award_id = award.get("id")
            if award_id not in seen_ids:
                seen_ids.add(award_id)
                unique_awards.append(award)

        results = []
        for award in unique_awards:
            pi_name = f"{award.get('piFirstName', '')} {award.get('piLastName', '')}".strip()
            amount_str = award.get("fundsObligatedAmt", "0")
            try:
                amount = int(amount_str)
            except (ValueError, TypeError):
                amount = 0
            results.append({
                "id": award.get("id"),
                "title": award.get("title"),
                "pi_name": pi_name,
                "institution": award.get("awardeeName"),
                "amount": amount,
                "abstract": award.get("abstractText")
            })

        results.sort(key=lambda x: x["amount"], reverse=True)
        return results[:limit]
        
    except Exception as e:
        print(f"Error calling NSF Grants API: {e}")
        return []


def lookup_nsf_funding(professor_name: str) -> dict:
    """
    Looks up NSF grant data for a specific professor by name.
    Tries pdPIName first; falls back to keyword search on last name.
    Returns the highest-value grant found, or empty dict if none.
    """
    nsf_url = "https://api.nsf.gov/services/v1/awards.json"
    print_fields = "id,title,piFirstName,piLastName,awardeeName,fundsObligatedAmt,abstractText,piEmail"
    all_awards = []

    try:
        # Strategy 1: search by PI name
        resp = requests.get(nsf_url, params={
            "pdPIName": professor_name,
            "dateStart": "01/01/2020",
            "printFields": print_fields
        }, timeout=8)
        resp.raise_for_status()
        all_awards += resp.json().get("response", {}).get("award", [])
    except Exception:
        pass

    # Strategy 2: keyword search on last name if no results yet
    if not all_awards:
        try:
            last_name = professor_name.strip().split()[-1] if professor_name.strip() else ""
            if last_name:
                resp2 = requests.get(nsf_url, params={
                    "keyword": last_name,
                    "dateStart": "01/01/2020",
                    "printFields": print_fields
                }, timeout=8)
                resp2.raise_for_status()
                all_awards += resp2.json().get("response", {}).get("award", [])
        except Exception:
            pass

    if not all_awards:
        return {}

    best = max(all_awards, key=lambda a: int(a.get("fundsObligatedAmt") or 0), default=None)
    if not best:
        return {}
    amount = int(best.get("fundsObligatedAmt") or 0)
    return {
        "grant_title": best.get("title", ""),
        "grant_amount": f"${amount:,}",
        "abstract": best.get("abstractText", ""),
        "pi_email": best.get("piEmail", "")
    }


def search_semantic_scholar(professor_name: str, institution: str = "") -> list:
    """
    Calls the Semantic Scholar API to find a professor's recent papers.
    """
    try:
        time.sleep(3)
        url = "https://api.semanticscholar.org/graph/v1/author/search"
        params = {
            "query": professor_name,
            "fields": "name,affiliations,papers.title,papers.year,papers.citationCount,papers.venue",
            "limit": 5
        }
        headers = {}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        if api_key:
            headers["x-api-key"] = api_key
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 429:
            time.sleep(5)
            response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if not data.get("data"):
            return []
        author = data["data"][0]
        if institution:
            for a in data["data"]:
                affiliations = [affil.lower() for affil in a.get("affiliations", []) or []]
                if any(institution.lower() in affil for affil in affiliations):
                    author = a
                    break
        papers = author.get("papers", [])
        current_year = datetime.now().year
        recent_papers = []
        for p in papers:
            year = p.get("year")
            if year and (current_year - year) <= 3:
                recent_papers.append({
                    "title": p.get("title"),
                    "year": year,
                    "citation_count": p.get("citationCount"),
                    "venue": p.get("venue")
                })
        return recent_papers
    except Exception:
        return []


def search_web(query: str, institution: str = "") -> str:
    """
    Uses DuckDuckGo to search the web and returns the top 3 results.
    """
    try:
        if institution and institution.lower() not in query.lower():
            query = f"{institution} faculty {query}"
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
        output = []
        for r in results:
            output.append(f"Title: {r.get('title')}\nBody: {r.get('body')}")
        return "\n\n".join(output)
    except Exception as e:
        return f"Error searching web: {e}"


def _extract_field_from_query(query: str) -> str:
    """Extract the core STEM field from a user query."""
    field_hints = [
        "ai hardware", "chip design", "vlsi", "neuromorphic", "hardware accelerator",
        "machine learning", "deep learning", "robotics", "computer vision",
        "natural language processing", "nlp", "reinforcement learning",
        "biomedical engineering", "computational biology", "bioinformatics",
        "electrical engineering", "mechanical engineering", "materials science",
        "quantum computing", "cybersecurity", "computer architecture",
        "data science", "signal processing"
    ]
    q = query.lower()
    for hint in field_hints:
        if hint in q:
            return hint
    words = [w for w in q.split() if len(w) > 3 and w not in
             ("find", "funded", "professor", "professors", "faculty", "with", "that", "have", "about")]
    return " ".join(words[:3]) if words else query


def _extract_professors_with_claude(results: list, seen_names: set) -> list:
    """
    Uses Claude Haiku to extract professor info from raw DuckDuckGo search results.
    Returns a list of new professor dicts (deduplicated against seen_names).
    """
    if not results:
        return []

    # Build a compact text block of all results
    raw_text = ""
    for i, r in enumerate(results):
        raw_text += f"Result {i+1}:\nTitle: {r.get('title', '')}\nURL: {r.get('href', '')}\nBody: {r.get('body', '')}\n\n"

    prompt = (
        "From these search results, extract all professors/faculty members you can identify. "
        "For each one return a JSON array with objects containing:\n"
        "- name: professor full name\n"
        "- institution: university name\n"
        "- email: their email address if found in the results (look for @university.edu patterns), otherwise empty string\n"
        "- research_description: 1-2 sentences about their research\n\n"
        "Look carefully for email addresses - they often appear as username@university.edu or "
        "firstname.lastname@university.edu. Only include real academic faculty. "
        "Return ONLY valid JSON array, nothing else.\n\n"
        + raw_text
    )

    try:
        haiku_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = haiku_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = re.sub(r"```(?:json)?\n?", "", text).rstrip("`").strip()
        extracted = json.loads(text)
        if not isinstance(extracted, list):
            return []
    except Exception as e:
        print(f"  ⚠ Claude extraction error: {e}", flush=True)
        return []

    personal_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"]
    valid_email_re = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$")
    
    new_professors = []
    for item in extracted:
        name = item.get("name", "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        
        # Validate email before storing
        email = item.get("email", "").strip().lower()
        if email:
            # Reject personal email domains
            if any(domain in email for domain in personal_domains):
                email = ""
            # Reject invalid email format
            elif not valid_email_re.match(email):
                email = ""
            # Only accept .edu emails
            elif not email.endswith(".edu"):
                email = ""
        
        new_professors.append({
            "name": name,
            "institution": item.get("institution", ""),
            "email": email,
            "research_description": item.get("research_description", ""),
            "grant_title": "",
            "grant_amount": "Unknown",
            "abstract": ""
        })

    return new_professors


def discover_professors(query: str, limit: int = 50, status_callback=None) -> list:
    """
    Discovers professors using 10 DuckDuckGo searches, then verifies
    their funding via the NSF API. Returns up to `limit` unique professors.
    """
    if status_callback:
        status_callback("🔍 Searching the web for professors...")

    field = _extract_field_from_query(query)
    print(f"🔍 Discovering '{field}' professors via web search...", flush=True)

    searches = [
        f"{field} professor funded research site:edu",
        f"{field} faculty NSF grant university",
        f"{field} professor PhD students research lab",
        f"funded {field} research professor active grant",
        f"{field} assistant associate professor NSF CAREER award",
        f"{field} professor NSF CAREER award chip design",
        f"{field} research lab university funded PhD openings",
        f"{field} associate professor NSF grant recent publications",
        f"{field} professor IEEE fellow funded research",
        f"{field} faculty member active NSF award university",
    ]

    seen_names: set = set()
    all_professors: list = []

    with DDGS() as ddgs:
        for search_query in searches:
            if len(all_professors) >= limit:
                break
            try:
                results = list(ddgs.text(search_query, max_results=15))
                new_profs = _extract_professors_with_claude(results, seen_names)
                all_professors.extend(new_profs)
                print(f"  → '{search_query[:55]}...': {len(new_profs)} new professors", flush=True)
            except Exception as e:
                print(f"  ⚠ Search error for '{search_query[:40]}': {e}", flush=True)
            time.sleep(0.5)

    if status_callback:
        status_callback("✅ Web search complete — verifying NSF funding...")
    print(f"🌐 Web discovery: {len(all_professors)} professors found. Verifying NSF funding...", flush=True)

    for i, prof in enumerate(all_professors[:limit]):
        funding = lookup_nsf_funding(prof["name"])
        if funding:
            prof["grant_title"] = funding.get("grant_title", "")
            prof["grant_amount"] = funding.get("grant_amount", "Unknown")
            prof["abstract"] = funding.get("abstract", "")
            # Use NSF email as fallback if web search didn't find one
            if not prof.get("email") and funding.get("pi_email"):
                nsf_email = funding["pi_email"].strip().lower()
                personal_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"]
                if nsf_email and not any(domain in nsf_email for domain in personal_domains) and nsf_email.endswith(".edu"):
                    prof["email"] = nsf_email
        time.sleep(0.3)
        if (i + 1) % 10 == 0:
            print(f"  ✓ Verified {i + 1}/{min(len(all_professors), limit)}", flush=True)

    # --- Semantic Scholar: fetch recent papers for each professor ---
    if status_callback:
        status_callback("📚 Fetching recent publications...")
    print(f"📚 Fetching recent papers from Semantic Scholar...", flush=True)
    for i, prof in enumerate(all_professors[:limit]):
        try:
            papers = search_semantic_scholar(prof["name"], prof.get("institution", ""))
            if papers:
                formatted = [
                    f"{p.get('title', 'Untitled')} ({p.get('venue', 'Unknown venue')}, "
                    f"{p.get('year', '?')}, {p.get('citation_count', 0)} citations)"
                    for p in papers[:4]
                ]
                prof["recent_papers"] = formatted
            else:
                prof["recent_papers"] = ["See faculty page"]
        except Exception:
            prof["recent_papers"] = ["See faculty page"]
        time.sleep(1)
        if (i + 1) % 5 == 0:
            print(f"  📚 Papers fetched for {i + 1}/{min(len(all_professors), limit)}", flush=True)

    # --- Email enrichment: targeted DuckDuckGo + Claude verification ---
    missing_email = [p for p in all_professors[:limit] if not p.get("email")]
    if missing_email:
        if status_callback:
            status_callback("📧 Looking up email addresses...")
        print(f"📧 Fetching missing emails for {len(missing_email)} professors...", flush=True)
        valid_email_re = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$")
        haiku_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        with DDGS() as ddgs:
            for prof in missing_email:
                try:
                    name = prof["name"]
                    institution = prof.get("institution", "")
                    # Use first + last name for precision
                    parts = name.strip().split()
                    first = parts[0] if parts else name
                    last = parts[-1] if len(parts) > 1 else ""
                    search_q = f"{first} {last} email {institution}".strip()
                    hits = list(ddgs.text(search_q, max_results=5))
                    if not hits:
                        continue

                    # Build snippet context for Claude
                    snippets = "\n\n".join(
                        f"Title: {h.get('title', '')}\nURL: {h.get('href', '')}\nBody: {h.get('body', '')}"
                        for h in hits
                    )
                    verify_prompt = (
                        f"From these search results, find the email address that belongs to "
                        f"Professor {name} at {institution}. "
                        "Only return their direct faculty email (usually firstname.lastname@university.edu or similar). "
                        "If you cannot confidently identify their specific email, return empty string. "
                        "Return ONLY the email address or empty string, nothing else.\n\n"
                        + snippets
                    )
                    resp = haiku_client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=50,
                        messages=[{"role": "user", "content": verify_prompt}]
                    )
                    candidate = resp.content[0].text.strip().lower()
                    # Only accept if it looks like a real email
                    if candidate and valid_email_re.match(candidate):
                        # Reject personal email domains
                        personal_domains = ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com"]
                        if any(domain in candidate for domain in personal_domains):
                            candidate = ""
                        
                        # Reject emails where domain doesn't match institution
                        if candidate and prof.get("institution"):
                            institution_lower = prof["institution"].lower()
                            inst_keywords = {
                                "mit": "mit", "stanford": "stanford", "purdue": "purdue",
                                "duke": "duke", "michigan": "umich", "berkeley": "berkeley",
                                "georgia tech": "gatech", "cornell": "cornell", "illinois": "illinois",
                                "yale": "yale", "columbia": "columbia", "princeton": "princeton",
                                "carnegie mellon": "cmu", "northwestern": "northwestern",
                                "texas": "utexas", "washington": "washington"
                            }
                            email_domain = candidate.split("@")[-1].lower()
                            matched = False
                            for inst_key, domain_key in inst_keywords.items():
                                if inst_key in institution_lower and domain_key in email_domain:
                                    matched = True
                                    break
                            if not matched and any(key in institution_lower for key in inst_keywords.keys()):
                                candidate = ""
                        
                        if candidate:
                            prof["email"] = candidate
                except Exception:
                    pass
                time.sleep(0.4)

    result = all_professors[:limit]
    print(f"✅ Discovery complete: {len(result)} professors ready.", flush=True)
    return result
