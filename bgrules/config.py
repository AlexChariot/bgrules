import sys

# Global debug flag - set based on command line arguments
DEBUG_MODE = "--debug" in sys.argv

ALLOWED_DOMAINS = [
    "asmodee",
    "days-of-wonder",
    "ravensburger",
    "hasbro",
]

PDF_FOLDER = "data/pdfs"
DB_PATH = "sqlite:///data/db.sqlite"