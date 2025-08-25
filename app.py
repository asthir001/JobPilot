import os
import json
import time
import requests 
from openai import OpenAI
from serpapi.google_search import GoogleSearch
import PyPDF2
import re
from firecrawl import FirecrawlApp
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit
import sys
import io

class Colors:
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './uploads'
socketio = SocketIO(app)
app.secret_key = 'your_secret_key'


OPENAI_API_KEY= os.getenv("OPENAI_API_KEY")
FIRECRAWL_API_KEY= os.getenv("FIRECRAWL_API_KEY")
SERP_API_KEY= os.getenv("SERP_API_KEY")

    
# Initialize clients
client = OpenAI(
  base_url="https://openrouter.ai/api/v1",
  api_key=OPENAI_API_KEY,
)
firecrawl_api_key = FIRECRAWL_API_KEY
serp_api_key = SERP_API_KEY

def read_resume(file_path):
    """Read the resume from the given PDF file path."""
    try:
        with open(file_path, 'rb') as file:  # Open the PDF file in binary mode
            reader = PyPDF2.PdfReader(file)
            resume_text = ""
            for page in reader.pages:
                resume_text += page.extract_text()  # Extract text from each page
            return resume_text
    except Exception as e:
        print(f"Error reading resume: {str(e)}")
        return None
    
# Function to extract job titles from resume text using LLM and clean them
def extract_job_titles(resume_text):
    prompt = """
    Just list top 3 job titles where I can apply based on my Resume.
    Return them in a comma-separated format like:
    Data Scientist, Business Analyst, Product Manager
    Do not include explanations or numbering.
    """

    try:
        response = client.chat.completions.create(
        model="deepseek/deepseek-r1:free",
        messages=[
            {"role": "system", "content": "You are a helpful assistant specialized in analyzing resumes."},
            {"role": "user", "content": f"{prompt}:\n\n{resume_text}"},
        ],
        stream=False,
    )

        raw_output = response.choices[0].message.content.strip()
        print(f"{Colors.YELLOW}Raw LLM Output: {raw_output}{Colors.RESET}")

        # Extract words that look like titles
        titles = re.findall(r"\b(?:[A-Z][a-z]+(?: [A-Z][a-z]+)*)\b", raw_output)
        cleaned = [title.strip() for title in titles if len(title.strip()) > 3]
        top_3 = cleaned[:3]

        return top_3

    except Exception as e:
        print(f"{Colors.RED}❌ Error extracting job titles: {str(e)}{Colors.RESET}")
        return []
    
def is_valid_job_site(url):
    """Return True if the URL is from a known job listing platform."""
    allowed_domains = [
        "greenhouse.io", "lever.co", "jobs.apple.com", "careers.google.com",
        "workday.com", "ashbyhq.com", "smartrecruiters.com", "recruiting.adp.com"
    ]
    return any(domain in url for domain in allowed_domains)   

def fetch_visible_text_from_page(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
            tag.decompose()
        visible_text = soup.get_text(separator="\n")
        return visible_text.strip()
    except Exception as e:
        print(f"{Colors.RED}Error fetching fallback HTML for {url}: {e}{Colors.RESET}")
        return None


def clean_json_string(text):
    text = text.strip()

    # Remove triple backticks or markdown formatting
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()

    # Optionally remove leading text before actual JSON
    match = re.search(r"{.*}", text, re.DOTALL)
    return match.group(0) if match else text

def extract_job_details_with_llm(page_text, link):
    prompt = f"""
                You are a helpful assistant extracting job information.

                Given this job description page, extract:
                - job_title (string)
                - company_name (string, if known)
                - location (string)
                - experience_level (string, e.g., Entry, Mid, Senior or '3+ years')
                - required_skills (comma-separated list or array)
                - job_description (string, max 500 words)

                Text:
                \"\"\"
                {page_text[:4000]}
                \"\"\"

                Return only JSON like:
                {{
                "job_title": "...",
                "company_name": "...",
                "location": "...",
                "experience_level": "...",
                "required_skills": ["..."],
                "job_description": "..."
                }}
                """

    try:
        response = client.chat.completions.create(
            model="deepseek/deepseek-chat",
            messages=[
                {"role": "system", "content": "You extract structured job data from raw job text."},
                {"role": "user", "content": prompt}
            ],
            stream=False,
        )
        content = response.choices[0].message.content
        print(f"{Colors.YELLOW}🔍 Raw LLM response for {link}:\n{content}{Colors.RESET}")  # Debug print

        # Clean and parse
        cleaned = clean_json_string(content)
        data = json.loads(cleaned)
        data["source"] = link
        return data

    except Exception as e:
        print(f"{Colors.RED}❌ LLM fallback failed for {link}: {e}{Colors.RESET}")
        return None

def find_relevant_jobs(resume_text):
    """Extract top 3 relevant job titles from resume text using LLM."""
    prompt = """just list top 3 job titles where I can apply based on my resume.
    Titles should be in a comma separated format like ---> Software Engineer, Data Scientist, Product Manager
    P.S.: Do not include any other information, just the job titles."""

    try:
        response = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct",  # or any other model supported by OpenRouter
            messages=[
                {"role": "system", "content": "You are a helpful assistant specialized in analyzing resumes."},
                {"role": "user", "content": f"{prompt}\n\n{resume_text}"},
            ],
            stream=False,
        )

        if response and hasattr(response, "choices"):
            job_titles_text = response.choices[0].message.content.strip()
            job_titles = [title.strip() for title in job_titles_text.split(",") if title.strip()]
            return job_titles

        else:
            print(f"{Colors.RED}No job titles found in response.{Colors.RESET}")
            return []

    except Exception as e:
        print(f"{Colors.RED}Error during job title extraction: {e}{Colors.RESET}")
        return []

@app.route('/')
def index():
    # Render the template with default values (None or empty lists)
    return render_template('index.html', job_titles=None, search_results=None, job_details=None, ranked_jobs=None)

@app.route('/upload', methods=['POST'])
def upload_file():
    
    print(f"Loaded API Key: {os.getenv('OPENAI_API_KEY')}")
    print(f"Loaded Firecrawl API Key: {os.getenv('FIRECRAWL_API_KEY')}")
    print(f"Loaded SerpAPI Key: {os.getenv('SERP_API_KEY')}")
    # Check if the post request has the file part
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']

    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Read the resume and process it
        resume_text = read_resume(file_path)
        session['resume_text'] = resume_text  # Store resume text in session
        job_titles = extract_job_titles(resume_text)
        # job_titles = ["Business Analyst", "Project Manager", "Data Analyst"]
        session['job_titles'] = job_titles  # Store job titles in session
        # search_results = search_jobs_on_google(job_titles)
        # filtered_results = [r for r in search_results if is_valid_job_site(r["link"])]
        
        # links = [result["link"] for result in filtered_results]
        # job_details = scrape_job_details(links)
        # ranked_jobs = rank_jobs(job_details, resume_text)

        return render_template('upload.html', job_titles=job_titles)

@app.route('/search', methods=['POST'])
def search_jobs_on_google():
    """Search for job postings on real job platforms using SerpAPI."""
    try:
        job_titles = session.get('job_titles', [])
        search_results = []

        # Limit results to real job platforms only
        allowed_sites = [
            "site:careers.google.com", 
            "site:jobs.apple.com", 
            "site:boards.greenhouse.io", 
            "site:jobs.lever.co",
            "site:workday.com",
            "site:smartrecruiters.com"
        ]

        for title in job_titles:
            query = f'({" OR ".join(allowed_sites)}) "{title}"'
            search_params = {
                "q": query,
                "engine": "google",
                "google_domain": "google.com",
                "api_key": serp_api_key,
                "num": request.form.get('num', default=3, type=int)
            }

            response = requests.get("https://serpapi.com/search", params=search_params)
            if response.status_code != 200:
                print(f"{Colors.RED}❌ Error for '{title}': {response.json().get('error', 'Unknown error')}{Colors.RESET}")
                continue

            results = response.json().get("organic_results", [])
            for result in results:
                search_results.append({
                    "title": result.get("title"),
                    "link": result.get("link"),
                    "snippet": result.get("snippet")
                })
        
        filtered_results = [r for r in search_results if is_valid_job_site(r["link"])]
        if not filtered_results:
            print(f"{Colors.RED}❌ No valid job listings found on supported sites.{Colors.RESET}")
            return
        session['filtered_results'] = filtered_results
        return render_template('search.html', search_results=filtered_results)

    except Exception as e:
        print(f"{Colors.RED}❌ Error searching jobs on Google: {str(e)}{Colors.RESET}")
        return []
    
@socketio.on('start_scraping')
def scrape_job_details():
    """Scrapes job details using Firecrawl one-by-one, and uses local HTML+LLM fallback if needed."""
    all_results = []
    fallback_used = 0
    empty_extractions = 0
    failed_count = 0

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {firecrawl_api_key}'
    }

    job_prompt = """
    Extract only:
    - job_title: position title (string)
    - required_skills: skills (array)
    - experience_level: years required (string)
    - job_description: description (string)
    - company_name: name of the company (string)    
    - location: job location (string)
    """
    links = session.get('filtered_results', [])
    if not links:
        emit('Logs', {'message': '❌ No job links available to scrape.'})
        return []
    emit('Logs', {'message': f'Scraping {len(links)} job links one-by-one with fallback logic...'})
        
    for idx, link in enumerate(links, 1):
        print(f"{Colors.CYAN}⏳ Scraping [{idx}/{len(links)}]: {link}{Colors.RESET}")
        emit('Logs', {'message': f'⏳ Scraping [{idx}/{len(links)}]: {link}'})
        payload = {
            "urls": [link],
            "prompt": job_prompt,
            "enableWebSearch": False
        }

        try:
            response = requests.post(
                "https://api.firecrawl.dev/v1/extract",
                headers=headers,
                json=payload,
                timeout=30
            )
            data = response.json()

            job_data = data.get("data", [])
            if data.get("success") and job_data:
                all_results.extend(job_data)
                emit('Logs', {'message': f'✅ Extracted with prompt [{idx}]'})                                  
            else:
                fallback_used += 1
                emit('Logs', {'message': f'⚠️ No structured job data. Using local HTML + LLM fallback [{idx}]...'})
                # Fallback to local HTML + LLM extraction
                raw_text = fetch_visible_text_from_page(link)
                if raw_text:
                    llm_result = extract_job_details_with_llm(raw_text, link)
                    if llm_result:
                        all_results.append(llm_result)
                        emit('Logs', {'message': f'🧠 LLM successfully extracted job info from local fallback HTML.'})
                    else:
                        empty_extractions += 1
                        emit('Logs', {'message': f'⚠️ LLM could not parse fallback page [{idx}]'})        
                else:
                    empty_extractions += 1
                    emit('Logs', {'message': f'⚠️ No content from local HTML scrape [{idx}]'})
        

        except Exception as e:
            failed_count += 1
            print(f"{Colors.RED}❌ Error scraping [{idx}]: {link}\nReason: {str(e)}{Colors.RESET}")
            emit('Logs', {'message': f'❌ Error scraping [{idx}]: {link}\nReason: {str(e)}'})


        time.sleep(6)  # Respect Firecrawl rate limit

    print(f"\n{Colors.GREEN}✅ Jobs extracted: {len(all_results)}{Colors.RESET}")
    emit('Logs', {'message': f'✅ Jobs extracted: {len(all_results)}'}) 
    print(f"{Colors.YELLOW}⚠️ Fallbacks used: {fallback_used}{Colors.RESET}")
    emit('Logs', {'message': f'⚠️ Fallbacks used: {fallback_used}'})   
    print(f"{Colors.YELLOW}⚠️ Pages with no usable data: {empty_extractions}{Colors.RESET}")
    emit('Logs', {'message': f'⚠️ Pages with no usable data: {empty_extractions}'})    
    print(f"{Colors.RED}❌ Failed requests: {failed_count}{Colors.RESET}")
    emit('Logs', {'message': f'❌ Failed requests: {failed_count}'})      
    
    session['all_results'] = all_results
    print("Session all_results:", session.get('all_results'))
    return all_results

@app.route('/results', methods=['POST'])
def rank_jobs():
    """Rank jobs based on resume relevance and suggest ATS-friendly keywords."""
    
    resume_text = session.get('resume_text', [])
    jobs = session.get('all_results', [])
    try:
        prompt = f"""
        You are an expert resume coach and ATS system analyst.

        TASK 1:
        Based on the following resume, rank the given jobs by relevance and provide a score out of 10 for each job.

        TASK 2:
        For each job, extract 5-10 keywords or phrases from the job description that are:
        - Important for the role
        - Missing or weakly mentioned in the resume
        - Likely to improve ATS compatibility if added

        Resume:
        {resume_text}

        Jobs:
        {json.dumps(jobs, indent=2)}

        Format your output as a JSON array like this:
        [
          {{
            "job_title": "...",
            "company_name": "...",
            "location": "...",
            "relevance_score": X,
            "reason": "...",
            "recommended_keywords": ["keyword1", "keyword2", "..."]
          }},
          ...
        ]
        """

        response = client.chat.completions.create(
            model="deepseek/deepseek-r1:free",
            messages=[
                {"role": "system", "content": "You are a career advisor and resume optimization expert."},
                {"role": "user", "content": prompt}
            ]
        )
        cleaned_response = clean_json_string(response.choices[0].message.content)
        ranked_jobs = json.loads(cleaned_response)
        return render_template('results.html', ranked_jobs=ranked_jobs)

    except Exception as e:
        print(f"{Colors.RED}Error ranking jobs: {str(e)}{Colors.RESET}")
        return []


if __name__ == "__main__":
    app.run(debug=True)
    
    
    


