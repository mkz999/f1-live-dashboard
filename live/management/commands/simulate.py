"""
Management command: simulate
Simuluje průběh závodu po kolech – posouvá current_lap každých N sekund.

Použití:
    python manage.py simulate --race 1
    python manage.py simulate --race 1 --interval 3
    python manage.py simulate --race 1 --reset
"""
import time
from django.core.management.base import BaseCommand, CommandError
from live.models import Race, Incident


class Command(BaseCommand):
    help = "Simuluje průběh závodu po kolech."

    def add_arguments(self, parser):
        parser.add_argument('--race', type=int, required=True, help='ID závodu v databázi')
        parser.add_argument('--interval', type=int, default=4, help='Interval mezi koly v sekundách (výchozí: 4)')
        parser.add_argument('--reset', action='store_true', help='Resetovat závod na kolo 0')
        parser.add_argument('--start-lap', type=int, default=0, help='Počáteční kolo simulace')

    def handle(self, *args, **options):
        race_id = options['race']
        interval = options['interval']
        reset = options['reset']
        start_lap = options['start_lap']

        try:
            race = Race.objects.get(id=race_id)
        except Race.DoesNotExist:
            raise CommandError(f"Závod s ID {race_id} neexistuje.")

        if not race.data_loaded:
            raise CommandError(
                f"Data pro {race.grand_prix} ještě nebyla načtena. "
                f"Použij nejdříve: python manage.py load_race --year {race.year} --round {race.round_number}"
            )

        # Reset
        if reset:
            race.current_lap = 0
            race.is_running = False
            race.is_finished = False
            race.safety_car = 'NONE'
            race.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Závod {race.grand_prix} resetován na kolo 0."))
            return

        # Nastav počáteční kolo
        if start_lap > 0:
            race.current_lap = start_lap
            race.save()

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"  🏁 SIMULACE ZÁVODU: {race.grand_prix} {race.year}")
        self.stdout.write(f"  Celkem kol: {race.total_laps}")
        self.stdout.write(f"  Interval: {interval}s mezi koly")
        self.stdout.write(f"  Start od kola: {race.current_lap}")
        self.stdout.write(f"{'='*60}\n")
        self.stdout.write("  Stiskni Ctrl+C pro zastavení simulace.\n")

        # Načti incidenty pro SC/VSC detekci
        sc_laps = set(
            Incident.objects.filter(
                race=race, incident_type='SC'
            ).values_list('lap_number', flat=True)
        )
        vsc_laps = set(
            Incident.objects.filter(
                race=race, incident_type='VSC'
            ).values_list('lap_number', flat=True)
        )

        # Spusť simulaci
        race.is_running = True
        race.is_finished = False
        race.save()

        try:
            while race.current_lap < race.total_laps:
                race.current_lap += 1

                # Aktualizuj safety car stav
                if race.current_lap in sc_laps:
                    race.safety_car = 'SC'
                elif race.current_lap in vsc_laps:
                    race.safety_car = 'VSC'
                else:
                    race.safety_car = 'NONE'

                race.save()

                # Výpis do konzole
                sc_indicator = ""
                if race.safety_car == 'SC':
                    sc_indicator = " 🟡 SAFETY CAR"
                elif race.safety_car == 'VSC':
                    sc_indicator = " 🟡 VSC"

                progress = race.current_lap / race.total_laps * 100
                bar_len = 30
                filled = int(bar_len * race.current_lap / race.total_laps)
                bar = '█' * filled + '░' * (bar_len - filled)

                self.stdout.write(
                    f"  Kolo {race.current_lap:3d}/{race.total_laps} "
                    f"[{bar}] {progress:5.1f}%{sc_indicator}"
                )

                # Čekej interval
                if race.current_lap < race.total_laps:
                    time.sleep(interval)

            # Závod dokončen
            race.is_running = False
            race.is_finished = True
            race.safety_car = 'NONE'
            race.save()

            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(self.style.SUCCESS("  🏁 ZÁVOD DOKONČEN!"))
            self.stdout.write(f"{'='*60}\n")

        except KeyboardInterrupt:
            race.is_running = False
            race.save()
            self.stdout.write(f"\n\n  ⏸️  Simulace zastavena na kole {race.current_lap}.")
            self.stdout.write(f"  Pro pokračování: python manage.py simulate --race {race.id}")
            self.stdout.write(f"  Pro reset: python manage.py simulate --race {race.id} --reset\n")
