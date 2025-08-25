# JobPilot 🚀

An AI-powered job search and resume optimization tool that helps job seekers find relevant positions and optimize their resumes for ATS (Applicant Tracking System) compatibility.

## 🌟 Features

- **Resume Analysis**: Upload PDF resumes and extract relevant job titles using AI
- **Smart Job Search**: Automatically search for jobs on major platforms (Google Careers, Apple Jobs, Greenhouse, Lever, etc.)
- **Job Scraping**: Extract detailed job information from job posting pages
- **AI-Powered Ranking**: Rank jobs by relevance to your resume with scoring out of 10
- **ATS Optimization**: Get keyword recommendations to improve resume ATS compatibility
- **Real-time Updates**: Live progress tracking during job scraping process

## 🛠️ Tech Stack

- **Backend**: Flask (Python)
- **AI/ML**: OpenAI API (via OpenRouter), DeepSeek models
- **Web Scraping**: Firecrawl API, BeautifulSoup, SerpAPI
- **PDF Processing**: PyPDF2
- **Real-time Communication**: Flask-SocketIO
- **Frontend**: HTML templates with real-time updates

## 📋 Prerequisites

- Python 3.7+
- Valid API keys for:
  - OpenRouter/OpenAI API
  - Firecrawl API
  - SerpAPI (Google Search)

## 🚀 Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd JobPilot
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**
   
   Create a `.env` file in the root directory:
   ```env
   OPENAI_API_KEY=your_openrouter_api_key
   FIRECRAWL_API_KEY=your_firecrawl_api_key
   SERP_API_KEY=your_serpapi_key
   ```

4. **Create uploads directory**
   ```bash
   mkdir uploads
   ```

## 📦 Dependencies

Create a `requirements.txt` file with these dependencies:
```
Flask==2.3.3
Flask-SocketIO==5.3.6
openai==1.3.5
requests==2.31.0
PyPDF2==3.0.1
beautifulsoup4==4.12.2
serpapi==0.1.5
firecrawl-py==0.0.16
python-dotenv==1.0.0
werkzeug==2.3.7
```

## 🎯 Usage

1. **Start the application**
   ```bash
   python app.py
   ```

2. **Access the web interface**
   - Open your browser and go to `http://localhost:5000`

3. **Upload your resume**
   - Upload a PDF resume on the home page
   - The AI will extract relevant job titles from your resume

4. **Search for jobs**
   - Click "Search Jobs" to find relevant positions
   - Specify the number of results per job title (default: 3)

5. **Scrape job details**
   - Start the scraping process to extract detailed job information
   - Monitor real-time progress in the console

6. **View ranked results**
   - Get AI-powered job rankings with relevance scores
   - Receive ATS keyword recommendations for each job

## 🏗️ Project Structure

```
JobPilot/
├── app.py                 # Main Flask application
├── templates/            
│   ├── index.html        # Home page
│   ├── upload.html       # Resume upload results
│   ├── search.html       # Job search results
│   ├── console.html      # Scraping progress console
│   └── results.html      # Final ranked results
├── uploads/              # Uploaded resume storage
├── .env                  # Environment variables
└── README.md            # Project documentation
```

## 🔧 API Configuration

### OpenRouter API
- Used for AI-powered resume analysis and job ranking
- Models used: `deepseek/deepseek-r1:free`, `deepseek/deepseek-chat`, `mistralai/mistral-7b-instruct`

### Firecrawl API
- Primary method for job posting extraction
- Includes automatic fallback to local HTML scraping + LLM analysis

### SerpAPI
- Google search integration for finding job postings
- Searches only on verified job platforms for quality results

## 🎨 Key Features Explained

### Resume Analysis
- Extracts text from PDF resumes using PyPDF2
- Uses AI to identify top 3 relevant job titles
- Stores resume content for later job matching

### Smart Job Search
- Searches only on trusted job platforms:
  - careers.google.com
  - jobs.apple.com
  - boards.greenhouse.io
  - jobs.lever.co
  - workday.com
  - smartrecruiters.com

### Job Scraping & Extraction
- Primary: Firecrawl API with structured prompts
- Fallback: Local HTML scraping + LLM analysis
- Rate limiting to respect API constraints
- Real-time progress updates via WebSocket

### AI-Powered Job Ranking
- Compares job requirements with resume content
- Provides relevance score (1-10) with explanations
- Suggests ATS-friendly keywords missing from resume

## 🚨 Error Handling

The application includes comprehensive error handling:
- API failures with automatic fallbacks
- PDF reading errors
- Network timeout handling
- Invalid job site filtering
- JSON parsing error recovery

## 🔒 Security

- Secure file uploads with filename sanitization
- Environment variable protection for API keys
- Session-based data storage
- Input validation and sanitization

## 📊 Performance

- Asynchronous job scraping with progress tracking
- Rate limiting to respect API constraints (6-second delays)
- Efficient PDF processing
- Optimized search queries for better results

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This tool is for educational and personal use. Please respect the terms of service of job platforms and APIs used. Ensure you have proper API quotas and permissions before running extensive scraping operations.

## 🆘 Troubleshooting

### Common Issues

1. **API Key Errors**
   - Ensure all API keys are properly set in `.env` file
   - Check API key validity and quotas

2. **PDF Reading Issues**
   - Ensure PDF files are not password protected
   - Check file upload size limits

3. **Scraping Failures**
   - Some job sites may block scraping attempts
   - Fallback methods will be used automatically

4. **No Job Results**
   - Verify SerpAPI key and quota
   - Check if job sites are accessible
   - Try different search terms

## 📞 Support

For issues and questions, please open an issue in the GitHub repository.

---

**Built with ❤️ for job seekers everywhere**
