import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("worker")

load_dotenv()

from database import RDBMS

db = RDBMS()

async def process_job(job: dict, repo: dict):
    """Process a single job for a repository."""
    job_id = job['id']
    repo_id = repo['id']
    
    try:
        logger.info(f"🚀 Starting job {job_id} for repo {repo_id} ({repo['name']})")
        
        # Update job status to running
        db.update_job_status(job_id, "running")
        
        # Get repository path
        repo_path = Path(repo['local_path'])
        
        if not repo_path.exists():
            raise Exception(f"Repository path does not exist: {repo_path}")
        
        logger.info(f"📁 Repository path: {repo_path}")
        logger.info(f"📝 Instructions: {job['instructions'][:100]}...")
        
        # Import run_aider here to avoid circular imports
        from main import run_aider
        
        # Execute Aider with the instructions
        # Strip metadata from instructions before passing to Aider
        clean_instructions = job['instructions']
        vuln_id = None
        if "[METADATA:VULN_ID:" in clean_instructions:
            import re
            match = re.search(r"\[METADATA:VULN_ID:(\d+)\]", clean_instructions)
            if match:
                vuln_id = int(match.group(1))
                clean_instructions = clean_instructions.replace(match.group(0), "").strip()

        result = run_aider(
            repo_path=repo_path,
            instructions=clean_instructions,
            repo_id=repo_id,
            github_url=repo.get('github_url'),
            github_token=repo.get('github_token'),
            pr_target_branch="master"
        )
        
        # Mark job as completed
        db.update_job_status(
            job_id,
            "completed",
            result=str(result)
        )

        # If this was a vulnerability fix, mark it as resolved
        if vuln_id and result.get("created_branch"):
             logger.info(f"🔒 Marking vulnerability {vuln_id} as resolved")
             db.update_vulnerability_status(vuln_id, "resolved")
        
        logger.info(f"✅ Job {job_id} completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Job {job_id} failed with error: {str(e)}", exc_info=True)
        db.update_job_status(
            job_id,
            "failed",
            error_message=str(e)
        )


async def process_repositories():
    """Background worker that processes queued jobs per repository."""
    logger.info("=" * 70)
    logger.info("🤖 AI Code Assistant - Background Job Processor")
    logger.info("=" * 70)
    logger.info(f"Database: {os.getenv('DATABASE_URL', 'SQLite')}")
    logger.info("Processing jobs sequentially per repository...")
    logger.info("=" * 70)
    
    while True:
        try:
            # Get all active repositories
            repos = db.get_all_repositories()
            
            if not repos:
                logger.debug("No repositories found")
            
            for repo in repos:
                repo_id = repo['id']
                
                # Skip if already running a job for this repo
                if db.has_running_job(repo_id):
                    logger.debug(f"⏳ Repo {repo_id} ({repo['name']}) already has a running job")
                    continue
                
                # Get next pending job for this repo
                job = db.get_next_job(repo_id)
                if not job:
                    continue
                
                logger.info(f"📋 Found pending job {job['id']} for repo {repo_id}")
                
                # Process the job
                await process_job(job, repo)
            
            # Check for new jobs every 5 seconds
            await asyncio.sleep(5)
        
        except KeyboardInterrupt:
            logger.info("\n⏹️  Worker stopped by user")
            break
        except Exception as e:
            logger.error(f"Worker error: {str(e)}", exc_info=True)
            await asyncio.sleep(5)


def main():
    """Start the background worker."""
    try:
        asyncio.run(process_repositories())
    except KeyboardInterrupt:
        logger.info("Worker stopped")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()