"""Runs the daily maturity check and reminder job. Schedule it once a day (cron or Task Scheduler)."""
from django.core.management.base import BaseCommand

from fdr import services


class Command(BaseCommand):
    help = 'Maturity check and reminders. Safe to run more than once a day.'

    def handle(self, *args, **options):
        result = services.run_daily_jobs()
        self.stdout.write(
            f"Status changes: {result['statusChanges']}, reminders created: {result['remindersCreated']}, "
            f"emails sent: {result['emailsSent']}"
        )
