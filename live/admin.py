from django.contrib import admin
from .models import Race, Driver, LapTiming, PitStop, TyreStint, Telemetry, Incident


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):
    list_display = ['year', 'round_number', 'grand_prix', 'circuit_name', 'total_laps', 'current_lap', 'is_running', 'data_loaded']
    list_filter = ['year', 'is_running', 'data_loaded']


@admin.register(Driver)
class DriverAdmin(admin.ModelAdmin):
    list_display = ['abbreviation', 'full_name', 'number', 'team', 'race', 'grid_position']
    list_filter = ['race', 'team']


@admin.register(LapTiming)
class LapTimingAdmin(admin.ModelAdmin):
    list_display = ['lap_number', 'driver', 'position', 'lap_time_str', 'delta_str']
    list_filter = ['race', 'driver', 'lap_number']


@admin.register(PitStop)
class PitStopAdmin(admin.ModelAdmin):
    list_display = ['driver', 'lap_number', 'stop_number', 'duration_str']
    list_filter = ['race', 'driver']


@admin.register(TyreStint)
class TyreStintAdmin(admin.ModelAdmin):
    list_display = ['driver', 'stint_number', 'compound', 'start_lap', 'end_lap', 'tyre_age', 'is_new']
    list_filter = ['race', 'compound']


@admin.register(Telemetry)
class TelemetryAdmin(admin.ModelAdmin):
    list_display = ['driver', 'lap_number']
    list_filter = ['race', 'driver']


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ['lap_number', 'incident_type', 'driver', 'description']
    list_filter = ['race', 'incident_type']
