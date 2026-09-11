from apscheduler.schedulers.blocking import BlockingScheduler
from backend.config import load_preferences
from agents.pipeline import run


def _run_hyperdrive():
    """Run one full application cycle without allowing a failed cycle to kill the scheduler."""
    try:
        run()
    except Exception as exc:
        print(f"Tumelo Job Agent run failed: {exc}")


def main():
    preferences = load_preferences()
    scheduler = BlockingScheduler(timezone="Africa/Johannesburg")
    schedule_times = preferences.get("schedule_times", [])

    for index, value in enumerate(schedule_times):
        hour, minute = map(int, value.split(":"))
        scheduler.add_job(
            _run_hyperdrive,
            "cron",
            hour=hour,
            minute=minute,
            id=f"hyperdrive-{index}",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )

    print(
        f"Tumelo Job Agent HYPERDRIVE running with {len(schedule_times)} scheduled runs/day. "
        "Press Ctrl+C to stop."
    )
    scheduler.start()


if __name__ == "__main__":
    main()
