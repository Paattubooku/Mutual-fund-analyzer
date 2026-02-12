import requests
import re
from bs4 import BeautifulSoup


def slugify(name):
    """Convert scheme name to URL-friendly slug — KEEP ORIGINAL CASE"""
    slug = name.strip()

    # Normalize double spaces
    slug = re.sub(r'\s{2,}', ' ', slug)

    # Remove (Formerly...) and (erstwhile...)
    slug = re.sub(r'\s*\(Formerly.*?\)', '', slug, flags=re.IGNORECASE)
    slug = re.sub(r'\s*\(erstwhile.*?\)', '', slug, flags=re.IGNORECASE)

    # Remove special chars EXCEPT letters, numbers, spaces, hyphens
    slug = re.sub(r'[^a-zA-Z0-9\s\-]', '', slug)

    # Normalize " - " or "- " or " -" → "-"
    slug = re.sub(r'\s*-\s*', '-', slug)

    # Replace remaining spaces with hyphens
    slug = re.sub(r'\s+', '-', slug)

    # Remove double hyphens
    slug = re.sub(r'-{2,}', '-', slug)

    # Trim
    slug = slug.strip('-')

    return slug


def clean_text(text):
    """Clean whitespace from scraped text"""
    if not text:
        return ""
    text = re.sub(r'[\t\r\n]+', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def scrape_advisorkhoj(scheme_name):
    """Scrape mutual fund data from AdvisorKhoj"""
    slug = slugify(scheme_name)
    url = f"https://www.advisorkhoj.com/mutual-funds-research/{slug}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        print(f"Scraping {url}")
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None, slug, url

        soup = BeautifulSoup(resp.text, "lxml")
        text = soup.get_text(separator="\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Check if valid fund page (not homepage/error)
        if not any(marker in text for marker in ["Total Assets:", "NAV as on"]):
            return None, slug, url

        data = {}

        # ════════════════════════════════════════
        #  LINE-BY-LINE PARSING (most reliable)
        # ════════════════════════════════════════
        for i, line in enumerate(lines):
            ll = line.lower().strip()

            # ── AUM ──
            if ll in ["total assets:", "total assets"]:
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    m = re.search(r'([\d,]+\.?\d*)\s*(Cr|Crore)', next_line)
                    if m:
                        data["aum"] = f"₹{m.group(1)} {m.group(2)}"
                        # Also grab date if present
                        dm = re.search(r'[Aa]s\s*on\s*([\d\-\/\w]+)', next_line)
                        if dm:
                            data["aum"] += f" (as on {dm.group(1)})"

            # ── EXIT LOAD ──
            if ll in ["exit load:", "exit load"]:
                if i + 1 < len(lines):
                    parts = []
                    j = i + 1
                    while j < len(lines) and j <= i + 8:
                        p = lines[j].strip()
                        # Stop if we hit next section
                        if re.match(
                            r'^(NAV\s|Total\s|Expense|Benchmark|Category|'
                            r'Launch|Scheme|Min|Entry|SIP|Fund\s*Manager)',
                            p, re.IGNORECASE
                        ):
                            break
                        if p and p not in ['|']:
                            parts.append(p)
                        j += 1

                    exit_text = clean_text(" ".join(parts))

                    if exit_text.lower() in ['nil', '-', 'na', 'none', 'not applicable']:
                        data["exit_load"] = "Nil"
                    elif exit_text:
                        if len(exit_text) > 300:
                            exit_text = exit_text[:300] + "..."
                        data["exit_load"] = exit_text

            # ── TER / EXPENSE RATIO ──
            if re.search(r'expense\s*ratio', ll):
                # Check same line for value
                em = re.search(r'(\d+\.?\d*)\s*%', line)
                if em:
                    val = float(em.group(1))
                    if 0 < val < 5:
                        data["ter"] = f"{em.group(1)}%"
                # Check next line
                elif i + 1 < len(lines):
                    em = re.search(r'(\d+\.?\d*)\s*%', lines[i + 1])
                    if em:
                        val = float(em.group(1))
                        if 0 < val < 5:
                            data["ter"] = f"{em.group(1)}%"

        # ════════════════════════════════════════
        #  FALLBACK: TABLE-BASED EXTRACTION
        # ════════════════════════════════════════
        if not data:
            for row in soup.find_all("tr"):
                cols = row.find_all(["td", "th"])
                if len(cols) < 2:
                    continue

                key = clean_text(cols[0].get_text()).lower()
                val = clean_text(cols[1].get_text())

                if not key or not val:
                    continue

                # AUM
                if "total assets" in key or "aum" in key or "fund size" in key:
                    m = re.search(r'([\d,]+\.?\d*)\s*(Cr|Crore)', val)
                    if m:
                        data["aum"] = f"₹{m.group(1)} {m.group(2)}"

                # TER
                if "expense ratio" in key or key == "ter":
                    m = re.search(r'(\d+\.?\d*)\s*%', val)
                    if m and 0 < float(m.group(1)) < 5:
                        data["ter"] = f"{m.group(1)}%"

                # Exit Load
                if "exit load" in key:
                    if val.lower() in ['nil', '-', 'na', 'none']:
                        data["exit_load"] = "Nil"
                    elif len(val) > 2:
                        data["exit_load"] = val[:300]

        # ════════════════════════════════════════
        #  FALLBACK: RAW HTML REGEX
        # ════════════════════════════════════════
        raw_html = resp.text

        if "aum" not in data:
            m = re.search(
                r'Total\s*Assets\s*:?\s*</[^>]+>\s*<[^>]+>\s*([\d,]+\.?\d*)\s*(Cr|Crore)',
                raw_html, re.IGNORECASE
            )
            if m:
                data["aum"] = f"₹{m.group(1)} {m.group(2)}"

        if "exit_load" not in data:
            m = re.search(
                r'<b>Exit\s*Load:</b>\s*(.*?)(?:</td>|</tr>)',
                raw_html, re.IGNORECASE | re.DOTALL
            )
            if m:
                exit_soup = BeautifulSoup(m.group(1), "lxml")
                exit_text = clean_text(exit_soup.get_text())
                if exit_text.lower() in ['nil', '-', 'na']:
                    data["exit_load"] = "Nil"
                elif exit_text and len(exit_text) > 2:
                    data["exit_load"] = exit_text[:300]

        return data if data else None, slug, url

    except Exception as e:
        print(f"Error scraping {scheme_name}: {e}")
        return None, slugify(scheme_name), url


# ════════════════════════════════════════
#  TEST
# ════════════════════════════════════════
if __name__ == "__main__":
    
    NAV_URL = "https://portal.amfiindia.com/spages/NAVOpen.txt"
    
    print("Fetching scheme names from AMFI...")
    # Download NAV file
    response = requests.get(NAV_URL)
    data = response.text.split("\n")
    
    scheme_names = []
    
    for line in data:
        parts = line.split(";")
        if len(parts) > 3 and parts[0].strip().isdigit():
            scheme_name = parts[3].strip()
            if scheme_name and "Direct" in scheme_name and "Growth" in scheme_name:
                scheme_names.append(scheme_name)
    
    print(f"Found {len(scheme_names)} Direct Growth schemes")
    print(f"Testing first 10 schemes...\n")
    
    # Test first 10 schemes
    # test_limit = 50
    
    # Counters
    success_count = 0
    failed_count = 0
    
    print(f"{'='*100}")
    print(f"{'SCHEME':<55} {'AUM':<22} {'TER':<8} {'EXIT LOAD':<20}")
    print(f"{'='*100}")
    
    for scheme in scheme_names:
        result = scrape_advisorkhoj(scheme)
        
        # Unpack the tuple properly
        if result and len(result) == 3:
            data, slug, url = result
        else:
            data, slug, url = None, "", ""
        
        if data:
            aum = data.get("aum", "N/A")[:20]
            ter = data.get("ter", "N/A")[:7]
            el = data.get("exit_load", "N/A")[:18]
            print(f"✅ {scheme[:53]:<55} {aum:<22} {ter:<8} {el:<20}")
            success_count += 1
        else:
            print(f"❌ {scheme[:53]:<55} {'—':<22} {'—':<8} {'—':<20}")
            print(f"   Slug: {slug}")
            print(f"   URL:  {url}")
            failed_count += 1
    
    print(f"{'='*100}")
    print(f"\n📊 SUMMARY:")
    print(f"   Total Tested:  {success_count+failed_count}")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Failed:     {failed_count}")
    print(f"{'='*100}")