import json
from tools import search_nsf_grants, search_semantic_scholar, search_web

def main():
    print("=== Testing search_nsf_grants ===")
    nsf_results = search_nsf_grants(keyword="AI hardware accelerator", institution="Purdue University")
    print("\nParsed NSF Results:")
    print(json.dumps(nsf_results, indent=2))
    
    print("\n=== Testing search_semantic_scholar ===")
    ss_results = search_semantic_scholar(professor_name="Tor Aamodt", institution="UBC")
    print(json.dumps(ss_results, indent=2))
    
    print("\n=== Testing search_web ===")
    web_results = search_web(query="AI hardware professors Purdue University faculty")
    print(web_results)

if __name__ == "__main__":
    main()
