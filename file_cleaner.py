import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
import schedule
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
)
logger = logging.getLogger('FileCleaner')

class FileCleaner:
    def __init__(self, directories=None, file_types=None, max_age_minutes=5, excluded_files=None):
        """Initialize FileCleaner with target directories and file types"""
        self.directories = directories or ['.', 'test']  # Default to current and test directory
        self.file_types = file_types or ['.csv', '.txt']  # Default to .csv and .txt files
        self.max_age_minutes = max_age_minutes
        self.excluded_files = excluded_files or ['requirements.txt']  # Default excluded files
        self.is_running = False
        logger.info(f"FileCleaner initialized - will clean {', '.join(self.file_types)} files after {max_age_minutes} minutes")
        logger.info(f"Excluded files: {', '.join(self.excluded_files)}")

    def clean_old_files(self):
        """Clean files older than max_age_minutes"""
        try:
            current_time = datetime.now()
            files_removed = 0
            
            for directory in self.directories:
                if not os.path.exists(directory):
                    continue
                    
                logger.debug(f"Scanning directory: {directory}")
                
                for file in os.listdir(directory):
                    # Skip if file is in excluded list
                    if file in self.excluded_files:
                        continue
                        
                    file_path = os.path.join(directory, file)
                    
                    # Skip if not a file or doesn't match target extensions
                    if not os.path.isfile(file_path) or not any(file.endswith(ext) for ext in self.file_types):
                        continue
                    
                    # Get file creation/modification time
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    age = current_time - file_time
                    
                    # Remove if older than max age
                    if age > timedelta(minutes=self.max_age_minutes):
                        try:
                            os.remove(file_path)
                            files_removed += 1
                            logger.info(f"Removed old file: {file} (age: {age.total_seconds()/60:.1f} minutes)")
                        except Exception as e:
                            logger.error(f"Error removing file {file}: {str(e)}")
            
            if files_removed > 0:
                logger.info(f"Cleaned {files_removed} old files")
                
        except Exception as e:
            logger.error(f"Error during file cleaning: {str(e)}")

    def start(self):
        """Start the file cleaning scheduler"""
        if self.is_running:
            logger.warning("File cleaner is already running")
            return
            
        def run_scheduler():
            self.is_running = True
            logger.info("File cleaner started")
            
            # Schedule cleaning every minute
            schedule.every(1).minutes.do(self.clean_old_files)
            
            # Run the scheduler
            while self.is_running:
                schedule.run_pending()
                time.sleep(1)
        
        # Start scheduler in a separate thread
        self.scheduler_thread = threading.Thread(target=run_scheduler)
        self.scheduler_thread.daemon = True
        self.scheduler_thread.start()

    def stop(self):
        """Stop the file cleaning scheduler"""
        if not self.is_running:
            logger.warning("File cleaner is not running")
            return
            
        self.is_running = False
        self.scheduler_thread.join()
        logger.info("File cleaner stopped")

def main():
    # Create and start the file cleaner
    cleaner = FileCleaner(
        directories=['.', 'test'],  # Add your directories here
        file_types=['.csv', '.txt'],
        max_age_minutes=5,
        excluded_files=['requirements.txt']  # Add excluded files here
    )
    
    try:
        cleaner.start()
        logger.info("Press Ctrl+C to stop the file cleaner")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cleaner.stop()
        logger.info("File cleaner stopped by user")

if __name__ == "__main__":
    main() 