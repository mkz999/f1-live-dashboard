"""
Management command to populate database with test F1 race data.
Useful for testing dashboard without live API data.
"""
import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from live.models import Race, Driver, LapTiming, PitStop, TyreStint, Incident


DRIVERS_DATA = [
    {"abbr": "VER", "name": "Max Verstappen", "number": 1, "team": "Red Bull Racing", "color": "#0600EF"},
    {"abbr": "PER", "name": "Sergio Pérez", "number": 11, "team": "Red Bull Racing", "color": "#0600EF"},
    {"abbr": "HAM", "name": "Lewis Hamilton", "number": 44, "team": "Mercedes", "color": "#00D2BE"},
    {"abbr": "RUS", "name": "George Russell", "number": 63, "team": "Mercedes", "color": "#00D2BE"},
    {"abbr": "LEC", "name": "Charles Leclerc", "number": 16, "team": "Ferrari", "color": "#DC0000"},
    {"abbr": "SAI", "name": "Carlos Sainz", "number": 55, "team": "Ferrari", "color": "#DC0000"},
    {"abbr": "ALO", "name": "Fernando Alonso", "number": 14, "team": "Aston Martin", "color": "#006C42"},
    {"abbr": "STR", "name": "Lance Stroll", "number": 18, "team": "Aston Martin", "color": "#006C42"},
    {"abbr": "NOR", "name": "Lando Norris", "number": 4, "team": "McLaren", "color": "#FF8700"},
    {"abbr": "PIA", "name": "Oscar Piastri", "number": 81, "team": "McLaren", "color": "#FF8700"},
]


class Command(BaseCommand):
    help = "Generate test F1 race data for dashboard testing"

    def add_arguments(self, parser):
        parser.add_argument(
            '--laps',
            type=int,
            default=20,
            help='Number of laps to simulate (default=20)'
        )

    def handle(self, *args, **options):
        self.stdout.write("🏁 Creating test race data...")
        
        # Create Race
        race, created = Race.objects.get_or_create(
            year=2026,
            round_number=2,
            defaults={
                "grand_prix": "Saudi Arabian GP",
                "country": "Saudi Arabia",
                "circuit_name": "Jeddah Corniche Circuit",
                "circuit_length_km": 6.174,
                "total_laps": 50,
                "current_lap": 20,
                "is_running": True,
                "is_finished": False,
                "weather": "Clear",
                "air_temp": 28.5,
                "track_temp": 42.0,
                "safety_car": "NONE",
                "data_loaded": True,
            }
        )
        
        if created:
            self.stdout.write(f"✓ Created race: {race.grand_prix}")
        else:
            self.stdout.write(f"✓ Using existing race: {race.grand_prix}")
        
        # Create/Update Drivers
        drivers = []
        for i, driver_data in enumerate(DRIVERS_DATA):
            driver, _ = Driver.objects.get_or_create(
                race=race,
                abbreviation=driver_data["abbr"],
                defaults={
                    "full_name": driver_data["name"],
                    "number": driver_data["number"],
                    "team": driver_data["team"],
                    "team_color": driver_data["color"],
                    "grid_position": i + 1,
                    "status": "Running",
                    "is_fastest_lap": (i == 0),
                }
            )
            drivers.append(driver)
        
        self.stdout.write(f"✓ Created/updated {len(drivers)} drivers")
        
        # Generate lap times
        num_laps = options.get('laps', 20)
        self.stdout.write(f"✓ Generating {num_laps} laps...")
        
        base_lap_time = 95000  # 95 seconds base
        
        for lap_num in range(1, num_laps + 1):
            for pos, driver in enumerate(drivers):
                # Simulate realistic lap times
                gap = pos * 500  # Each position ~0.5s slower
                time_variation = random.randint(-1000, 1000)
                lap_time = base_lap_time + gap + time_variation + (lap_num * 100)  # Tire degradation
                
                # Calculate sectors
                sector1 = int(lap_time * 0.33)
                sector2 = int(lap_time * 0.33)
                sector3 = lap_time - sector1 - sector2
                
                LapTiming.objects.update_or_create(
                    race=race,
                    driver=driver,
                    lap_number=lap_num,
                    defaults={
                        "position": pos + 1,
                        "lap_time_ms": lap_time,
                        "sector1_ms": sector1,
                        "sector2_ms": sector2,
                        "sector3_ms": sector3,
                        "delta_to_leader_ms": gap,
                        "is_personal_best": (lap_num > 2 and random.random() > 0.7),
                    }
                )
        
        # Create some pit stops
        for i in range(5):
            driver = random.choice(drivers)
            pit_lap = random.randint(4, num_laps - 5)
            
            PitStop.objects.update_or_create(
                race=race,
                driver=driver,
                stop_number=1,
                defaults={
                    "lap_number": pit_lap,
                    "duration_ms": random.randint(20000, 30000),
                }
            )
        
        self.stdout.write("✓ Created pit stops")
        
        # Create tire stints
        for driver in drivers:
            for stint in range(1, 4):
                start_lap = (stint - 1) * (num_laps // 3) + 1
                end_lap = stint * (num_laps // 3)
                if stint == 3:
                    end_lap = num_laps
                
                TyreStint.objects.update_or_create(
                    race=race,
                    driver=driver,
                    stint_number=stint,
                    defaults={
                        "compound": random.choice(["SOFT", "MEDIUM", "HARD"]),
                        "start_lap": start_lap,
                        "end_lap": end_lap,
                        "tyre_age": stint * 10,
                        "is_new": (stint == 1),
                    }
                )
        
        self.stdout.write("✓ Created tire stints")
        
        # Create some incidents
        incidents = [
            {"lap": 8, "type": "SC", "desc": "Safety Car deployed - debris on track"},
            {"lap": 15, "type": "VSC", "desc": "Virtual Safety Car - minor incident Turn 2"},
            {"lap": 18, "type": "PENALTY", "driver": drivers[3], "desc": "5s penalty - unsafe release"},
        ]
        
        for incident in incidents:
            Incident.objects.get_or_create(
                race=race,
                lap_number=incident["lap"],
                incident_type=incident["type"],
                defaults={
                    "driver": incident.get("driver"),
                    "description": incident["desc"],
                }
            )
        
        self.stdout.write("✓ Created incidents")
        
        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Test data generated!\n"
            f"   Race: {race.grand_prix}\n"
            f"   Drivers: {len(drivers)}\n"
            f"   Laps: {num_laps}\n"
            f"   Run: python manage.py runserver"
        ))
