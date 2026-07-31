"""Built-in engagement templates. They are local, versioned, and freely available."""

ENGAGEMENT_TEMPLATES = {
    "web": {
        "name": "Web Application",
        "description": "Web application assessment with OWASP coverage.",
        "methodologies": ["owasp_top10"],
    },
    "api": {
        "name": "API Security",
        "description": "API assessment using OWASP API Security Top 10 coverage.",
        "methodologies": ["owasp_api_top10"],
    },
    "external": {
        "name": "External Network",
        "description": "Internet-facing network and service assessment.",
        "methodologies": ["network_pentest"],
    },
    "internal": {
        "name": "Internal Network",
        "description": "Internal network penetration test and service review.",
        "methodologies": ["network_pentest"],
    },
    "active_directory": {
        "name": "Active Directory",
        "description": "Directory-focused assessment with full penetration test phases.",
        "methodologies": ["ptes"],
    },
    "cloud": {
        "name": "Cloud Environment",
        "description": "Cloud-oriented technical security assessment planning.",
        "methodologies": ["nist_800_115"],
    },
}
