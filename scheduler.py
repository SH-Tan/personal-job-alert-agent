from apscheduler.schedulers.blocking import BlockingScheduler
from main import main

scheduler = BlockingScheduler()

# Run every 6 hours
scheduler.add_job(main, "interval", hours=6)

if __name__ == "__main__":
    print("[INFO] Internship agent scheduler started.")
    scheduler.start()