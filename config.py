import os
from dotenv import load_dotenv

load_dotenv()

# --- DO NOT MODIFY THE BELOW SECTION ---

# =================================================================
# 1. CORE SYSTEM CONFIGURATION (Do not Modify)
# =================================================================

SUPABASE_URL: str = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

SUPABASE_TABLE_NAME: str = "jobs"
SUPABASE_CUSTOMIZED_RESUMES_TABLE_NAME = "customized_resumes"

SUPABASE_STORAGE_BUCKET = "personalized_resumes"
SUPABASE_RESUME_STORAGE_BUCKET = "resumes"

SUPABASE_BASE_RESUME_TABLE_NAME = "base_resume"
BASE_RESUME_PATH = "resume.json"

# API keys — set only the key(s) needed for your chosen provider.
LLM_API_KEY = (
    os.environ.get("LLM_API_KEY")
    or os.environ.get("GEMINI_API_KEY")
    or os.environ.get("GEMINI_FIRST_API_KEY")
)


# =================================================================
# 2. USER PREFERENCES (Editable)
# =================================================================

# --- LLM Settings ---

# Use any model supported by LiteLLM
# (gemini, openai/gpt-4o-mini, groq/llama-3.3-70b-versatile)
#
# Full list of supported models & naming:
# https://docs.litellm.ai/docs/providers

LLM_MODEL = "gemini"


# --- LinkedIn Search Configuration ---

LINKEDIN_SEARCH_QUERIES = [
    "software developer",
    "software developer 2",
    "software developer II",
    "software",
    "software engineer",
    "software engineer 2",
    "Java software developer",
    "Java",
    "Spring",
    "Spring Boot",
    "Kafka",
    "SDE",
    "SDE2",
    "Redis",
    "Backend",
    "Backend Developer",
    "Backend Software Engineer",
    "Full Stack software developer",
    "Full Stack",
    "Engineer",
    "DSA",
    "System Design",
    "Data Structures & Algorithms",
    "Data Structures",
    "Algorithms",
]


# -----------------------------------------------------------------
# LinkedIn Locations
#
# Format:
#     "Location Name": LinkedIn Geo ID
#
# You can add/remove locations without changing scraper.py.
# -----------------------------------------------------------------

LINKEDIN_LOCATIONS = {
    "Hyderabad": 105556991,
    "Bangalore": 105214831,
    "Pune": 114806696,
    "Mumbai": 106164952,
    "Noida": 104569687,
    "Chennai": 106888327,
    "Delhi": 106187582,
}


# -----------------------------------------------------------------
# LinkedIn Job Type
#
# F = Full-time
# C = Contract
# P = Part-time
# T = Temporary
# I = Internship
# -----------------------------------------------------------------

LINKEDIN_JOB_TYPE = "F"


# -----------------------------------------------------------------
# LinkedIn Job Posting Date Filters
#
# r86400  = Past 24 hours
# r604800 = Past week
# -----------------------------------------------------------------

LINKEDIN_JOB_POSTING_DATES = [
    "r86400",
    "r604800",
]


# -----------------------------------------------------------------
# LinkedIn Workplace Type
#
# 1 = Onsite
# 2 = Remote
# 3 = Hybrid
# -----------------------------------------------------------------

LINKEDIN_WORK_TYPES = [
    1,
    2,
    3,
]


# --- CareersFuture Configuration ---
# Kept for compatibility with the existing scraper.
# Currently disabled because SCRAPING_SOURCES contains only "linkedin".

CAREERS_FUTURE_SEARCH_QUERIES = [
    "IT Support",
    "Full Stack Web Developer",
    "Application Support",
    "Cybersecurity Analyst",
    "fresher developer",
]

CAREERS_FUTURE_SEARCH_CATEGORIES = [
    "Information Technology"
]

CAREERS_FUTURE_SEARCH_EMPLOYMENT_TYPES = [
    "Full Time"
]


# --- Processing Limits ---

SCRAPING_SOURCES = [
    "linkedin"
]  # "linkedin", "careers_future"

JOBS_TO_SCORE_PER_RUN = 5
JOBS_TO_CUSTOMIZE_PER_RUN = 1

MAX_JOBS_PER_SEARCH = {
    "linkedin": 2,
    "careers_future": 10,
}


# =================================================================
# 3. ADVANCED SYSTEM SETTINGS (Modify with Caution)
# =================================================================

LLM_MAX_RPM = 10
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 10
LLM_DAILY_REQUEST_BUDGET = 0
LLM_REQUEST_DELAY_SECONDS = 8


# -----------------------------------------------------------------
# LinkedIn Pagination
#
# LinkedIn pagination uses:
#   start=0
#   start=10
#   start=20
#   ...
#
# With the current scraper logic:
#
#   LINKEDIN_MAX_START = 1
#
# means only start=0 is requested.
#
# Use 10 for two pages:
#   start=0
#   start=10
# -----------------------------------------------------------------

LINKEDIN_MAX_START = 1


# -----------------------------------------------------------------
# HTTP Configuration
# -----------------------------------------------------------------

REQUEST_TIMEOUT = 30

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 15


# -----------------------------------------------------------------
# Job Lifecycle Configuration
# -----------------------------------------------------------------

JOB_EXPIRY_DAYS = 30
JOB_CHECK_DAYS = 3
JOB_DELETION_DAYS = 60
JOB_CHECK_LIMIT = 50

ACTIVE_CHECK_TIMEOUT = 20
ACTIVE_CHECK_MAX_RETRIES = 2
ACTIVE_CHECK_RETRY_DELAY = 10
