import logging
import xml.etree.ElementTree as ET
import urllib3
import requests

# Set up basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

EDUSKUNTA_API_BASE = "https://avoindata.eduskunta.fi/api/v1"
FINLEX_API_BASE = "https://opendata.finlex.fi/finlex/avoindata/v1"

def get_session():
    """Create and configure a requests Session with error recovery and connection pooling."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Finland-Legislative-Tracker/1.0 (Python; Requests)",
        "Accept-Encoding": "gzip"
    })
    
    # Check if we encounter SSL issues (common in fresh macOS Python setups)
    try:
        session.get(f"{EDUSKUNTA_API_BASE}/tables/", timeout=5)
    except requests.exceptions.SSLError:
        logger.warning("SSL verification failed. Enabling insecure request fallback...")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        session.verify = False
    except Exception as e:
        logger.warning("Session initialization connection test failed: %s", e)
        
    return session

def parse_proposal_xml(xml_content):
    """Parse the XML content of a government proposal (HE) and extract metadata.
    
    Returns:
        dict: A dictionary of parsed fields, or None if the document is not a proposal.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        logger.error("Failed to parse XML content: %s", e)
        return {"error": f"XML parse error: {e}"}

    def clean_tag(elem):
        return elem.tag.split("}")[-1] if elem is not None else ""

    # Validate message type (must be Finnish or Swedish government proposal)
    msg_type_elem = next((e for e in root.iter() if clean_tag(e) == "SanomatyyppiNimi"), None)
    msg_type = msg_type_elem.text.strip() if msg_type_elem is not None and msg_type_elem.text else ""
    
    if msg_type not in ("VASKI_JULKVP_GovernmentProposal_fi", "VASKI_JULKVP_GovernmentProposal_sv"):
        return None

    metadata = {
        "message_type": msg_type,
        "identifier": "",
        "title": "",
        "date": "",
        "keywords": [],
        "summary": ""
    }

    for elem in root.iter():
        tag = clean_tag(elem)
        if tag == "JulkaisuMetatieto":
            # Extract identifier and date from attributes if available
            for key, val in elem.attrib.items():
                attr_name = key.split("}")[-1]
                if attr_name == "eduskuntaTunnus":
                    metadata["identifier"] = val
                elif attr_name == "laadintaPvm":
                    metadata["date"] = val
        elif tag == "NimekeTeksti":
            metadata["title"] = elem.text.strip() if elem.text else ""
        elif tag == "LaadintaPvmTeksti" and not metadata["date"]:
            metadata["date"] = elem.text.strip() if elem.text else ""
        elif tag == "AiheTeksti" and elem.text:
            val = elem.text.strip()
            if val and val not in metadata["keywords"]:
                metadata["keywords"].append(val)
        elif tag == "SisaltoKuvaus":
            texts = [t.strip() for t in elem.itertext() if t.strip()]
            metadata["summary"] = " ".join(texts)

    # Fallback for identifier if not extracted from attributes
    if not metadata["identifier"]:
        id_elem = next((e for e in root.iter() if clean_tag(e) == "EduskuntaTunnus"), None)
        if id_elem is not None and id_elem.text:
            metadata["identifier"] = id_elem.text.strip()

    return metadata

def fetch_recent_matters(limit=50):
    """Fetch the most recent government proposals (HE) from the Eduskunta API.
    
    Paginates backwards through VaskiData rows.
    
    Args:
        limit (int): The maximum number of proposals to retrieve.
        
    Returns:
        list: A list of dictionaries, each containing metadata for a proposal.
    """
    session = get_session()
    proposals = []
    per_page = 100
    
    # 1. Fetch total count to determine pagination start
    logger.info("Fetching VaskiData table counts...")
    try:
        response = session.get(f"{EDUSKUNTA_API_BASE}/tables/counts", timeout=10)
        response.raise_for_status()
        counts = response.json()
        row_count = next((item["rowCount"] for item in counts if item.get("tableName") == "VaskiData"), None)
    except Exception as e:
        logger.error("Failed to fetch table counts: %s", e)
        return []
        
    if not row_count:
        logger.error("VaskiData table row count is unavailable.")
        return []
        
    total_pages = (row_count + per_page - 1) // per_page
    logger.info("VaskiData has %d rows (~%d pages). Scanning for %d HE proposals...", row_count, total_pages, limit)
    
    # 2. Paginate backwards from the last page
    page = total_pages - 1
    while page >= 0 and len(proposals) < limit:
        logger.info("Fetching page %d...", page)
        try:
            url = f"{EDUSKUNTA_API_BASE}/tables/VaskiData/rows"
            response = session.get(url, params={"page": page, "perPage": per_page}, timeout=15)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.error("Error fetching page %d: %s. Aborting scan.", page, e)
            break
            
        rows = data.get("rowData", [])
        if not rows:
            logger.warning("Page %d returned no row data.", page)
            page -= 1
            continue
            
        # Process rows in reverse order (newest first within the page)
        for row in reversed(rows):
            if len(proposals) >= limit:
                break
                
            try:
                # row columns: Id:0, XmlData:1, Status:2, Created:3, Eduskuntatunnus:4
                tunnus = row[4]
                if tunnus and tunnus.startswith("HE "):
                    proposal = parse_proposal_xml(row[1])
                    if proposal:
                        proposal["id"] = row[0]
                        proposal["created"] = row[3]
                        proposal["xml_content"] = row[1]
                        proposals.append(proposal)
            except IndexError as ie:
                logger.error("Malformed row structure on page %d: %s", page, ie)
            except Exception as ex:
                logger.error("Unexpected error parsing row: %s", ex)
                
        page -= 1
        
    logger.info("Successfully fetched %d government proposals.", len(proposals))
    return proposals

def parse_statute_id(statute_id):
    """Parse a statute ID into (year, number) dynamically.
    
    Supports formats: 'number/year' or 'year/number'.
    
    Returns:
        tuple: (year, number) as strings.
    """
    parts = [p.strip() for p in str(statute_id).split("/")]
    if len(parts) != 2:
        raise ValueError(f"Invalid statute ID format: '{statute_id}'. Expected format 'number/year' (e.g. 585/2023).")
        
    p0_is_year = parts[0].isdigit() and 1800 <= int(parts[0]) <= 2100
    p1_is_year = parts[1].isdigit() and 1800 <= int(parts[1]) <= 2100
    
    if p0_is_year and not p1_is_year:
        return parts[0], parts[1]
    elif p1_is_year and not p0_is_year:
        return parts[1], parts[0]
    else:
        # Default fallback: assume first is number, second is year
        return parts[1], parts[0]

def fetch_finlex_xml(statute_id):
    """Query the Finlex REST API for a statute in Akoma Ntoso XML format.
    
    Args:
        statute_id (str): The ID of the law, e.g. "585/2023".
        
    Returns:
        str: The raw Akoma Ntoso XML text, or None if the request failed.
    """
    try:
        year, number = parse_statute_id(statute_id)
    except ValueError as ve:
        logger.error(ve)
        return None
        
    session = get_session()
    
    # Constructing URL deterministically using year and number as per GUARDRAILS.md
    url = f"{FINLEX_API_BASE}/akn/fi/act/statute/{year}/{number}/fin@"
    logger.info("Fetching Finlex statute %s/%s from %s...", number, year, url)
    
    try:
        response = session.get(url, timeout=15)
        
        if response.status_code == 404:
            logger.error("Statute %s/%s not found on Finlex (404).", number, year)
            return None
        elif response.status_code == 429:
            logger.error("Finlex API rate limit exceeded (429).")
            return None
            
        response.raise_for_status()
        return response.text
        
    except requests.exceptions.RequestException as e:
        logger.error("Failed to fetch Finlex XML: %s", e, exc_info=True)
    except Exception as e:
        logger.error("Failed to fetch Finlex XML: %s", e, exc_info=True)
        
    return None
