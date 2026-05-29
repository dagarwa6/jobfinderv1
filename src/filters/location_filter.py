from __future__ import annotations

import re

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
}

US_STATE_ABBREVS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI",
    "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC",
    "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

NON_US_INDICATORS = {
    "canada", "united kingdom", "uk", "london", "toronto", "vancouver",
    "germany", "berlin", "munich", "france", "paris", "japan", "tokyo",
    "india", "bangalore", "bengaluru", "mumbai", "hyderabad", "gurugram", "pune",
    "noida", "gurgaon", "chennai", "kolkata", "ahmedabad", "jaipur",
    "china", "shanghai", "beijing", "singapore", "australia", "sydney",
    "melbourne", "brazil", "são paulo", "sao paulo", "mexico",
    "ireland", "dublin", "netherlands", "amsterdam", "israel", "tel aviv",
    "korea", "seoul", "spain", "barcelona", "madrid", "italy", "rome",
    "milan", "poland", "warsaw", "sweden", "stockholm", "thailand",
    "bangkok", "philippines", "manila", "taiwan", "hong kong",
    "czech republic", "prague", "romania", "bucharest", "portugal",
    "lisbon", "argentina", "buenos aires", "colombia", "bogota",
    "chile", "santiago", "peru", "lima", "costa rica",
}

REMOTE_US_PATTERNS = [
    r"remote\s*[-–—/,]\s*us",
    r"remote\s*[-–—/,]\s*usa",
    r"remote\s*[-–—/,]\s*united\s*states",
    r"us\s*[-–—/,]\s*remote",
    r"usa\s*[-–—/,]\s*remote",
    r"united\s*states\s*[-–—/,]\s*remote",
    r"\bremote\b.*\b(us|usa|united states)\b",
    r"\b(us|usa|united states)\b.*\bremote\b",
]


def is_us_location(location: str) -> tuple[bool, str]:
    """Determine if a location string refers to a US location.

    Returns:
        Tuple of (is_us, normalized_location).

    Finding #14: Country-code prefix check runs BEFORE state abbreviation
    matching to prevent false positives like "Bloomington, IN" being rejected
    (IN = Indiana, not India). The prefix check only matches "XX - City" format
    where the code appears at the start followed by a dash.
    """
    if not location:
        return False, ""

    loc_lower = location.lower().strip()

    # Explicit US signals win — if the string ends with ", US" or ", USA" or
    # contains a US state abbreviation right next to "US", trust that over
    # ambiguous city names (e.g., "Dublin, OH, US" is Ohio, not Ireland).
    if re.search(r"\b(us|usa|united\s+states)\s*$", loc_lower) or re.search(r",\s*[a-z]{2}\s*,\s*(us|usa)\b", loc_lower):
        # Still reject if it actually says "remote - india, us" etc. — keep checking
        # for non-US indicators but only those that DON'T overlap with US city names.
        strong_non_us = {"canada", "united kingdom", "germany", "france", "japan",
                         "china", "singapore", "australia", "brazil", "mexico",
                         "ireland", "netherlands", "israel", "korea", "spain",
                         "italy", "poland", "sweden", "thailand", "philippines",
                         "taiwan", "hong kong", "argentina", "colombia", "chile",
                         "peru", "costa rica", "india", "bangalore", "bengaluru",
                         "mumbai", "hyderabad", "gurugram", "gurgaon", "noida",
                         "chennai", "kolkata", "ahmedabad", "jaipur", "pune"}
        for term in strong_non_us:
            if re.search(rf"\b{re.escape(term)}\b", loc_lower):
                return False, location
        # OK, trust the US suffix.
        # Fall through to state/city normalization below.
    else:
        # Word-boundary match for non-US indicators (substring would falsely
        # reject "Indianapolis" because it contains "india").
        for non_us in NON_US_INDICATORS:
            if re.search(rf"\b{re.escape(non_us)}\b", loc_lower):
                return False, location

    for pattern in REMOTE_US_PATTERNS:
        if re.search(pattern, loc_lower):
            return True, "Remote (US)"

    if loc_lower in ("remote", "remote - anywhere", "anywhere"):
        return True, "Remote"

    if loc_lower in ("united states", "usa", "us", "united states of america"):
        return True, "United States"

    for state in US_STATES:
        if state in loc_lower:
            return True, location

    # Reject country-code prefixes that collide with US state abbreviations
    # e.g. "IN - Bengaluru" (India), "DE - Berlin" (Germany)
    # Finding #14: Only match "XX - " at START of string (not "Bloomington, IN")
    NON_US_COUNTRY_CODES = {"IN", "DE", "UK", "GB", "SG", "JP", "CN", "KR", "BR", "MX", "IE", "NL", "IL", "FR", "ES", "IT", "PL", "SE", "TH", "PH", "TW", "HK", "CZ", "RO", "PT", "AR", "CO", "CL", "PE", "CR", "AU", "NZ", "CA"}
    country_prefix = re.match(r"^([A-Z]{2})\s*[-–—]\s*\S", location.strip())
    if country_prefix and country_prefix.group(1) in NON_US_COUNTRY_CODES:
        return False, location

    for abbrev in US_STATE_ABBREVS:
        if re.search(rf"\b{abbrev}\b", location):
            return True, location

    US_CITIES = {
        "new york", "los angeles", "chicago", "houston", "phoenix",
        "philadelphia", "san antonio", "san diego", "dallas", "san jose",
        "austin", "jacksonville", "fort worth", "columbus", "charlotte",
        "san francisco", "indianapolis", "seattle", "denver", "nashville",
        "oklahoma city", "el paso", "boston", "portland", "las vegas",
        "memphis", "louisville", "baltimore", "milwaukee", "albuquerque",
        "tucson", "fresno", "sacramento", "mesa", "kansas city",
        "atlanta", "raleigh", "omaha", "miami", "minneapolis",
        "tampa", "new orleans", "cleveland", "pittsburgh", "st. louis",
        "st louis", "salt lake city", "detroit", "bentonville",
        "arlington", "plano", "irving", "cupertino", "mountain view",
        "palo alto", "menlo park", "sunnyvale", "redmond", "bellevue",
        "scottsdale", "tempe", "boulder", "durham", "reston",
        "mclean", "tysons", "herndon", "bethesda", "washington",
    }

    for city in US_CITIES:
        if city in loc_lower:
            return True, location

    return False, location
