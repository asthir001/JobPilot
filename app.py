import os
import json
import time
import requests 
from openai import OpenAI
from serpapi import GoogleSearch
import PyPDF2
import re
from firecrawl import FirecrawlApp
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit
import logging
import sys
import io

class Colors:
    CYAN = '\033[96m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    RESET = '\033[0m'


OPENAI_API_KEY= os.getenv("OPENAI_API_KEY")
FIRECRAWL_API_KEY=os.getenv("FIRECRAWL_API_KEY")
SERP_API_KEY=os.getenv("SERP_API_KEY")


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = './uploads'
socketio = SocketIO(app, manage_session=True)
app.secret_key = 'your_secret_key'

global_scraped_results = []


# Initialize clients
client = OpenAI(
    api_key=OPENAI_API_KEY,
    base_url="https://openrouter.ai/api/v1" # read from environment
)

firecrawl_api_key = FIRECRAWL_API_KEY
serp_api_key      = SERP_API_KEY



class SocketIOLogHandler(logging.Handler):
    def emit(self, record):
        """Send log message to the client via SocketIO 'Logs' event."""
        log_msg = self.format(record)
        socketio.emit('Logs', {'message': log_msg})

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

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
    


def pretty_console_block(jobs: list[dict]) -> str:
    """Return a clean multiline string for the textarea console."""
    lines = []
    for i, j in enumerate(jobs, 1):
        lines.append(f"\n—— Job {i} ———————————————————")
        lines.append(f"Title   : {j.get('job_title', 'N/A')}")
        lines.append(f"Company : {j.get('company_name', 'N/A')}")
        lines.append(f"Location: {j.get('location', 'N/A')}")
        lines.append(f"Score   : {j.get('relevance_score', '—')}")
        kw = ', '.join(j.get('recommended_keywords', []))
        lines.append(f"Keywords: {kw if kw else '—'}")
        lines.append(f"Source  : {j.get('source', 'N/A')}")
    return '\n'.join(lines)


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

def robust_json_array_from_llm(text):
    """
    Handles multiple LLM output formats: 
    - single JSON array 
    - multiple JSON objects stacked
    - markdown code blocks
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()

    # Attempt 1: try parsing as a clean array
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Attempt 2: try stacking individual JSON objects
    matches = re.findall(r"\{.*?\}", text, re.DOTALL)
    try:
        parsed_objects = [json.loads(obj) for obj in matches]
        return parsed_objects
    except Exception as e:
        print(f"{Colors.RED}❌ Failed to parse stacked objects: {e}{Colors.RESET}")
        print(f"{Colors.YELLOW}⚠️ Raw Text Received:\n{text}{Colors.RESET}")
        return []


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
    
    # Check if the post request has the file part
    if 'file' not in request.files:
        return redirect(request.url)
    file = request.files['file']

    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path) #stores the file in local server.
        
        resume_text = read_resume(file_path) # simply read the PDF file using PyPDF2.
        session['resume_text'] = resume_text  
        job_titles = extract_job_titles(resume_text)
        session['job_titles'] = job_titles  # Store job titles in session


        return render_template('upload.html', job_titles=job_titles)

@app.route('/search', methods=['POST'])
def search_jobs_on_google():
    """Search for job postings on real job platforms using SerpAPI."""
    try:
        job_titles = session.get('job_titles', [])
        search_results = []

        # here i am using the google docking, so that my search will be efficient and also i m limiting my search space 
        # so that i can fasten the entire process as we are in a time constraint, 
        # also one can use this tool without google docking and unlimiting the number of websites
        allowed_sites = [
            "site:careers.google.com", 
            "site:jobs.apple.com", 
            "site:boards.greenhouse.io", 
            "site:jobs.lever.co",
            "site:workday.com",
            "site:smartrecruiters.com"
        ]

        for title in job_titles:
            #Google search query API - Serpapi.   
            query = f'({" OR ".join(allowed_sites)}) "{title}"'
            #Api parameters.
            search_params = {
                "q": query,
                "engine": "google",
                "google_domain": "google.com",
                "api_key": serp_api_key,
                "num": request.form.get('num', default=3, type=int) # Number of results to fetch that user can select from the form.
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
            # store empty list in session so user doesn't see "None"
            session['filtered_results'] = []
            # Render the template anyway, maybe show an error message
            return render_template('search.html', 
                                search_results=[], 
                                error_msg="No valid job listings found.")

        session['filtered_results'] = filtered_results
        return render_template('search.html', search_results=filtered_results)


    except Exception as e:
        print(f"{Colors.RED}❌ Error searching jobs on Google: {str(e)}{Colors.RESET}")
        return []
    

def pretty_scrape_block(jobs):
    lines = []
    for i, j in enumerate(jobs, 1):
        lines.append(f"\n—— Job {i} ———————————————————")
        lines.append(f"Title       : {j['job_title']}")
        lines.append(f"Company     : {j['company_name']}")
        lines.append(f"Location    : {j['location']}")
        lines.append(f"Experience  : {j['experience_level']}")
        # show the REQUIRED skills, not recommended
        skills = ', '.join(j.get('required_skills', []))
        lines.append(f"Req. Skills : {skills or '—'}")
        lines.append(f"Source      : {j['source']}")
    return '\n'.join(lines)



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
        

    for idx, item in enumerate(links, 1):
    # item is a dictionary like {"link": "https://...", "title": "...", "snippet": "..."}
        actual_url = item["link"]

        print(f"{Colors.CYAN}⏳ Scraping [{idx}/{len(links)}]: {actual_url}{Colors.RESET}")
        emit('Logs', {'message': f'⏳ Scraping [{idx}/{len(links)}]: {actual_url}'})
        
        # Executing the firecrawl API to extract the data from each links
        payload = {
            "urls": [actual_url],
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
                raw_text = fetch_visible_text_from_page(actual_url)
                if raw_text:
                    llm_result = extract_job_details_with_llm(raw_text, actual_url)
                    if llm_result:
                        all_results.append(llm_result)
                        emit('Logs', {'message': f'[{llm_result}]'})
                        emit('Logs', {'message': f'🧠 LLM successfully extracted job info from local fallback HTML.'})
                    else:
                        empty_extractions += 1
                        emit('Logs', {'message': f'⚠️ LLM could not parse fallback page [{idx}]'})
                else:
                    empty_extractions += 1
                    emit('Logs', {'message': f'⚠️ No content from local HTML scrape [{idx}]'})

        except Exception as e:
            failed_count += 1
            print(f"{Colors.RED}❌ Error scraping [{idx}]: {actual_url}\nReason: {str(e)}{Colors.RESET}")
            emit('Logs', {'message': f'❌ Error scraping [{idx}]: {actual_url}\nReason: {str(e)}'})

        # Respect Firecrawl rate limit
        time.sleep(6)

    print(f"\n{Colors.GREEN}✅ Jobs extracted: {len(all_results)}{Colors.RESET}")
    emit('Logs', {'message': f'✅ Jobs extracted: {len(all_results)}'}) 
    print(f"{Colors.YELLOW}⚠️ Fallbacks used: {fallback_used}{Colors.RESET}")
    emit('Logs', {'message': f'⚠️ Fallbacks used: {fallback_used}'})   
    print(f"{Colors.YELLOW}⚠️ Pages with no usable data: {empty_extractions}{Colors.RESET}")
    emit('Logs', {'message': f'⚠️ Pages with no usable data: {empty_extractions}'})    
    print(f"{Colors.RED}❌ Failed requests: {failed_count}{Colors.RESET}")
    emit('Logs', {'message': f'❌ Failed requests: {failed_count}'})      
    
    
    session['all_results'] = all_results
    global global_scraped_results
    global_scraped_results = all_results


    formatted = pretty_scrape_block(all_results)
    print(formatted)
    emit('Logs', {'message': formatted})


@app.route('/results', methods=['POST'])
def rank_jobs():
    logging.info(f"🔎 Request method: {request.method}")
    
    resume_text = session.get('resume_text', [])
    global global_scraped_results
    jobs = global_scraped_results
    
    logging.info(f"📦 resume_text length: {len(resume_text)}")
    logging.info(f"📊 all_results in session: {len(jobs)} jobs")
    logging.info(f"📊 Sample job: {jobs[0] if jobs else 'N/A'}")
    
    if not jobs:
        return render_template("results.html", ranked_jobs=[])
    
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
            "recommended_keywords": ["keyword1", "keyword2", "..."],
            "source:" "..."
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
        raw_output = response.choices[0].message.content
        logging.info(f"🧠 Raw LLM Response:\n{raw_output}")
        
        ranked_jobs = robust_json_array_from_llm(raw_output)
        logging.info(f"✅ Parsed {len(ranked_jobs)} ranked jobs")
        session['ranked_jobs'] = ranked_jobs
        return render_template("results.html", ranked_jobs=ranked_jobs)

    except Exception as e:
        print(f"{Colors.RED}Error ranking jobs: {str(e)}{Colors.RESET}")
        return render_template("results.html", ranked_jobs=[])


if __name__ == "__main__":
    app.run(debug=True)
    
    
# /upload
# /search
# start_scraping
# /results
    


