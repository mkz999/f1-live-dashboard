from django.db import models


class Race(models.Model):
    """Informace o závodě."""
    year = models.IntegerField(help_text="Rok sezóny")
    round_number = models.IntegerField(help_text="Číslo závodu v sezóně")
    grand_prix = models.CharField(max_length=100, help_text="Název Grand Prix")
    country = models.CharField(max_length=100, help_text="Stát")
    circuit_name = models.CharField(max_length=200, help_text="Název okruhu")
    circuit_length_km = models.FloatField(default=0, help_text="Délka okruhu v km")
    total_laps = models.IntegerField(default=0, help_text="Celkový počet kol")
    current_lap = models.IntegerField(default=0, help_text="Aktuální simulované kolo")
    is_running = models.BooleanField(default=False, help_text="Je simulace aktivní?")
    is_finished = models.BooleanField(default=False, help_text="Je závod dokončen?")
    weather = models.CharField(max_length=50, default="—", help_text="Počasí")
    air_temp = models.FloatField(null=True, blank=True, help_text="Teplota vzduchu °C")
    track_temp = models.FloatField(null=True, blank=True, help_text="Teplota trati °C")
    safety_car = models.CharField(
        max_length=20,
        default="NONE",
        choices=[
            ("NONE", "Žádný"),
            ("SC", "Safety Car"),
            ("VSC", "Virtual Safety Car"),
            ("RED", "Červená vlajka"),
        ],
        help_text="Stav Safety Caru v aktuálním kole",
    )
    data_loaded = models.BooleanField(default=False, help_text="Byla data načtena z FastF1?")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-round_number']
        unique_together = ['year', 'round_number']

    def __str__(self):
        return f"{self.year} {self.grand_prix}"


class Driver(models.Model):
    """Jezdec v závodě."""
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='drivers')
    abbreviation = models.CharField(max_length=3, help_text="Zkratka jezdce (VER, HAM...)")
    full_name = models.CharField(max_length=100, help_text="Celé jméno")
    number = models.IntegerField(help_text="Číslo jezdce")
    team = models.CharField(max_length=100, help_text="Název týmu")
    team_color = models.CharField(max_length=7, default="#ffffff", help_text="Barva týmu (#hex)")
    grid_position = models.IntegerField(default=0, help_text="Startovní pozice")
    status = models.CharField(max_length=50, default="Running", help_text="Stav (Running, DNF, +1 Lap...)")
    is_fastest_lap = models.BooleanField(default=False, help_text="Má nejrychlejší kolo?")

    class Meta:
        ordering = ['grid_position']
        unique_together = ['race', 'abbreviation']

    def __str__(self):
        return f"{self.abbreviation} – {self.full_name}"


class LapTiming(models.Model):
    """Časový záznam jednoho kola jednoho jezdce."""
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='lap_timings')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='lap_timings')
    lap_number = models.IntegerField(help_text="Číslo kola")
    position = models.IntegerField(help_text="Pozice v tomto kole")
    lap_time_ms = models.FloatField(null=True, blank=True, help_text="Čas kola v milisekundách")
    sector1_ms = models.FloatField(null=True, blank=True, help_text="Sektor 1 v ms")
    sector2_ms = models.FloatField(null=True, blank=True, help_text="Sektor 2 v ms")
    sector3_ms = models.FloatField(null=True, blank=True, help_text="Sektor 3 v ms")
    delta_to_leader_ms = models.FloatField(null=True, blank=True, help_text="Ztráta na lídra v ms")
    is_personal_best = models.BooleanField(default=False, help_text="Osobní nejlepší kolo?")

    class Meta:
        ordering = ['lap_number', 'position']
        unique_together = ['race', 'driver', 'lap_number']

    def __str__(self):
        return f"Lap {self.lap_number} – {self.driver.abbreviation} P{self.position}"

    @property
    def lap_time_str(self):
        """Formátuje čas kola jako M:SS.mmm."""
        if self.lap_time_ms is None:
            return "—"
        total_seconds = self.lap_time_ms / 1000
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:06.3f}"

    @property
    def delta_str(self):
        """Formátuje delta čas."""
        if self.delta_to_leader_ms is None:
            return "—"
        if self.delta_to_leader_ms == 0:
            return "LEADER"
        return f"+{self.delta_to_leader_ms / 1000:.3f}s"


class PitStop(models.Model):
    """Pitstop jezdce."""
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='pitstops')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='pitstops')
    lap_number = models.IntegerField(help_text="Kolo pitstop")
    stop_number = models.IntegerField(default=1, help_text="Kolikátý pitstop")
    duration_ms = models.FloatField(null=True, blank=True, help_text="Doba pitstop v ms")

    class Meta:
        ordering = ['lap_number']
        unique_together = ['race', 'driver', 'stop_number']

    def __str__(self):
        return f"Pit {self.stop_number} – {self.driver.abbreviation} (kolo {self.lap_number})"

    @property
    def duration_str(self):
        if self.duration_ms is None:
            return "—"
        return f"{self.duration_ms / 1000:.1f}s"


class TyreStint(models.Model):
    """Stint na jedné sadě pneumatik."""
    COMPOUND_CHOICES = [
        ("SOFT", "Soft"),
        ("MEDIUM", "Medium"),
        ("HARD", "Hard"),
        ("INTERMEDIATE", "Intermediate"),
        ("WET", "Wet"),
        ("UNKNOWN", "Unknown"),
    ]

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='tyre_stints')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='tyre_stints')
    stint_number = models.IntegerField(default=1, help_text="Kolikátý stint")
    compound = models.CharField(max_length=20, choices=COMPOUND_CHOICES, default="UNKNOWN")
    start_lap = models.IntegerField(help_text="Počáteční kolo stintu")
    end_lap = models.IntegerField(null=True, blank=True, help_text="Koncové kolo stintu")
    tyre_age = models.IntegerField(default=0, help_text="Stáří pneumatiky (kola)")
    is_new = models.BooleanField(default=True, help_text="Nová sada?")

    class Meta:
        ordering = ['driver', 'stint_number']
        unique_together = ['race', 'driver', 'stint_number']

    def __str__(self):
        return f"{self.driver.abbreviation} stint {self.stint_number}: {self.compound} (kolo {self.start_lap}–{self.end_lap or '?'})"


class Telemetry(models.Model):
    """Telemetrická data pedálů pro jednoho jezdce v jednom kole."""
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='telemetry')
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='telemetry')
    lap_number = models.IntegerField(help_text="Číslo kola")
    distance = models.TextField(help_text="JSON pole vzdáleností (m)")
    speed = models.TextField(help_text="JSON pole rychlostí (km/h)")
    throttle = models.TextField(help_text="JSON pole polohy plynu (0–100)")
    brake = models.TextField(help_text="JSON pole brzdění (0/1 nebo 0–100)")
    gear = models.TextField(default="[]", help_text="JSON pole převodového stupně")
    drs = models.TextField(default="[]", help_text="JSON pole DRS (0/1)")

    class Meta:
        ordering = ['driver', 'lap_number']
        unique_together = ['race', 'driver', 'lap_number']

    def __str__(self):
        return f"Telemetry – {self.driver.abbreviation} kolo {self.lap_number}"


class Incident(models.Model):
    """Incident během závodu (SC, VSC, penalizace, DNF)."""
    INCIDENT_TYPE_CHOICES = [
        ("SC", "Safety Car"),
        ("VSC", "Virtual Safety Car"),
        ("RED", "Červená vlajka"),
        ("PENALTY", "Penalizace"),
        ("DNF", "Odstoupení"),
        ("OTHER", "Jiné"),
    ]

    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name='incidents')
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE, related_name='incidents',
        null=True, blank=True, help_text="Dotčený jezdec (volitelné)"
    )
    lap_number = models.IntegerField(help_text="Kolo incidentu")
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPE_CHOICES)
    description = models.TextField(blank=True, help_text="Popis incidentu")

    class Meta:
        ordering = ['lap_number']

    def __str__(self):
        driver_str = self.driver.abbreviation if self.driver else "—"
        return f"Kolo {self.lap_number}: {self.incident_type} – {driver_str}"
