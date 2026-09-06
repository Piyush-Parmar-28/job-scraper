import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import random
import logging
import config
import user_agents
import supabase_utils
from markdownify import markdownify as md
import json


# --- Setup Logging ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# =================================================================
# Utility Functions
# =================================================================

def convert_html_to_markdown(html: str) -> str | None:
    """
    Convert HTML to clean Markdown using BeautifulSoup
    and markdownify.

    No LLM API calls are made.
    """

    if not html or not html.strip():
        logging.info(
            "Received empty HTML for Markdown conversion, "
            "returning empty string."
        )
        return ""

    try:
        # Clean the HTML
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup.find_all(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "iframe",
                "noscript",
            ]
        ):
            tag.decompose()

        cleaned_html = str(soup)

        # Convert cleaned HTML to Markdown
        markdown_text = md(
            cleaned_html,
            heading_style="ATX",
            bullets="-",
            strip=["img"],
        )

        # Clean up excessive blank lines
        lines = markdown_text.splitlines()

        cleaned_lines = []
        prev_blank = False

        for line in lines:

            if not line.strip():

                if not prev_blank:
                    cleaned_lines.append("")

                prev_blank = True

            else:

                cleaned_lines.append(line)
                prev_blank = False

        markdown_text = "\n".join(cleaned_lines).strip()

        logging.info(
            "Successfully converted HTML to Markdown."
        )

        return markdown_text if markdown_text else ""

    except Exception as e:

        logging.error(
            f"Error during HTML to Markdown conversion: {e}"
        )

        return None


def _get_careers_future_job_company_name(
    job_item: dict
) -> str | None:
    """Helper to extract company name, preferring hiringCompany."""

    if not isinstance(job_item, dict):
        return None

    hiring_company = job_item.get("hiringCompany")

    if (
        isinstance(hiring_company, dict)
        and hiring_company.get("name")
    ):
        return hiring_company["name"]

    posted_company = job_item.get("postedCompany")

    if (
        isinstance(posted_company, dict)
        and posted_company.get("name")
    ):
        return posted_company["name"]

    return None


# =================================================================
# LinkedIn Scraping Logic
# =================================================================

def _fetch_linkedin_job_ids(
    search_query: str,
    location: str,
    geo_id: int,
    posting_date: str,
    work_type: int
) -> list:
    """
    Fetch job IDs from LinkedIn guest search results.

    Search parameters:
        - search query
        - location
        - geo ID
        - posting date
        - job type
        - workplace type

    Pagination is controlled by LINKEDIN_MAX_START.
    """

    job_ids_list = []

    start = 0
    max_start = config.LINKEDIN_MAX_START

    search_url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/"
        "seeMoreJobPostings/search"
    )

    logging.info(
        "--- Starting Phase 1: Scraping LinkedIn Job IDs "
        f"(Max Start: {max_start}) ---"
    )

    while start <= max_start:

        # IMPORTANT:
        #
        # Use requests' params argument rather than manually
        # constructing the query string.
        #
        # This correctly handles queries such as:
        #
        #   Data Structures & Algorithms
        #
        # because '&' will be URL encoded correctly.

        params = {
            "keywords": search_query,
            "location": location,
            "geoId": geo_id,
            "f_TPR": posting_date,
            "f_JT": config.LINKEDIN_JOB_TYPE,
            "f_WT": work_type,
            "start": start,
        }

        # Delay between pagination requests
        if start > 0:

            sleep_time = random.uniform(
                5.0,
                15.0
            )

            logging.info(
                f"Waiting for {sleep_time:.2f} seconds "
                "before next LinkedIn results request..."
            )

            time.sleep(sleep_time)

        user_agent = random.choice(
            user_agents.USER_AGENTS
        )

        headers = {
            "User-Agent": user_agent
        }

        logging.info(
            f"Using User-Agent: {user_agent}"
        )

        logging.info(
            "Scraping LinkedIn search: "
            f"query='{search_query}', "
            f"location='{location}', "
            f"geo_id={geo_id}, "
            f"posting_date='{posting_date}', "
            f"work_type={work_type}, "
            f"start={start}"
        )

        res = None
        retries = 0

        # ---------------------------------------------------------
        # Request with retry handling
        # ---------------------------------------------------------

        while retries <= config.MAX_RETRIES:

            try:

                res = requests.get(
                    search_url,
                    params=params,
                    headers=headers,
                    timeout=config.REQUEST_TIMEOUT,
                )

                res.raise_for_status()

                break

            except requests.exceptions.HTTPError as e:

                status_code = (
                    e.response.status_code
                    if e.response is not None
                    else None
                )

                if (
                    status_code == 429
                    and retries < config.MAX_RETRIES
                ):

                    retries += 1

                    wait_time = (
                        config.RETRY_DELAY_SECONDS
                        + random.uniform(0, 5)
                    )

                    logging.warning(
                        "Error 429: Too Many Requests. "
                        f"Retrying attempt "
                        f"{retries}/{config.MAX_RETRIES} "
                        f"after {wait_time:.2f} seconds..."
                    )

                    time.sleep(wait_time)

                    user_agent = random.choice(
                        user_agents.USER_AGENTS
                    )

                    headers = {
                        "User-Agent": user_agent
                    }

                    logging.info(
                        "Retrying with new User-Agent: "
                        f"{user_agent}"
                    )

                    continue

                logging.error(
                    "HTTP Error fetching LinkedIn "
                    f"search results page: {e}"
                )

                res = None
                break

            except requests.exceptions.RequestException as e:

                logging.error(
                    "Request Exception fetching LinkedIn "
                    f"search results page: {e}"
                )

                res = None
                break

        # ---------------------------------------------------------
        # Request failed
        # ---------------------------------------------------------

        if res is None:

            logging.error(
                "Failed to fetch LinkedIn search for "
                f"query='{search_query}', "
                f"location='{location}', "
                f"posting_date='{posting_date}', "
                f"work_type={work_type}, "
                f"start={start} "
                f"after {retries} retries. "
                "Stopping pagination for this combination."
            )

            break

        if not res.text:

            logging.info(
                f"Received empty response text at start={start}, "
                "stopping."
            )

            break

        # ---------------------------------------------------------
        # Parse search results
        # ---------------------------------------------------------

        soup = BeautifulSoup(
            res.text,
            "html.parser"
        )

        all_jobs_on_this_page = soup.find_all("li")

        if not all_jobs_on_this_page:

            logging.info(
                f"No job listings ('li' elements) found "
                f"on page at start={start}, stopping."
            )

            break

        logging.info(
            f"Found {len(all_jobs_on_this_page)} potential "
            "job elements on this page."
        )

        jobs_found_this_iteration = 0

        for job_element in all_jobs_on_this_page:

            base_card = job_element.find(
                "div",
                {"class": "base-card"}
            )

            job_urn = (
                base_card.get("data-entity-urn")
                if base_card
                else None
            )

            if job_urn and "jobPosting:" in job_urn:

                try:

                    job_id = job_urn.split(":")[3]

                    if job_id not in job_ids_list:

                        job_ids_list.append(job_id)

                        jobs_found_this_iteration += 1

                except IndexError:

                    logging.warning(
                        "Could not parse job ID from URN: "
                        f"{job_urn}"
                    )

        logging.info(
            f"Added {jobs_found_this_iteration} unique "
            "job IDs from this page."
        )

        # If LinkedIn returned list items but none contained
        # a new job ID, there is no reason to continue.
        if jobs_found_this_iteration == 0:

            logging.info(
                "Found list items but no new job IDs extracted, "
                "potentially end of relevant results or parsing issue."
            )

            break

        # LinkedIn pagination increments by 10
        start += 10

    logging.info(
        "--- Finished Phase 1: Found "
        f"{len(job_ids_list)} unique job IDs "
        "during scraping ---"
    )

    return job_ids_list


# =================================================================
# LinkedIn Job Details
# =================================================================

def _fetch_linkedin_job_details(
    job_id: str
) -> dict | None:
    """
    Fetch detailed information for a single LinkedIn job ID.
    """

    job_detail_url = (
        "https://www.linkedin.com/jobs-guest/jobs/api/"
        f"jobPosting/{job_id}"
    )

    logging.info(
        f"Preparing to fetch details for job ID: {job_id}"
    )

    # Delay before fetching details
    sleep_time = random.uniform(
        3.0,
        10.0
    )

    logging.info(
        f"Waiting for {sleep_time:.2f} seconds "
        "before fetching details..."
    )

    time.sleep(sleep_time)

    user_agent = random.choice(
        user_agents.USER_AGENTS
    )

    headers = {
        "User-Agent": user_agent
    }

    logging.info(
        f"Using User-Agent for details: {user_agent}"
    )

    logging.info(
        f"Fetching details from: {job_detail_url}"
    )

    resp = None
    retries = 0

    while retries <= config.MAX_RETRIES:

        try:

            resp = requests.get(
                job_detail_url,
                headers=headers,
                timeout=config.REQUEST_TIMEOUT,
            )

            resp.raise_for_status()

            break

        except requests.exceptions.HTTPError as e:

            status_code = (
                e.response.status_code
                if e.response is not None
                else None
            )

            if (
                status_code == 429
                and retries < config.MAX_RETRIES
            ):

                retries += 1

                wait_time = (
                    config.RETRY_DELAY_SECONDS
                    + random.uniform(0, 5)
                )

                logging.warning(
                    f"Error 429 for job ID {job_id}. "
                    f"Retrying attempt "
                    f"{retries}/{config.MAX_RETRIES} "
                    f"after {wait_time:.2f} seconds..."
                )

                time.sleep(wait_time)

                user_agent = random.choice(
                    user_agents.USER_AGENTS
                )

                headers = {
                    "User-Agent": user_agent
                }

                logging.info(
                    f"Retrying job {job_id} "
                    f"with new User-Agent: {user_agent}"
                )

                continue

            logging.error(
                f"HTTP Error fetching details for "
                f"job ID {job_id}: {e}"
            )

            return None

        except requests.exceptions.RequestException as e:

            logging.error(
                f"Request Exception fetching details "
                f"for job ID {job_id}: {e}"
            )

            return None

    if resp is None:

        logging.error(
            f"Failed to fetch details for job ID "
            f"{job_id} after {retries} retries "
            "(unexpected state)."
        )

        return None

    # -------------------------------------------------------------
    # Parse job details
    # -------------------------------------------------------------

    try:

        soup = BeautifulSoup(
            resp.text,
            "html.parser"
        )

        job_details = {
            "job_id": job_id
        }

        # ---------------------------------------------------------
        # Extract Company
        # ---------------------------------------------------------

        try:

            top_card = soup.find(
                "div",
                {"class": "top-card-layout__card"}
            )

            company_img = (
                top_card.find("a").find("img")
                if top_card
                else None
            )

            if company_img:

                company_alt = company_img.get("alt")

                if company_alt:
                    job_details["company"] = (
                        company_alt.strip()
                    )

            if not job_details.get("company"):

                company_link = soup.find(
                    "a",
                    {"class": "topcard__org-name-link"}
                )

                if company_link:

                    job_details["company"] = (
                        company_link.text.strip()
                    )

                else:

                    sub_title_span = soup.find(
                        "span",
                        {"class": "topcard__flavor"}
                    )

                    if sub_title_span:

                        job_details["company"] = (
                            sub_title_span.text.strip()
                        )

            if not job_details.get("company"):

                job_details["company"] = None

                print(
                    "Warning: Could not extract company "
                    f"for job ID {job_id}"
                )

        except Exception as e:

            print(
                "Error extracting company for "
                f"job ID {job_id}: {e}"
            )

            job_details["company"] = None

        # ---------------------------------------------------------
        # Extract Job Title
        # ---------------------------------------------------------

        try:

            entity_info = soup.find(
                "div",
                {"class": "top-card-layout__entity-info"}
            )

            title_link = (
                entity_info.find("a")
                if entity_info
                else None
            )

            job_details["job_title"] = (
                title_link.text.strip()
                if title_link
                else None
            )

            if not job_details["job_title"]:

                title_h1 = soup.find(
                    "h1",
                    {"class": "top-card-layout__title"}
                )

                if title_h1:

                    job_details["job_title"] = (
                        title_h1.text.strip()
                    )

        except Exception as e:

            print(
                "Error extracting job title for "
                f"job ID {job_id}: {e}"
            )

            job_details["job_title"] = None

        # ---------------------------------------------------------
        # Extract Seniority Level
        # ---------------------------------------------------------

        try:

            criteria_list = soup.find(
                "ul",
                {
                    "class":
                    "description__job-criteria-list"
                }
            )

            criteria_items = (
                criteria_list.find_all("li")
                if criteria_list
                else []
            )

            job_details["level"] = None

            for item in criteria_items:

                header = item.find(
                    "h3",
                    {
                        "class":
                        "description__job-criteria-subheader"
                    }
                )

                if (
                    header
                    and "Seniority level"
                    in header.text
                ):

                    level_text = item.find(
                        "span",
                        {
                            "class":
                            "description__job-criteria-text"
                        }
                    )

                    if level_text:

                        job_details["level"] = (
                            level_text.text.strip()
                        )

                        break

        except Exception as e:

            print(
                "Error extracting seniority level "
                f"for job ID {job_id}: {e}"
            )

            job_details["level"] = None

        # ---------------------------------------------------------
        # Extract Location
        # ---------------------------------------------------------

        try:

            location_span = soup.find(
                "span",
                {
                    "class":
                    "topcard__flavor topcard__flavor--bullet"
                }
            )

            if location_span:

                job_details["location"] = (
                    location_span.text.strip()
                )

            else:

                subtitle_div = soup.find(
                    "div",
                    {
                        "class":
                        "topcard__flavor-row"
                    }
                )

                if subtitle_div:

                    location_span_fallback = (
                        subtitle_div.find(
                            "span",
                            {
                                "class":
                                "topcard__flavor"
                            }
                        )
                    )

                    if location_span_fallback:

                        job_details["location"] = (
                            location_span_fallback
                            .text
                            .strip()
                        )

            if not job_details.get("location"):

                job_details["location"] = None

                print(
                    "Warning: Could not extract location "
                    f"for job ID {job_id}"
                )

        except Exception as e:

            print(
                "Error extracting location for "
                f"job ID {job_id}: {e}"
            )

            job_details["location"] = None

        # ---------------------------------------------------------
        # Extract Description
        # ---------------------------------------------------------

        description_html = ""

        try:

            description_div = soup.find(
                "div",
                {
                    "class":
                    "show-more-less-html__markup"
                }
            )

            if description_div:

                description_html = str(
                    description_div
                )

            else:

                logging.warning(
                    "Could not find description div "
                    f"for job ID {job_id}"
                )

        except Exception as e:

            logging.error(
                "Error extracting description HTML "
                f"for job ID {job_id}: {e}"
            )

            description_html = ""

        if description_html.strip():

            job_details["description"] = (
                convert_html_to_markdown(
                    description_html
                )
            )

        else:

            job_details["description"] = None

            logging.warning(
                "Description HTML was empty for "
                f"job ID {job_id}. "
                "Skipping conversion."
            )

        # ---------------------------------------------------------
        # Provider
        # ---------------------------------------------------------

        job_details["provider"] = "linkedin"

        return job_details

    except Exception as e:

        logging.error(
            "General Error processing details for "
            f"job ID {job_id} after successful fetch: {e}"
        )

        return None


# =================================================================
# LinkedIn Query Processing
# =================================================================

def process_linkedin_query(
    search_query: str,
    location: str,
    geo_id: int,
    posting_date: str,
    work_type: int,
    limit: int = None
) -> list:
    """
    Orchestrates LinkedIn scraping and detail fetching
    for one search combination.

    Flow:

        1. Scrape LinkedIn job IDs.
        2. Remove duplicate IDs while preserving order.
        3. Check IDs against Supabase.
        4. Fetch details only for new jobs.
        5. Return new job details.
    """

    scraped_job_ids = _fetch_linkedin_job_ids(
        search_query=search_query,
        location=location,
        geo_id=geo_id,
        posting_date=posting_date,
        work_type=work_type,
    )

    if not scraped_job_ids:

        logging.info(
            "No job IDs found in Phase 1. "
            "Skipping detail fetching."
        )

        return []

    # Preserve LinkedIn result order while removing duplicates.
    unique_linkedin_job_ids = list(
        dict.fromkeys(scraped_job_ids)
    )

    logging.info(
        f"Found {len(scraped_job_ids)} raw job IDs, "
        f"{len(unique_linkedin_job_ids)} unique IDs "
        "after scraping."
    )

    # -------------------------------------------------------------
    # Check Supabase
    # -------------------------------------------------------------

    logging.info(
        "\n--- Starting Filtering Step: "
        "Checking against Supabase ---"
    )

    job_ids_set, company_title_set = (
        supabase_utils.get_existing_jobs_from_supabase()
    )

    new_job_ids_to_process = [
        str(job_id)
        for job_id in unique_linkedin_job_ids
        if str(job_id) not in job_ids_set
    ]

    logging.info(
        f"Found {len(unique_linkedin_job_ids)} "
        "unique scraped IDs."
    )

    logging.info(
        f"Found {len(job_ids_set)} existing IDs "
        "in Supabase."
    )

    logging.info(
        f"Identified {len(new_job_ids_to_process)} "
        "new job IDs to fetch details for."
    )

    if not new_job_ids_to_process:

        logging.info(
            "No new job IDs to process after filtering."
        )

        return []

    # -------------------------------------------------------------
    # Apply per-search limit
    # -------------------------------------------------------------

    if (
        limit is not None
        and len(new_job_ids_to_process) > limit
    ):

        logging.info(
            f"Truncating new_job_ids_to_process "
            f"from {len(new_job_ids_to_process)} "
            f"to {limit} to stay within source limit."
        )

        new_job_ids_to_process = (
            new_job_ids_to_process[:limit]
        )

    # -------------------------------------------------------------
    # Fetch details
    # -------------------------------------------------------------

    logging.info(
        "\n--- Starting Phase 2: Fetching Job Details "
        f"for {len(new_job_ids_to_process)} New IDs ---"
    )

    detailed_new_jobs = []
    processed_count = 0

    for job_id in new_job_ids_to_process:

        details = _fetch_linkedin_job_details(
            job_id
        )

        if details:

            description = details.get(
                "description"
            )

            if description and description.strip():

                if (
                    "job_id" in details
                    and details["job_id"] is not None
                ):

                    detailed_new_jobs.append(
                        details
                    )

                    processed_count += 1

                else:

                    logging.warning(
                        f"Fetched details for {job_id} "
                        "but missing 'job_id' key. "
                        "Skipping."
                    )

            else:

                logging.warning(
                    f"Skipping job ID {job_id} "
                    "due to missing or empty description."
                )

        else:

            logging.warning(
                f"Skipping job ID {job_id} "
                "as detail fetching failed "
                "or returned no data."
            )

    logging.info(
        "--- Finished Phase 2: Successfully fetched "
        f"details for {processed_count} new job(s) ---"
    )

    return detailed_new_jobs


# =================================================================
# CareersFuture Scraping Logic
# =================================================================

def _fetch_careers_future_jobs(
    search_query: str
) -> list:
    """
    Fetches job items from CareersFuture based on
    the provided search query.
    """

    careers_future_suggestions_api_url = (
        "https://api.mycareersfuture.gov.sg/"
        "v2/skills/suggestions"
    )

    careers_future_search_api_base_url = (
        "https://api.mycareersfuture.gov.sg/"
        "v2/search"
    )

    skillUuids = []

    # -------------------------------------------------------------
    # 1. Get Skill Suggestions
    # -------------------------------------------------------------

    skills_suggestions_payload = {
        "jobTitle": search_query
    }

    try:

        logging.info(
            f"Fetching skill suggestions for query: "
            f"'{search_query}' from "
            f"{careers_future_suggestions_api_url}"
        )

        skills_suggestions_response = requests.post(
            careers_future_suggestions_api_url,
            data=skills_suggestions_payload,
            timeout=config.REQUEST_TIMEOUT
        )

        skills_suggestions_response.raise_for_status()

        skills_data = (
            skills_suggestions_response.json()
        )

        skills_list = skills_data.get(
            "skills",
            []
        )

        skillUuids = [
            skill_dict["uuid"]
            for skill_dict in skills_list
            if "uuid" in skill_dict
        ]

        logging.info(
            f"Successfully retrieved "
            f"{len(skillUuids)} skill UUIDs "
            f"for '{search_query}'."
        )

        if not skillUuids:

            logging.warning(
                f"No skill UUIDs found for query "
                f"'{search_query}'. Job search will "
                "proceed without specific skill filtering."
            )

    except requests.exceptions.HTTPError as http_err:

        status_code = (
            http_err.response.status_code
            if http_err.response is not None
            else "N/A"
        )

        response_text = (
            http_err.response.text
            if http_err.response is not None
            else "N/A"
        )

        logging.error(
            "HTTP error during skill suggestions: "
            f"{http_err} - Status: {status_code}"
        )

        logging.debug(
            "Skill suggestions error response "
            f"content: {response_text[:500]}"
        )

        return []

    except requests.exceptions.RequestException as req_err:

        logging.error(
            "Request exception during skill suggestions: "
            f"{req_err}"
        )

        return []

    except json.JSONDecodeError:

        content_for_log = (
            skills_suggestions_response.text
            if (
                "skills_suggestions_response"
                in locals()
                and skills_suggestions_response
            )
            else "N/A"
        )

        logging.error(
            "Could not decode JSON response for "
            "skill suggestions. Content: "
            f"{content_for_log[:500]}"
        )

        return []

    # -------------------------------------------------------------
    # 2. Search for Jobs and Handle Pagination
    # -------------------------------------------------------------

    all_job_items = []
    total_api_calls_for_search = 0

    current_search_url = (
        f"{careers_future_search_api_base_url}"
        "?limit=100&page=0"
    )

    search_payload = {
        "sessionId": "",
        "search": search_query,
        "categories": (
            config.CAREERS_FUTURE_SEARCH_CATEGORIES
        ),
        "employmentTypes": (
            config.CAREERS_FUTURE_SEARCH_EMPLOYMENT_TYPES
        ),
        "postingCompany": [],
        "sortBy": ["new_posting_date"],
        "skillUuids": skillUuids,
    }

    try:

        while current_search_url:

            total_api_calls_for_search += 1

            logging.info(
                f"Job search API call "
                f"{total_api_calls_for_search}: "
                f"POST to {current_search_url}"
            )

            search_response = requests.post(
                current_search_url,
                json=search_payload
            )

            search_response.raise_for_status()

            search_results_data = (
                search_response.json()
            )

            current_page_jobs = (
                search_results_data.get(
                    "results",
                    []
                )
            )

            all_job_items.extend(
                current_page_jobs
            )

            logging.info(
                f"Retrieved {len(current_page_jobs)} "
                "job items from this page. "
                f"Total items collected: "
                f"{len(all_job_items)}."
            )

            if (
                "total" in search_results_data
                and total_api_calls_for_search == 1
            ):

                logging.info(
                    "API reports total potential jobs "
                    "matching criteria: "
                    f"{search_results_data['total']}"
                )

            next_page_link_info = (
                search_results_data
                .get("_links", {})
                .get("next", {})
            )

            current_search_url = (
                next_page_link_info.get("href")
                if next_page_link_info
                else None
            )

            if current_search_url:

                logging.debug(
                    "Next page URL for job search: "
                    f"{current_search_url}"
                )

            else:

                logging.info(
                    "No more job pages to fetch."
                )

        logging.info(
            "Completed job search. Total API calls "
            "made for search: "
            f"{total_api_calls_for_search}."
        )

    except requests.exceptions.HTTPError as http_err:

        status_code = (
            http_err.response.status_code
            if http_err.response is not None
            else "N/A"
        )

        response_text = (
            http_err.response.text
            if http_err.response is not None
            else "N/A"
        )

        logging.error(
            f"HTTP error during job search: "
            f"{http_err} - Status: {status_code}"
        )

        logging.debug(
            "Job search error response content: "
            f"{response_text[:500]}"
        )

    except requests.exceptions.RequestException as req_err:

        logging.error(
            "Request exception during job search: "
            f"{req_err}"
        )

    except json.JSONDecodeError:

        content_for_log = (
            search_response.text
            if (
                "search_response" in locals()
                and search_response
            )
            else "N/A"
        )

        logging.error(
            "Could not decode JSON response during "
            "job search. Content: "
            f"{content_for_log[:500]}"
        )

    # -------------------------------------------------------------
    # 3. Return all collected job items
    # -------------------------------------------------------------

    if not all_job_items:

        logging.info(
            f"No job items were collected for query "
            f"'{search_query}'."
        )

        return []

    logging.info(
        f"Returning {len(all_job_items)} total job "
        f"items for query '{search_query}'."
    )

    return all_job_items


# =================================================================
# CareersFuture Job Details
# =================================================================

def _fetch_careers_future_job_details(
    job_id: str
) -> dict | None:
    """
    Fetch job details from CareersFuture.
    """

    if not job_id:

        logging.warning(
            "Job ID is missing or empty. "
            "Cannot fetch details."
        )

        return None

    api_url = (
        "https://api.mycareersfuture.gov.sg/"
        f"v2/jobs/{job_id}"
    )

    logging.info(
        f"Attempting to fetch job details for ID: "
        f"{job_id} from URL: {api_url}"
    )

    try:

        response = requests.get(
            api_url,
            timeout=config.REQUEST_TIMEOUT
        )

        response.raise_for_status()

        job_data = response.json()

        logging.info(
            f"Successfully fetched and parsed job "
            f"details for ID: {job_id}"
        )

        raw_description_html = (
            job_data.get("description", "")
        )

        markdown_description = None

        if raw_description_html.strip():

            markdown_description = (
                convert_html_to_markdown(
                    raw_description_html
                )
            )

        else:

            logging.warning(
                "Raw description was empty for "
                f"Careers Future job ID {job_id}. "
                "Skipping conversion."
            )

        job_details = {
            "job_id": job_data.get("uuid"),
            "company": (
                _get_careers_future_job_company_name(
                    job_data
                )
            ),
            "job_title": job_data.get("title"),
            "location": "Singapore",
            "level": (
                job_data.get(
                    "positionLevels",
                    [
                        {
                            "position":
                            "Not applicable"
                        }
                    ]
                )[0].get(
                    "position",
                    "Not applicable"
                )
            ),
            "provider": "careers_future",
            "description": markdown_description,
            "posted_at": (
                job_data
                .get("metadata", {})
                .get("createdAt", "")
            ),
        }

        return job_details

    except requests.exceptions.HTTPError as http_err:

        status_code = (
            http_err.response.status_code
            if http_err.response is not None
            else "N/A"
        )

        response_text = (
            http_err.response.text
            if http_err.response is not None
            else "N/A"
        )

        if status_code == 404:

            logging.warning(
                "Job details not found (404) for "
                f"ID: {job_id} at {api_url}."
            )

        else:

            logging.error(
                "HTTP error occurred while fetching "
                f"job details for ID '{job_id}': "
                f"{http_err} - Status: {status_code}"
            )

            logging.debug(
                "Error response content: "
                f"{response_text[:500]}"
            )

    except requests.exceptions.ConnectionError as conn_err:

        logging.error(
            "Connection error occurred while fetching "
            f"job details for ID '{job_id}': "
            f"{conn_err}"
        )

    except requests.exceptions.Timeout as timeout_err:

        logging.error(
            "Timeout error occurred while fetching "
            f"job details for ID '{job_id}': "
            f"{timeout_err}"
        )

    except requests.exceptions.RequestException as req_err:

        logging.error(
            "An error occurred during the request for "
            f"job details for ID '{job_id}': "
            f"{req_err}"
        )

    except json.JSONDecodeError:

        content_for_log = (
            response.text
            if (
                "response" in locals()
                and response
            )
            else "N/A"
        )

        logging.error(
            "Failed to decode JSON response for "
            f"job details for ID '{job_id}'. "
            f"Content: {content_for_log[:500]}"
        )

    return None


# =================================================================
# CareersFuture Query Processing
# =================================================================

def process_careers_future_query(
    search_query: str,
    limit: int = None
) -> list:
    """
    Fetch jobs from CareersFuture and return them
    as a list of dictionaries.
    """

    # -------------------------------------------------------------
    # 1. Fetch all potential jobs
    # -------------------------------------------------------------

    careers_future_jobs = (
        _fetch_careers_future_jobs(
            search_query
        )
    )

    if not careers_future_jobs:

        print(
            "No job items found in Phase 1. "
            "Skipping detail fetching."
        )

        return []

    # -------------------------------------------------------------
    # 2. Fetch existing identifiers from Supabase
    # -------------------------------------------------------------

    logging.info(
        "Phase 2: Fetching existing job identifiers "
        "from Supabase..."
    )

    try:

        (
            job_ids_set_supabase,
            company_title_set_supabase
        ) = (
            supabase_utils
            .get_existing_jobs_from_supabase()
        )

        logging.info(
            "Phase 2: Supabase returned "
            f"{len(job_ids_set_supabase)} existing IDs "
            f"and {len(company_title_set_supabase)} "
            "company/title pairs."
        )

    except Exception as e:

        logging.error(
            f"Failed to fetch existing jobs from Supabase: {e}"
        )

        logging.warning(
            "Proceeding without Supabase data; "
            "all fetched jobs will be considered new."
        )

        job_ids_set_supabase = set()
        company_title_set_supabase = set()

    # -------------------------------------------------------------
    # 3. Filter fetched jobs
    # -------------------------------------------------------------

    logging.info(
        "Phase 3: Filtering fetched jobs "
        "against Supabase data..."
    )

    new_job_ids_to_process = []

    skipped_by_id_count = 0
    skipped_by_combo_count = 0

    for job_item in careers_future_jobs:

        if not isinstance(job_item, dict):

            logging.warning(
                "Skipping invalid job item "
                "(not a dict): "
                f"{str(job_item)[:100]}"
            )

            continue

        job_uuid = str(
            job_item.get("uuid")
        )

        # ---------------------------------------------------------
        # Check 1: ID already exists
        # ---------------------------------------------------------

        if (
            job_uuid
            and job_uuid in job_ids_set_supabase
        ):

            logging.debug(
                "Skipping job "
                "(ID exists in Supabase): "
                f"UUID='{job_uuid}', "
                f"Title='{job_item.get('title', 'N/A')}'"
            )

            skipped_by_id_count += 1

            continue

        # ---------------------------------------------------------
        # Check 2: Company + Title
        # ---------------------------------------------------------

        company_name = (
            _get_careers_future_job_company_name(
                job_item
            )
        )

        job_title = job_item.get("title")

        normalized_company = None
        normalized_title = None

        if company_name:

            normalized_company = (
                company_name
                .strip()
                .lower()
            )

        if job_title:

            normalized_title = (
                job_title
                .strip()
                .lower()
            )

        if (
            normalized_company
            and normalized_title
        ):

            company_title_key = (
                normalized_company,
                normalized_title
            )

            if (
                company_title_key
                in company_title_set_supabase
            ):

                logging.debug(
                    "Skipping job "
                    "(Company/Title combo exists "
                    "in Supabase): "
                    f"UUID='{job_uuid}', "
                    f"Company='{normalized_company}', "
                    f"Title='{normalized_title}'"
                )

                skipped_by_combo_count += 1

                continue

        elif job_uuid:

            logging.debug(
                f"Job UUID='{job_uuid}' has no "
                "company/title for combo check. "
                "Will be added if ID is new."
            )

        else:

            logging.warning(
                "Job item has no UUID and insufficient "
                "company/title for matching: "
                f"{str(job_item)[:100]}"
            )

        new_job_ids_to_process.append(
            job_uuid
        )

    # -------------------------------------------------------------
    # 4. Fetch details ONLY for new jobs
    # -------------------------------------------------------------

    if (
        limit is not None
        and len(new_job_ids_to_process) > limit
    ):

        logging.info(
            "Truncating new_job_ids_to_process "
            f"from {len(new_job_ids_to_process)} "
            f"to {limit} to stay within source limit."
        )

        new_job_ids_to_process = (
            new_job_ids_to_process[:limit]
        )

    print(
        "\n--- Phase 4: Fetching Job Details "
        f"for {len(new_job_ids_to_process)} New Jobs ---"
    )

    detailed_new_jobs = []
    processed_count = 0

    for job_id in new_job_ids_to_process:

        details = (
            _fetch_careers_future_job_details(
                job_id
            )
        )

        if details:

            description = details.get(
                "description"
            )

            if (
                description
                and description.strip()
            ):

                if (
                    "job_id" in details
                    and details["job_id"] is not None
                ):

                    detailed_new_jobs.append(
                        details
                    )

                    processed_count += 1

                else:

                    logging.warning(
                        f"Fetched details for {job_id} "
                        "but missing 'job_id' key. "
                        "Skipping."
                    )

            else:

                logging.warning(
                    f"Skipping job ID {job_id} "
                    "due to missing or empty description."
                )

        else:

            logging.warning(
                f"Skipping job ID {job_id} "
                "as detail fetching failed "
                "or returned no data."
            )

    logging.info(
        "--- Finished Phase 4: Successfully fetched "
        f"details for {processed_count} new job(s) ---"
    )

    return detailed_new_jobs


# =================================================================
# Main Execution
# =================================================================

if __name__ == "__main__":

    total_new_jobs_saved = 0

    # =============================================================
    # LinkedIn
    # =============================================================

    if "linkedin" in config.SCRAPING_SOURCES:

        logging.info(
            "\n--- Starting LinkedIn Job Scraping ---"
        )

        max_jobs_per_search = (
            config.MAX_JOBS_PER_SEARCH.get(
                "linkedin",
                getattr(
                    config,
                    "DEFAULT_MAX_JOBS_PER_SEARCH",
                    10
                )
            )
        )

        # ---------------------------------------------------------
        # Iterate over:
        #
        # Location
        #     × Posting Date
        #         × Workplace Type
        #             × Search Query
        # ---------------------------------------------------------

        for location, geo_id in (
            config.LINKEDIN_LOCATIONS.items()
        ):

            for posting_date in (
                config.LINKEDIN_JOB_POSTING_DATES
            ):

                for work_type in (
                    config.LINKEDIN_WORK_TYPES
                ):

                    for query in (
                        config.LINKEDIN_SEARCH_QUERIES
                    ):

                        print(
                            f"\n{'=' * 20} "
                            f"Location='{location}' | "
                            f"Date='{posting_date}' | "
                            f"WorkType={work_type} | "
                            f"Query='{query}' "
                            f"{'=' * 20}"
                        )

                        # -------------------------------------------------
                        # Process this exact search combination
                        # -------------------------------------------------

                        new_linkedin_job_details = (
                            process_linkedin_query(
                                search_query=query,
                                location=location,
                                geo_id=geo_id,
                                posting_date=posting_date,
                                work_type=work_type,
                                limit=max_jobs_per_search,
                            )
                        )

                        # -------------------------------------------------
                        # Save new jobs
                        # -------------------------------------------------

                        if new_linkedin_job_details:

                            print(
                                f"\n--- Saving "
                                f"{len(new_linkedin_job_details)} "
                                f"new job(s) for query "
                                f"'{query}' "
                                f"[{location} | "
                                f"{posting_date} | "
                                f"{work_type}] ---"
                            )

                            supabase_utils.save_jobs_to_supabase(
                                new_linkedin_job_details
                            )

                            total_new_jobs_saved += (
                                len(
                                    new_linkedin_job_details
                                )
                            )

                        else:

                            print(
                                f"\nNo new job details were "
                                f"fetched or processed for "
                                f"query '{query}' "
                                f"[{location} | "
                                f"{posting_date} | "
                                f"{work_type}]."
                            )

    else:

        logging.info(
            "\n--- Skipping LinkedIn Job Scraping "
            "per config ---"
        )

    # =============================================================
    # CareersFuture
    # =============================================================

    if "careers_future" in config.SCRAPING_SOURCES:

        logging.info(
            "\n--- Starting Careers Future "
            "Job Scraping ---"
        )

        max_jobs_per_search = (
            config.MAX_JOBS_PER_SEARCH.get(
                "careers_future",
                getattr(
                    config,
                    "DEFAULT_MAX_JOBS_PER_SEARCH",
                    10
                )
            )
        )

        for query in (
            config.CAREERS_FUTURE_SEARCH_QUERIES
        ):

            logging.info(
                f"\n{'=' * 20} "
                "Processing Careers Future "
                f"Search Query: '{query}' "
                f"{'=' * 20}"
            )

            new_careers_future_job_details = (
                process_careers_future_query(
                    query,
                    limit=max_jobs_per_search
                )
            )

            if new_careers_future_job_details:

                logging.info(
                    f"\n--- Saving "
                    f"{len(new_careers_future_job_details)} "
                    f"new job(s) for query "
                    f"'{query}' ---"
                )

                supabase_utils.save_jobs_to_supabase(
                    new_careers_future_job_details
                )

                total_new_jobs_saved += (
                    len(
                        new_careers_future_job_details
                    )
                )

            else:

                logging.info(
                    f"\nNo new job details were "
                    f"fetched or processed for "
                    f"query '{query}'."
                )

    else:

        logging.info(
            "\n--- Skipping Careers Future "
            "Job Scraping per config ---"
        )

    # =============================================================
    # End of Script
    # =============================================================

    logging.info(
        f"\n{'=' * 20} "
        "Job scraping script finished "
        f"{'=' * 20}"
    )

    logging.info(
        "Total new jobs saved across all queries: "
        f"{total_new_jobs_saved}"
    )
