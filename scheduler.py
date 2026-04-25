from apscheduler.schedulers.blocking import BlockingScheduler
from main import main

scheduler = BlockingScheduler(timezone="America/New_York")

# Run every 48 hours
scheduler.add_job(main, "interval", hours=48)

if __name__ == "__main__":
    print("[INFO] Internship agent scheduler started.")
    scheduler.start()
