"""
Management command: load_race
Stáhne data ze zvoleného závodu pomocí FastF1 a uloží je do databáze.

Použití:
    python manage.py load_race --year 2024 --round 1
    python manage.py load_race --year 2023 --round 5
"""
import json
import logging
import numpy as np
import fastf1
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from live.models import (
    Race, Driver, LapTiming, PitStop, TyreStint, Telemetry, Incident,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Načte data závodu z FastF1 a uloží je do databáze."

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, required=True, help='Rok sezóny (např. 2024)')
        parser.add_argument('--round', type=int, required=True, help='Číslo závodu v sezóně')
        parser.add_argument('--force', action='store_true', help='Přepsat existující data')

    def handle(self, *args, **options):
        year = options['year']
        round_num = options['round']
        force = options['force']

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"  F1 Live Dashboard – Načítání dat")
        self.stdout.write(f"  Závod: {year}, kolo {round_num}")
        self.stdout.write(f"{'='*60}\n")

        # Kontrola, jestli data už existují
        existing = Race.objects.filter(year=year, round_number=round_num).first()
        if existing and existing.data_loaded and not force:
            self.stdout.write(self.style.WARNING(
                f"Data pro {existing.grand_prix} {year} už jsou načtena. "
                f"Použij --force pro přepsání."
            ))
            return

        if existing and force:
            self.stdout.write("Mažu existující data...")
            existing.delete()

        # Nastavení FastF1 cache
        cache_dir = str(settings.FASTF1_CACHE_DIR)
        fastf1.Cache.enable_cache(cache_dir)

        # --- 1. Načtení session ---
        self.stdout.write("📡 Načítám data ze session (to může trvat)...")
        try:
            session = fastf1.get_session(year, round_num, 'R')
            session.load(
                laps=True,
                telemetry=True,
                weather=True,
                messages=True,
            )
        except Exception as e:
            raise CommandError(f"Chyba při načítání dat z FastF1: {e}")

        event = session.event
        self.stdout.write(self.style.SUCCESS(
            f"Session načtena: {event['EventName']} – {event['Location']}"
        ))

        # --- 2. Vytvoření Race objektu ---
        self.stdout.write("Ukládám informace o závodě...")
        race = Race.objects.create(
            year=year,
            round_number=round_num,
            grand_prix=str(event['EventName']),
            country=str(event.get('Country', '—')),
            circuit_name=str(event.get('Location', '—')),
            circuit_length_km=0,  # FastF1 nemá přímý atribut
            total_laps=int(session.laps['LapNumber'].max()) if len(session.laps) > 0 else 0,
            current_lap=0,
            is_running=False,
            is_finished=False,
            weather=self._get_weather(session),
            air_temp=self._get_temp(session, 'AirTemp'),
            track_temp=self._get_temp(session, 'TrackTemp'),
            data_loaded=False,
        )

        # --- 3. Jezdci ---
        self.stdout.write("🏎️  Ukládám jezdce...")
        drivers_map = {}  # abbreviation -> Driver objekt
        results = session.results
        for _, row in results.iterrows():
            abbr = str(row.get('Abbreviation', ''))
            if not abbr:
                continue

            # Barva týmu
            color = '#ffffff'
            try:
                color_raw = row.get('TeamColor', 'ffffff')
                if color_raw and str(color_raw) != 'nan':
                    color = f"#{str(color_raw).strip('#')}"
            except Exception:
                pass

            # Grid position
            grid = 0
            try:
                grid_val = row.get('GridPosition', 0)
                grid = int(grid_val) if not np.isnan(grid_val) else 0
            except (ValueError, TypeError):
                pass

            # Status
            status = str(row.get('Status', 'Running'))

            full_name = str(row.get('FullName', abbr))
            number = 0
            try:
                num_val = row.get('DriverNumber', 0)
                number = int(num_val) if not np.isnan(float(num_val)) else 0
            except (ValueError, TypeError):
                pass

            team = str(row.get('TeamName', '—'))

            driver = Driver.objects.create(
                race=race,
                abbreviation=abbr,
                full_name=full_name,
                number=number,
                team=team,
                team_color=color,
                grid_position=grid,
                status=status,
            )
            drivers_map[abbr] = driver

        self.stdout.write(f"   → {len(drivers_map)} jezdců uloženo")

        # --- 4. Časy kol (LapTiming) ---
        self.stdout.write("⏱️  Ukládám časy kol...")
        laps = session.laps
        timings_to_create = []
        fastest_lap_time = None
        fastest_lap_driver = None

        for _, lap in laps.iterrows():
            abbr = str(lap.get('Driver', ''))
            driver = drivers_map.get(abbr)
            if not driver:
                continue

            lap_num = int(lap['LapNumber'])

            # Čas kola v ms
            lap_time_ms = None
            try:
                lt = lap.get('LapTime')
                if lt is not None and not (isinstance(lt, float) and np.isnan(lt)):
                    lap_time_ms = lt.total_seconds() * 1000
            except Exception:
                pass

            # Sektory
            s1 = self._td_to_ms(lap.get('Sector1Time'))
            s2 = self._td_to_ms(lap.get('Sector2Time'))
            s3 = self._td_to_ms(lap.get('Sector3Time'))

            # Pozice
            pos = 0
            try:
                pos_val = lap.get('Position')
                pos = int(pos_val) if pos_val is not None and not np.isnan(float(pos_val)) else 0
            except (ValueError, TypeError):
                pass

            # Personal best
            is_pb = False
            try:
                is_pb = bool(lap.get('IsPersonalBest', False))
            except Exception:
                pass

            # Track fastest lap
            if lap_time_ms and (fastest_lap_time is None or lap_time_ms < fastest_lap_time):
                fastest_lap_time = lap_time_ms
                fastest_lap_driver = abbr

            timings_to_create.append(LapTiming(
                race=race,
                driver=driver,
                lap_number=lap_num,
                position=pos,
                lap_time_ms=lap_time_ms,
                sector1_ms=s1,
                sector2_ms=s2,
                sector3_ms=s3,
                delta_to_leader_ms=None,  # Spočítáme dole
                is_personal_best=is_pb,
            ))

        # Bulk create
        LapTiming.objects.bulk_create(timings_to_create, ignore_conflicts=True)
        self.stdout.write(f"   → {len(timings_to_create)} záznamů kol uloženo")

        # Označit nejrychlejší kolo
        if fastest_lap_driver and fastest_lap_driver in drivers_map:
            drivers_map[fastest_lap_driver].is_fastest_lap = True
            drivers_map[fastest_lap_driver].save()

        # --- 5. Spočítat delta časy ---
        self.stdout.write("📊 Počítám delta časy...")
        self._compute_deltas(race)

        # --- 6. Pitstopy ---
        self.stdout.write("🔧 Ukládám pitstopy...")
        pits_created = self._save_pitstops(session, race, drivers_map)
        self.stdout.write(f"   → {pits_created} pitstopů uloženo")

        # --- 7. Pneumatiky (stinty) ---
        self.stdout.write("🛞 Ukládám stinty pneumatik...")
        stints_created = self._save_tyre_stints(session, race, drivers_map)
        self.stdout.write(f"   → {stints_created} stintů uloženo")

        # --- 8. Telemetrie (jen pro některá kola) ---
        self.stdout.write("📈 Ukládám telemetrii (top 5 jezdců, posledních 10 kol)...")
        tel_created = self._save_telemetry(session, race, drivers_map)
        self.stdout.write(f"   → {tel_created} telemetrických záznamů uloženo")

        # --- 9. Incidenty ---
        self.stdout.write("⚠️  Ukládám incidenty...")
        inc_created = self._save_incidents(session, race, drivers_map)
        self.stdout.write(f"   → {inc_created} incidentů uloženo")

        # --- Hotovo ---
        race.data_loaded = True
        race.save()

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(
            f"  Data úspěšně načtena pro: {race.grand_prix} {race.year}"
        ))
        self.stdout.write(f"  Celkem kol: {race.total_laps}")
        self.stdout.write(f"  Jezdců: {len(drivers_map)}")
        self.stdout.write(f"{'='*60}\n")
        self.stdout.write(
            "Pro spuštění simulace závodu použij:\n"
            f"  python manage.py simulate --race {race.id}\n"
        )

    # ===== HELPER METODY =====

    def _td_to_ms(self, val):
        """Převede timedelta na milisekundy."""
        try:
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return None
            return val.total_seconds() * 1000
        except Exception:
            return None

    def _get_weather(self, session):
        """Získá obecné počasí ze session."""
        try:
            weather = session.weather_data
            if weather is not None and len(weather) > 0:
                rainfall = weather['Rainfall'].any()
                if rainfall:
                    return "Déšť 🌧️"
                return "Sucho ☀️"
        except Exception:
            pass
        return "—"

    def _get_temp(self, session, col):
        """Získá průměrnou teplotu."""
        try:
            weather = session.weather_data
            if weather is not None and len(weather) > 0 and col in weather.columns:
                return round(float(weather[col].mean()), 1)
        except Exception:
            pass
        return None

    def _compute_deltas(self, race):
        """Spočítá kumulativní delta časy pro každé kolo."""
        all_laps = list(range(1, race.total_laps + 1))

        for lap_num in all_laps:
            timings = LapTiming.objects.filter(
                race=race, lap_number=lap_num
            ).order_by('position')

            if not timings.exists():
                continue

            # Najdi lídra (pozice 1)
            leader = timings.filter(position=1).first()
            if not leader:
                leader = timings.first()

            # Spočítej kumulativní časy
            cumulative = {}
            for drv in race.drivers.all():
                total = LapTiming.objects.filter(
                    race=race, driver=drv,
                    lap_number__lte=lap_num,
                    lap_time_ms__isnull=False,
                ).values_list('lap_time_ms', flat=True)
                if total:
                    cumulative[drv.id] = sum(total)

            if not cumulative:
                continue

            leader_total = cumulative.get(leader.driver_id)
            if leader_total is None:
                continue

            for timing in timings:
                drv_total = cumulative.get(timing.driver_id)
                if drv_total is not None:
                    timing.delta_to_leader_ms = drv_total - leader_total
                else:
                    timing.delta_to_leader_ms = None
                timing.save(update_fields=['delta_to_leader_ms'])

    def _save_pitstops(self, session, race, drivers_map):
        """Uloží pitstopy z FastF1 laps dat."""
        count = 0
        laps = session.laps

        for abbr, driver in drivers_map.items():
            driver_laps = laps[laps['Driver'] == abbr].sort_values('LapNumber')
            stop_num = 0

            for _, lap in driver_laps.iterrows():
                try:
                    pit_in = lap.get('PitInTime')
                    pit_out = lap.get('PitOutTime')

                    if pit_in is not None and not (isinstance(pit_in, float) and np.isnan(pit_in)):
                        stop_num += 1
                        duration_ms = None
                        if pit_out is not None and not (isinstance(pit_out, float) and np.isnan(pit_out)):
                            try:
                                duration_ms = (pit_out - pit_in).total_seconds() * 1000
                            except Exception:
                                pass

                        PitStop.objects.create(
                            race=race,
                            driver=driver,
                            lap_number=int(lap['LapNumber']),
                            stop_number=stop_num,
                            duration_ms=duration_ms,
                        )
                        count += 1
                except Exception:
                    continue

        return count

    def _save_tyre_stints(self, session, race, drivers_map):
        """Uloží stinty pneumatik."""
        count = 0
        laps = session.laps

        for abbr, driver in drivers_map.items():
            driver_laps = laps[laps['Driver'] == abbr].sort_values('LapNumber')
            if driver_laps.empty:
                continue

            stint_num = 0
            current_compound = None
            stint_start = None

            for _, lap in driver_laps.iterrows():
                compound = str(lap.get('Compound', 'UNKNOWN')).upper()
                if compound == 'NAN' or compound == '':
                    compound = 'UNKNOWN'

                lap_num = int(lap['LapNumber'])
                tyre_life = 0
                try:
                    tl = lap.get('TyreLife')
                    if tl is not None and not np.isnan(float(tl)):
                        tyre_life = int(tl)
                except (ValueError, TypeError):
                    pass

                fresh = True
                try:
                    fn = lap.get('FreshTyre')
                    if fn is not None:
                        fresh = bool(fn)
                except Exception:
                    pass

                if compound != current_compound:
                    # Uzavři předchozí stint
                    if current_compound is not None and stint_num > 0:
                        TyreStint.objects.filter(
                            race=race, driver=driver, stint_number=stint_num
                        ).update(end_lap=lap_num - 1)

                    stint_num += 1
                    current_compound = compound
                    stint_start = lap_num

                    TyreStint.objects.create(
                        race=race,
                        driver=driver,
                        stint_number=stint_num,
                        compound=compound if compound in ['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'] else 'UNKNOWN',
                        start_lap=stint_start,
                        end_lap=None,
                        tyre_age=tyre_life,
                        is_new=fresh,
                    )
                    count += 1
                else:
                    # Aktualizuj stáří pneumatiky
                    TyreStint.objects.filter(
                        race=race, driver=driver, stint_number=stint_num
                    ).update(tyre_age=tyre_life, end_lap=lap_num)

            # Uzavři poslední stint
            if stint_num > 0:
                last_lap = int(driver_laps.iloc[-1]['LapNumber'])
                TyreStint.objects.filter(
                    race=race, driver=driver, stint_number=stint_num
                ).update(end_lap=last_lap)

        return count

    def _save_telemetry(self, session, race, drivers_map):
        """Uloží telemetrii pedálů. Pro úsporu místa: top 5 jezdců, vybraná kola."""
        count = 0
        laps = session.laps

        # Najdi top 5 jezdců podle konečné pozice
        results = session.results.sort_values('Position')
        top_abbrs = [str(row['Abbreviation']) for _, row in results.head(5).iterrows()
                     if str(row.get('Abbreviation', '')) in drivers_map]

        # Pro každého jezdce ulož telemetrii pro každé 5. kolo + poslední kolo
        total_laps = race.total_laps
        selected_laps = set(range(1, total_laps + 1, 5))
        selected_laps.add(total_laps)
        # Přidej také posledních 10 kol
        for i in range(max(1, total_laps - 10), total_laps + 1):
            selected_laps.add(i)

        for abbr in top_abbrs:
            driver = drivers_map[abbr]
            driver_laps = laps[laps['Driver'] == abbr]

            for lap_num in sorted(selected_laps):
                try:
                    lap_data = driver_laps[driver_laps['LapNumber'] == lap_num]
                    if lap_data.empty:
                        continue

                    lap_row = lap_data.iloc[0]
                    tel = lap_row.get_telemetry()

                    if tel is None or tel.empty:
                        continue

                    # Vzorkuj na max 200 bodů
                    if len(tel) > 200:
                        step = len(tel) // 200
                        tel = tel.iloc[::step].head(200)

                    def safe_list(series):
                        """Převede pandas Series na list s ošetřením NaN."""
                        return [round(float(x), 1) if not np.isnan(float(x)) else 0
                                for x in series]

                    Telemetry.objects.create(
                        race=race,
                        driver=driver,
                        lap_number=lap_num,
                        distance=json.dumps(safe_list(tel['Distance'])),
                        speed=json.dumps(safe_list(tel['Speed'])),
                        throttle=json.dumps(safe_list(tel['Throttle'])),
                        brake=json.dumps(safe_list(tel['Brake'])),
                        gear=json.dumps(safe_list(tel['nGear'])) if 'nGear' in tel.columns else '[]',
                        drs=json.dumps(safe_list(tel['DRS'])) if 'DRS' in tel.columns else '[]',
                    )
                    count += 1
                except Exception as e:
                    logger.debug(f"Telemetrie skip {abbr} kolo {lap_num}: {e}")
                    continue

        return count

    def _save_incidents(self, session, race, drivers_map):
        """Uloží incidenty – DNF, SC, VSC z race control messages."""
        count = 0

        # 1. DNF z výsledků
        results = session.results
        for _, row in results.iterrows():
            status = str(row.get('Status', ''))
            abbr = str(row.get('Abbreviation', ''))
            driver = drivers_map.get(abbr)

            if status and 'Finished' not in status and '+' not in status and driver:
                # Najdi kolo, kde jezdec vypadl
                driver_laps = session.laps[session.laps['Driver'] == abbr]
                last_lap = int(driver_laps['LapNumber'].max()) if not driver_laps.empty else 0

                Incident.objects.create(
                    race=race,
                    driver=driver,
                    lap_number=last_lap,
                    incident_type='DNF',
                    description=f"{driver.full_name} – {status}",
                )
                count += 1

        # 2. Race control messages (SC, VSC)
        try:
            rcm = session.race_control_messages
            if rcm is not None and not rcm.empty:
                for _, msg in rcm.iterrows():
                    message = str(msg.get('Message', '')).upper()
                    category = str(msg.get('Category', ''))
                    lap = 0
                    try:
                        lap_val = msg.get('Lap')
                        if lap_val is not None and not np.isnan(float(lap_val)):
                            lap = int(lap_val)
                    except (ValueError, TypeError):
                        pass

                    if 'SAFETY CAR' in message and 'VIRTUAL' not in message:
                        Incident.objects.create(
                            race=race, driver=None, lap_number=lap,
                            incident_type='SC',
                            description=str(msg.get('Message', 'Safety Car')),
                        )
                        count += 1
                    elif 'VIRTUAL SAFETY CAR' in message or 'VSC' in message:
                        Incident.objects.create(
                            race=race, driver=None, lap_number=lap,
                            incident_type='VSC',
                            description=str(msg.get('Message', 'Virtual Safety Car')),
                        )
                        count += 1
        except Exception as e:
            logger.debug(f"RC messages skip: {e}")

        return count
