import os
import requests
import json
import time
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from live.models import Race, Driver, LapTiming, PitStop, TyreStint, Incident


class OpenF1Client:
    """Klient pro OpenF1 API s OAuth2 autentizací."""
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.base_url = "https://api.openf1.org/v1"
        self.token_url = "https://api.openf1.org/token"
        self.token = None
        self.token_expiry = None
        
    def authenticate(self):
        """Získej OAuth2 token."""
        try:
            response = requests.post(
                self.token_url,
                data={
                    "grant_type": "password",
                    "username": self.username,
                    "password": self.password,
                }
            )
            response.raise_for_status()
            data = response.json()
            self.token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))
            self.token_expiry = time.time() + expires_in - 60  # refresh 60s před expirací
            print(f"✓ OAuth2 token acquired (expires in {expires_in}s)")
            return True
        except Exception as e:
            print(f"✗ Authentication failed: {e}")
            return False
    
    def _refresh_token_if_needed(self):
        """Refresh token pokud je blízko expiraci."""
        if self.token_expiry and time.time() >= self.token_expiry:
            self.authenticate()
    
    def _make_request(self, endpoint):
        """Dělej API request s autentizací."""
        self._refresh_token_if_needed()
        
        headers = {
            "Authorization": f"Bearer {self.token}"
        }
        
        try:
            response = requests.get(
                f"{self.base_url}{endpoint}",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"✗ API request failed: {e}")
            return None
    
    def get_sessions(self):
        """Vrátí seznam aktuálních sessions."""
        return self._make_request("/sessions")
    
    def get_drivers(self, session_key):
        """Vrátí seznam jezdců v session."""
        return self._make_request(f"/drivers?session_key={session_key}")
    
    def get_laps(self, session_key):
        """Vrátí seznam kol v session."""
        return self._make_request(f"/laps?session_key={session_key}")
    
    def get_race_control(self, session_key):
        """Vrátí race control eventy."""
        return self._make_request(f"/race_control?session_key={session_key}")


class Command(BaseCommand):
    help = "Fetch live race data from OpenF1 API a updatuj Django models"
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=3,
            help='Interval mezi requesty (sekundy, default=3)'
        )
    
    def handle(self, *args, **options):
        # Načti credentials z .env
        username = os.getenv("OPENF1_USERNAME")
        password = os.getenv("OPENF1_PASSWORD")
        
        if not username or not password:
            raise CommandError(
                "OPENF1_USERNAME a OPENF1_PASSWORD musí být definovány v .env"
            )
        
        interval = options.get('interval', 3)
        
        # Připoj se k OpenF1
        client = OpenF1Client(username, password)
        if not client.authenticate():
            raise CommandError("Autentizace na OpenF1 selhala")
        
        self.stdout.write(self.style.SUCCESS("✓ Připojen k OpenF1 API"))
        self.stdout.write(
            f"  Polling interval: {interval}s\n"
            f"  Stiskni Ctrl+C pro zastavení\n"
        )
        
        try:
            iteration = 0
            while True:
                iteration += 1
                timestamp = datetime.now().strftime("%H:%M:%S")
                self.stdout.write(f"\n[{timestamp}] Iterace #{iteration}", ending="")
                
                # Fetchni sessions
                sessions = client.get_sessions()
                if not sessions:
                    self.stdout.write(" – Sessions nedostupné")
                    time.sleep(interval)
                    continue
                
                # Najdi aktuální session (poslední live session)
                current_session = None
                for session in sessions:
                    if session.get("status") in ["live", "completed"]:
                        current_session = session
                        break
                
                if not current_session:
                    self.stdout.write(" – Žádná aktuální session")
                    time.sleep(interval)
                    continue
                
                session_key = current_session.get("session_key")
                session_type = current_session.get("session_type", "unknown")
                year = current_session.get("date_start", "")[:4]
                round_num = current_session.get("round", 0)
                
                self.stdout.write(
                    f" – {year} R{round_num} {session_type} "
                    f"({current_session.get('status')})"
                )
                
                # Vytvoř nebo updatuj Race
                race, created = Race.objects.get_or_create(
                    year=int(year),
                    round_number=round_num,
                    defaults={
                        "grand_prix": current_session.get("location", "Unknown"),
                        "country": current_session.get("country", ""),
                        "circuit_name": current_session.get("circuit_short_name", ""),
                        "is_running": current_session.get("status") == "live",
                        "is_finished": current_session.get("status") == "completed",
                        "data_loaded": True,
                    }
                )
                
                # Updatuj Race stav
                race.is_running = current_session.get("status") == "live"
                race.is_finished = current_session.get("status") == "completed"
                race.save(update_fields=['is_running', 'is_finished'])
                
                # Fetchni a updatuj drivers
                drivers_data = client.get_drivers(session_key)
                if drivers_data:
                    for driver_data in drivers_data:
                        driver, created = Driver.objects.get_or_create(
                            race=race,
                            abbreviation=driver_data.get("abbreviation", "UNK"),
                            defaults={
                                "full_name": driver_data.get("full_name", "Unknown"),
                                "number": driver_data.get("driver_number", 0),
                                "team": driver_data.get("team_name", ""),
                                "team_color": driver_data.get("team_colour", "#ffffff"),
                                "grid_position": driver_data.get("grid_position", 0),
                                "status": driver_data.get("status", "Running"),
                            }
                        )
                        
                        # Updatuj driver aktuální status
                        driver.status = driver_data.get("status", "Running")
                        driver.save(update_fields=['status'])
                
                # Fetchni a updatuj laps
                laps_data = client.get_laps(session_key)
                if laps_data:
                    for lap_data in laps_data:
                        driver_abbr = lap_data.get("driver_abbreviation")
                        lap_num = lap_data.get("lap_number")
                        
                        # Najdi driver
                        try:
                            driver = Driver.objects.get(
                                race=race,
                                abbreviation=driver_abbr
                            )
                        except Driver.DoesNotExist:
                            continue
                        
                        # Create or update LapTiming
                        lap_time = lap_data.get("duration_ms")
                        
                        LapTiming.objects.update_or_create(
                            race=race,
                            driver=driver,
                            lap_number=lap_num,
                            defaults={
                                "position": lap_data.get("lap_position", 0),
                                "lap_time_ms": lap_time,
                                "sector1_ms": lap_data.get("sector1_ms"),
                                "sector2_ms": lap_data.get("sector2_ms"),
                                "sector3_ms": lap_data.get("sector3_ms"),
                                "is_personal_best": lap_data.get("is_personal_best", False),
                            }
                        )
                
                # Fetchni a updatuj incidents
                rc_data = client.get_race_control(session_key)
                if rc_data:
                    for event in rc_data:
                        lap_num = event.get("lap_number", 0)
                        message = event.get("message", "")
                        
                        # Mapuj message na incident_type
                        incident_type = "OTHER"
                        if "SAFETY" in message.upper() and "VIRTUAL" not in message.upper():
                            incident_type = "SC"
                        elif "VIRTUAL" in message.upper():
                            incident_type = "VSC"
                        elif "RED FLAG" in message.upper():
                            incident_type = "RED"
                        elif "PENALTY" in message.upper():
                            incident_type = "PENALTY"
                        
                        # Try to find driver if in message
                        driver = None
                        for d in race.drivers.all():
                            if d.abbreviation in message.upper():
                                driver = d
                                break
                        
                        # Vytvoř incident (prevent duplicates s lap_number + message)
                        Incident.objects.get_or_create(
                            race=race,
                            lap_number=lap_num,
                            incident_type=incident_type,
                            defaults={
                                "driver": driver,
                                "description": message,
                            }
                        )
                
                time.sleep(interval)
        
        except KeyboardInterrupt:
            self.stdout.write("\n\n✓ Live race monitoring zastaveno")
