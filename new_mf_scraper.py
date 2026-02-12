import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime


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


def calculate_fund_age(launch_date_str):
    """Calculate fund age from launch date string"""
    try:
        # Try different date formats
        date_formats = ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y', '%Y/%m/%d']
        
        launch_date = None
        for fmt in date_formats:
            try:
                launch_date = datetime.strptime(launch_date_str, fmt)
                break
            except ValueError:
                continue
        
        if not launch_date:
            return None
        
        today = datetime.now()
        years = today.year - launch_date.year
        months = today.month - launch_date.month
        
        if months < 0:
            years -= 1
            months += 12
        
        if years > 0:
            if months > 0:
                return f"{years}Y {months}M"
            else:
                return f"{years}Y"
        else:
            return f"{months}M"
    
    except Exception as e:
        return None


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

            # ── FUND AGE ──
            if ll in ["fund age:", "fund age"]:
                if i + 1 < len(lines):
                    age_line = lines[i + 1].strip()
                    # Direct fund age (e.g., "17Y 3M")
                    if re.search(r'\d+Y|\d+M', age_line):
                        data["fund_age"] = age_line
            
            # ── LAUNCH DATE (for calculating Fund Age) ──
            if ll in ["launch date:", "launch date", "inception date:", "inception date"]:
                if i + 1 < len(lines):
                    date_line = lines[i + 1].strip()
                    # Extract date pattern
                    date_match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', date_line)
                    if date_match and "fund_age" not in data:
                        launch_date = date_match.group(1)
                        fund_age = calculate_fund_age(launch_date)
                        if fund_age:
                            data["fund_age"] = fund_age
                            data["launch_date"] = launch_date

            # ── AUM / TOTAL ASSETS ──
            if ll in ["total assets:", "total assets", "aum:", "aum", "fund size:", "fund size"]:
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    # Match patterns like "24,523.83 Cr As on 30-01-2026"
                    m = re.search(r'([\d,]+\.?\d*)\s*(Cr|Crore)', next_line, re.IGNORECASE)
                    if m:
                        aum_value = f"₹{m.group(1)} {m.group(2)}"
                        # Also grab date if present
                        dm = re.search(r'[Aa]s\s*on\s*([\d\-\/]+)', next_line)
                        if dm:
                            aum_value += f" (as on {dm.group(1)})"
                        data["aum"] = aum_value

            # ── TER / EXPENSE RATIO ──
            if ll in ["ter:", "ter", "expense ratio:", "expense ratio"]:
                # Check same line for value (e.g., "TER: 0.91% As on (31-01-2026)")
                em = re.search(r'(\d+\.?\d*)\s*%', line)
                if em:
                    val = float(em.group(1))
                    if 0 < val < 5:
                        ter_val = f"{em.group(1)}%"
                        # Try to capture the date
                        dm = re.search(r'[Aa]s\s*on\s*\(?([\d\-\/]+)\)?', line)
                        if dm:
                            ter_val += f" (as on {dm.group(1)})"
                        data["ter"] = ter_val
                # Check next line
                elif i + 1 < len(lines):
                    next_line = lines[i + 1]
                    em = re.search(r'(\d+\.?\d*)\s*%', next_line)
                    if em:
                        val = float(em.group(1))
                        if 0 < val < 5:
                            ter_val = f"{em.group(1)}%"
                            # Try to capture the date from next line
                            dm = re.search(r'[Aa]s\s*on\s*\(?([\d\-\/]+)\)?', next_line)
                            if dm:
                                ter_val += f" (as on {dm.group(1)})"
                            data["ter"] = ter_val

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
                            r'Launch|Scheme|Min|Entry|SIP|Fund\s*Manager|TER)',
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

        # ════════════════════════════════════════
        #  FALLBACK: TABLE-BASED EXTRACTION
        # ════════════════════════════════════════
        for row in soup.find_all("tr"):
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue

            key = clean_text(cols[0].get_text()).lower()
            val = clean_text(cols[1].get_text())

            if not key or not val:
                continue

            # Fund Age
            if "fund age" in key and "fund_age" not in data:
                if re.search(r'\d+Y|\d+M', val):
                    data["fund_age"] = val

            # Launch Date
            if ("launch date" in key or "inception date" in key) and "fund_age" not in data:
                date_match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', val)
                if date_match:
                    launch_date = date_match.group(1)
                    fund_age = calculate_fund_age(launch_date)
                    if fund_age:
                        data["fund_age"] = fund_age
                        data["launch_date"] = launch_date

            # AUM
            if ("total assets" in key or "aum" in key or "fund size" in key) and "aum" not in data:
                m = re.search(r'([\d,]+\.?\d*)\s*(Cr|Crore)', val, re.IGNORECASE)
                if m:
                    aum_value = f"₹{m.group(1)} {m.group(2)}"
                    dm = re.search(r'[Aa]s\s*on\s*([\d\-\/]+)', val)
                    if dm:
                        aum_value += f" (as on {dm.group(1)})"
                    data["aum"] = aum_value

            # TER
            if ("expense ratio" in key or key == "ter" or "ter:" in key) and "ter" not in data:
                m = re.search(r'(\d+\.?\d*)\s*%', val)
                if m:
                    val_float = float(m.group(1))
                    if 0 < val_float < 5:
                        ter_val = f"{m.group(1)}%"
                        dm = re.search(r'[Aa]s\s*on\s*\(?([\d\-\/]+)\)?', val)
                        if dm:
                            ter_val += f" (as on {dm.group(1)})"
                        data["ter"] = ter_val

            # Exit Load
            if "exit load" in key and "exit_load" not in data:
                if val.lower() in ['nil', '-', 'na', 'none']:
                    data["exit_load"] = "Nil"
                elif len(val) > 2:
                    data["exit_load"] = val[:300]

        # ════════════════════════════════════════
        #  FALLBACK: RAW HTML REGEX
        # ════════════════════════════════════════
        raw_html = resp.text

        # Fund Age from HTML
        if "fund_age" not in data:
            # Try direct fund age
            m = re.search(r'<b>Fund\s*Age:</b>\s*([^<]+)', raw_html, re.IGNORECASE)
            if m:
                age = clean_text(m.group(1))
                if re.search(r'\d+Y|\d+M', age):
                    data["fund_age"] = age
            
            # Try launch date
            if "fund_age" not in data:
                m = re.search(r'<b>Launch\s*Date:</b>\s*([^<]+)', raw_html, re.IGNORECASE)
                if m:
                    date_str = clean_text(m.group(1))
                    date_match = re.search(r'(\d{2}[-/]\d{2}[-/]\d{4})', date_str)
                    if date_match:
                        launch_date = date_match.group(1)
                        fund_age = calculate_fund_age(launch_date)
                        if fund_age:
                            data["fund_age"] = fund_age
                            data["launch_date"] = launch_date

        # AUM from HTML
        if "aum" not in data:
            m = re.search(
                r'<b>Total\s*Assets:</b>\s*[^>]*>\s*[^>]*>\s*([\d,]+\.?\d*)\s*(Cr|Crore)',
                raw_html, re.IGNORECASE | re.DOTALL
            )
            if m:
                aum_value = f"₹{m.group(1)} {m.group(2)}"
                # Try to get date
                dm = re.search(
                    r'<b>Total\s*Assets:</b>.*?[Aa]s\s*on\s*([\d\-\/]+)',
                    raw_html, re.IGNORECASE | re.DOTALL
                )
                if dm:
                    aum_value += f" (as on {dm.group(1)})"
                data["aum"] = aum_value

        # TER from HTML
        if "ter" not in data:
            # Try comprehensive pattern: "TER: 0.91% As on (31-01-2026)"
            m = re.search(
                r'<b>TER:</b>\s*([\d\.]+)\s*%\s*As\s*on\s*\(?([\d\-\/]+)\)?',
                raw_html, re.IGNORECASE
            )
            if m:
                data["ter"] = f"{m.group(1)}% (as on {m.group(2)})"
            else:
                # Try simpler pattern
                m = re.search(r'<b>TER:</b>\s*([\d\.]+)\s*%', raw_html, re.IGNORECASE)
                if m:
                    val_float = float(m.group(1))
                    if 0 < val_float < 5:
                        data["ter"] = f"{m.group(1)}%"

        # Exit Load from HTML
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
    print(f"Testing schemes...\n")
    
    # Counters
    success_count = 0
    failed_count = 0
    
    print(f"{'='*130}")
    print(f"{'SCHEME':<55} {'FUND AGE':<10} {'AUM':<25} {'TER':<20} {'EXIT LOAD':<18}")
    print(f"{'='*130}")
    
    for scheme in scheme_names:
        result = scrape_advisorkhoj(scheme)
        
        # Unpack the tuple properly
        if result and len(result) == 3:
            data, slug, url = result
        else:
            data, slug, url = None, "", ""
        
        if data:
            fund_age = data.get("fund_age", "N/A")[:9]
            aum = data.get("aum", "N/A")[:23]
            ter = data.get("ter", "N/A")[:18]
            el = data.get("exit_load", "N/A")[:16]
            print(f"✅ {scheme[:53]:<55} {fund_age:<10} {aum:<25} {ter:<20} {el:<18}")
            success_count += 1
        else:
            print(f"❌ {scheme[:53]:<55} {'—':<10} {'—':<25} {'—':<20} {'—':<18}")
            print(f"   Slug: {slug}")
            print(f"   URL:  {url}")
            failed_count += 1
    
    print(f"{'='*130}")
    print(f"\n📊 SUMMARY:")
    print(f"   Total Tested:  {success_count+failed_count}")
    print(f"   ✅ Successful: {success_count}")
    print(f"   ❌ Failed:     {failed_count}")
    print(f"{'='*130}")