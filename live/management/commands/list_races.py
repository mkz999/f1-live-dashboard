from django.core.management.base import BaseCommand
from live.models import Race


class Command(BaseCommand):
    help = "List all loaded races from database"

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            help='Filter by year'
        )
        parser.add_argument(
            '--active',
            action='store_true',
            help='Show only active/running races'
        )

    def handle(self, *args, **options):
        races = Race.objects.all().order_by('-year', '-round_number')
        
        # Apply filters
        if options.get('year'):
            races = races.filter(year=options['year'])
        
        if options.get('active'):
            races = races.filter(is_running=True)
        
        if not races.exists():
            self.stdout.write(self.style.WARNING("No races found."))
            return
        
        self.stdout.write(self.style.SUCCESS(f"\n{races.count()} race(s) found:\n"))
        
        for race in races:
            status = "🔴 LIVE" if race.is_running else ("✅ FINISHED" if race.is_finished else "⏸️  PENDING")
            data_status = "✓ DATA LOADED" if race.data_loaded else "✗ NO DATA"
            
            self.stdout.write(
                f"  [{race.id}] {race.year} R{race.round_number:2d} – {race.grand_prix:30s} "
                f"({race.country:15s}) | {status:15s} | {data_status}"
            )
            self.stdout.write(
                f"         Circuit: {race.circuit_name} ({race.circuit_length_km:.2f}km) "
                f"| Laps: {race.current_lap}/{race.total_laps}\n"
            )
