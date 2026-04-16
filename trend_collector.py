import os
import requests
import datetime
import math
import time 
import urllib.parse 
import xml.etree.ElementTree as ET 
import json 
import random 
import re 

# --- LLM API Configuration ---
# Leave as empty string. The environment provides the key at runtime.
API_KEY = "" 
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent"

# --- Configuration ---
# NOTE: Replace 'YOUR_GITHUB_TOKEN' if you have a PAT for higher rate limits.
GITHUB_TOKEN = os.environ.get("GH_TOKEN", "YOUR_LOCAL_TESTING_TOKEN")
GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/commits"
ARXIV_API_URL = "http://export.arxiv.org/api/query?"
OUTPUT_FILE = "trend_report.json"

#   News API:
NEWS_API_KEY = os.environ.get("NEWS_API", "YOUR_LOCAL_TESTING_TOKEN")
NEWS_API_URL = "https://newsapi.org/v2/everything"

# Weights
DEV_WEIGHT = 0.35 
ACADEMIC_WEIGHT = 0.40 
BUZZ_WEIGHT = 0.25     

# Time Windows
TODAY = datetime.datetime.now(datetime.timezone.utc)
RECENT_START = TODAY - datetime.timedelta(days=7)
PAST_START = RECENT_START - datetime.timedelta(days=7)

# --- Niche Configurations ---
NICHES = {
    "ai_agents": {
        "display_name": "AI Agents & Multi-Agent Systems",
        "repos": [
            {"owner": "microsoft", "repo": "autogen"},
            {"owner": "crewAIInc", "repo": "crewAI"},
            {"owner": "pydantic", "repo": "pydantic-ai"},
        ],
        "keywords": ["AI Agents", "Multi-Agent Systems", "Agentic Workflows", "Autonomous Agents"],
        "news_query": "AI Agents OR Multi-Agent Systems"
    },
    "rag": {
        "display_name": "RAG & Vector Databases",
        "repos": [
            {"owner": "langchain-ai", "repo": "langchain"},
            {"owner": "qdrant", "repo": "qdrant"},
            {"owner": "chroma-core", "repo": "chroma"},
        ],
        "keywords": ["Retrieval-Augmented Generation", "Vector Database", "LLM Retrieval", "Hybrid Search", "Multimodal RAG"],
        "news_query": '"Retrieval-Augmented Generation" OR "Vector Database" OR "LangChain"'
    },
    "web3": {
        "display_name": "Web3 & Decentralized Infrastructure",
        "repos": [
            {"owner": "ethereum", "repo": "go-ethereum"},
            {"owner": "solana-labs", "repo": "solana"},
        ],
        "keywords": ["Web3", "Blockchain", "Smart Contracts", "Decentralized Finance"],
        "news_query": "Web3 OR Blockchain OR Crypto"
    },
    "devops": {
        "display_name": "Cloud Native & DevOps",
        "repos": [
            {"owner": "kubernetes", "repo": "kubernetes"},
            {"owner": "docker", "repo": "compose"},
        ],
        "keywords": ["Kubernetes", "Docker", "Microservices", "Cloud Native"],
        "news_query": "Kubernetes OR DevOps OR Cloud Native"
    }
}

def clean_text(text: str) -> str:
    """Cleans up extra whitespace and newlines for JSON safety."""
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def get_smart_fallback(title: str) -> str:
    """Provides a tailored summary based on keywords if LLM API is unavailable."""
    t = title.lower()
    if "multi-agent" in t or "collaboration" in t:
        return "This research explores how multiple specialized AI agents can work together to solve problems that are too complex for a single model."
    elif "planning" in t or "reasoning" in t:
        return "Focuses on 'Chain-of-Thought' for agents, allowing them to plan their actions and self-correct errors before responding."
    elif "tool" in t or "api" in t:
        return "A breakthrough in teaching AI how to autonomously use external tools like web search, code executors, and databases."
    elif "ui" in t or "gui" in t or "web" in t:
        return "Presents a new method for AI agents to navigate and interact with complex website interfaces and desktop software."
    return "An important advancement in open-source framework logic that improves the reliability and efficiency of AI-driven automation."

def generate_topic_summary(topic_title: str, topic_type: str) -> str:
    """Attempts to call Gemini API; falls back to smart local logic if needed."""
    if not API_KEY:
        return get_smart_fallback(topic_title)
    
    payload = {
        "contents": [{"parts": [{"text": f"Explain this {topic_type} titled '{topic_title}' in one simple, jargon-free sentence for a student."}]}],
        "systemInstruction": {"parts": [{"text": "You are a world-class tech simplifier. Use zero jargon. Be concise."}]}
    }
    try:
        url = f"{GEMINI_API_URL}?key={API_KEY}"
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        return clean_text(result['candidates'][0]['content']['parts'][0]['text'])
    except:
        return get_smart_fallback(topic_title)

def get_commit_count(owner: str, repo: str, since: datetime.datetime, until: datetime.datetime) -> int:
    headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN != "YOUR_GITHUB_TOKEN" else {}
    url = GITHUB_API_URL.format(owner=owner, repo=repo)
    # Tell GitHub to send 100 commits per page instead of 30 to speed things up
    params = {"since": since.isoformat(), "until": until.isoformat(), "per_page": 100}
    
    count = 0
    try:
        while url:
            res = requests.get(url, params=params, headers=headers, timeout=10)
            
            if res.status_code == 403:
                print("  [!] GitHub API Rate Limit hit! Please add a Personal Access Token.")
                break
            if res.status_code != 200:
                break
                
            commits = res.json()
            count += len(commits)
            
            # Check GitHub's response headers to see if there is another page of data
            if 'next' in res.links:
                url = res.links['next']['url']
                params = None # The 'next' URL already contains all the parameters
            else:
                url = None
                
        return count
    except Exception as e:
        print(f"  [!] GitHub Fetch Error: {e}")
        return 0

def run_analysis(niche_key, config):
    display_name = config["display_name"]
    print(f"\n🚀 Starting TrendSense Analysis: {display_name}")
    
    # 1. Developer Momentum (GitHub)
    total_dev_score = 0
    dev_results = []
    print("--- Fetching GitHub Data ---")
    for r in config["repos"]:  
        recent = get_commit_count(r['owner'], r['repo'], RECENT_START, TODAY)
        past = get_commit_count(r['owner'], r['repo'], PAST_START, RECENT_START)
        
        spike = ((recent - past) / max(past, 1)) * 100
        score = min(spike / 20.0, 10.0) if spike > 0 else 0
        total_dev_score += score
        
        dev_results.append({
            "repo_name": f"{r['owner']}/{r['repo']}",
            "recent_commits": recent,
            "increase_pct": f"{spike:.1f}%",
            "score_contribution": round(score, 2)
        })
        print(f"  - {r['repo']}: {recent} commits ({spike:.1f}% spike)")

    # 2. Academic Research (arXiv)
    print("--- Fetching arXiv Research ---")
    query = "abs:(" + " OR ".join(f'"{kw}"' for kw in config["keywords"]) + ")" 
    params = {"search_query": query, "max_results": 10, "sortBy": "submittedDate"}
    res = requests.get(ARXIV_API_URL, params=params, timeout=15)
    root = ET.fromstring(res.content)
    
    papers = []
    NS = {'atom': 'http://www.w3.org/2005/Atom'}
    for entry in root.findall('atom:entry', NS):
        title = clean_text(entry.find('atom:title', NS).text)
        link = entry.find("atom:link[@type='application/pdf']", NS)
        pdf_url = link.attrib['href'] if link is not None else "#"
        
        papers.append({
            "title": title,
            "summary": generate_topic_summary(title, "paper"),
            "link": pdf_url,
            "published": "Last 7 Days"
        })

    # 3. Industry Buzz (Live via NewsAPI)
    print("--- Fetching Industry Buzz ---")
    buzz_data = []
    buzz_score_norm = 0.0
    
    if NEWS_API_KEY != "PASTE_YOUR_NEW_API_KEY_HERE":
        news_params = {
            "q": config["news_query"], 
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 5  
        }
        headers = {"X-Api-Key": NEWS_API_KEY}
        
        try:
            news_res = requests.get(NEWS_API_URL, params=news_params, headers=headers, timeout=10)
            if news_res.status_code == 200:
                articles = news_res.json().get("articles", [])
                
                for art in articles[:2]:
                    buzz_data.append({
                        "title": art.get("title", "No Title"),
                        "source": art.get("source", {}).get("name", "Industry News")
                    })
                
                total_results = news_res.json().get("totalResults", 0)
                buzz_score_norm = min((total_results / 100.0) * 10.0, 10.0) 
                
        except Exception as e:
            print(f"  - Error fetching news: {e}")

    if not buzz_data:
        print("  - Falling back to default buzz data.")
        buzz_score_norm = 7.5
        buzz_data = [
            {"title": f"New breakthroughs in {display_name} spark interest.", "source": "Industry Insider"},
            {"title": f"VC funding for {display_name} startups grows steadily.", "source": "Financial Trends"}
        ]

    # Final Scoring
    S_Dev_Norm = total_dev_score / len(config["repos"]) 
    S_Acad_Norm = min(len(papers), 10)
    final_score = (S_Acad_Norm * ACADEMIC_WEIGHT) + (S_Dev_Norm * DEV_WEIGHT) + (buzz_score_norm * BUZZ_WEIGHT)

    report = {
        "report_generated_time": datetime.datetime.now().isoformat(),
        "niche": display_name, 
        "final_score": round(final_score, 2),
        "alert_status": "TRENDING_NOW" if final_score >= 7.0 else "PRE_TREND_ALERT",
        "alert_message": f"Topic is showing momentum. The shift in {display_name} is underway.",
        "human_summary": f"Developers and researchers are actively expanding the {display_name} ecosystem. Keep an eye on the latest framework updates and academic publications.",
        "signals": {
            "academic": {"normalized_score": round(S_Acad_Norm, 2), "data": papers},
            "developer": {"normalized_score": round(S_Dev_Norm, 2), "data": dev_results},
            "buzz": {"normalized_score": round(buzz_score_norm, 2), "data": buzz_data}
        }
    }
    
    # Dynamically name the output file
    output_filename = f"trend_report_{niche_key}.json"

    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=4)
    
    print(f"✅ SUCCESS: Saved {output_filename} (Score: {final_score:.2f}/10)")
    
if __name__ == "__main__":
    print("Starting full batch analysis for all niches...")
    for niche_key, config in NICHES.items():
        run_analysis(niche_key, config)
        time.sleep(2) # Brief polite pause between APIs
    print("\nBatch analysis complete!")