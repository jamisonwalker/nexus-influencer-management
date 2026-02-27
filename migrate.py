import os
import urllib.parse
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from models import Base

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

def run_migrations():
    """
    Run database migrations to create tables based on SQLAlchemy models.
    
    Handles connection string parsing and password encoding for special characters.
    """
    try:
        raw_url = os.getenv("SUPABASE_DB_URL")
        
        if not raw_url:
            raise ValueError("SUPABASE_DB_URL environment variable is required")
            
        logger.info("🔧 Starting database migrations...")
        
        url = make_url(raw_url)
        
        # Strip the brackets if they are literally in the string
        clean_password = url.password.strip('[]')
        
        # Reconstruct with encoded password
        encoded_password = urllib.parse.quote_plus(clean_password)
        
        # Build the final safe URL
        safe_url = f"postgresql://{url.username}:{encoded_password}@{url.host}:{url.port}/{url.database}"
        
        logger.info(f"🔗 Connecting to Supabase at {url.host}:{url.port}")
        engine = create_engine(safe_url)
        
        try:
            Base.metadata.create_all(engine)
            logger.info("✅ Schema is up to date!")
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            raise
            
    except Exception as e:
        logger.error(f"❌ Database migration error: {str(e)}")
        raise

if __name__ == "__main__":
    try:
        run_migrations()
    except Exception as e:
        logger.error(f"❌ Migration process failed: {str(e)}")
        exit(1)
