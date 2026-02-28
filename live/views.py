import json
from django.shortcuts import render
from django.http import JsonResponse
from .models import Race, Driver, LapTiming, PitStop, TyreStint, Telemetry, Incident


def dashboard(request):
    """F1 Live Dashboard main page."""
    return render(request, 'live/dashboard.html')


def _get_active_race():
    """Return active running race or last loaded race."""
    race = Race.objects.filter(is_running=True).first()
    if not race:
        race = Race.objects.filter(data_loaded=True).order_by('-id').first()
    return race


def api_race(request):
    """GET /api/race/ - Basic race information."""
    race = _get_active_race()
    if not race:
        return JsonResponse({'status': 'no_race', 'message': 'No race loaded.'})

    fastest = None
    fastest_driver = Driver.objects.filter(race=race, is_fastest_lap=True).first()
    if fastest_driver:
        fl = LapTiming.objects.filter(
            race=race, driver=fastest_driver, lap_time_ms__isnull=False
        ).order_by('lap_time_ms').first()
        if fl:
            fastest = {
                'driver': fastest_driver.abbreviation,
                'time': fl.lap_time_str,
                'lap': fl.lap_number,
            }

    return JsonResponse({
        'status': 'ok',
        'race': {
            'id': race.id,
            'grand_prix': race.grand_prix,
            'country': race.country,
            'circuit': race.circuit_name,
            'circuit_length_km': race.circuit_length_km,
            'total_laps': race.total_laps,
            'current_lap': race.current_lap,
            'is_running': race.is_running,
            'is_finished': race.is_finished,
            'weather': race.weather,
            'air_temp': race.air_temp,
            'track_temp': race.track_temp,
            'safety_car': race.safety_car,
            'fastest_lap': fastest,
        }
    })


def api_ranking(request):
    """GET /api/ranking/ - Driver standings for current lap."""
    race = _get_active_race()
    if not race:
        return JsonResponse({'status': 'no_race', 'drivers': []})

        drivers = Driver.objects.filter(race=race).order_by('grid_position')
        result = []
        for d in drivers:
            stint = TyreStint.objects.filter(
                race=race, driver=d, start_lap__lte=max(current_lap, 1)
            ).order_by('-stint_number').first()

            pit_count = PitStop.objects.filter(
                race=race, driver=d, lap_number__lte=max(current_lap, 1)
            ).count()

            result.append({
                'position': d.grid_position,
                'abbreviation': d.abbreviation,
                'full_name': d.full_name,
                'number': d.number,
                'team': d.team,
                'team_color': d.team_color,
                'grid_position': d.grid_position,
                'pos_change': 0,
                'lap_time': '—',
                'delta': '—',
                'status': d.status,
                'compound': stint.compound if stint else 'UNKNOWN',
                'tyre_age': stint.tyre_age if stint else 0,
                'pit_stops': pit_count,
                'is_fastest_lap': d.is_fastest_lap,
            })
        return JsonResponse({'status': 'ok', 'current_lap': current_lap, 'drivers': result})

    timings = LapTiming.objects.filter(
        race=race, lap_number=current_lap
    ).select_related('driver').order_by('position')

    result = []
    for t in timings:
        d = t.driver

        stint = TyreStint.objects.filter(
            race=race, driver=d,
            start_lap__lte=current_lap,
        ).filter(
            # end_lap >= current_lap OR end_lap is null
            end_lap__gte=current_lap
        ).first()

        if not stint:
            stint = TyreStint.objects.filter(
                race=race, driver=d,
                start_lap__lte=current_lap,
            ).order_by('-stint_number').first()

        pit_count = PitStop.objects.filter(
            race=race, driver=d, lap_number__lte=current_lap
        ).count()

        tyre_age = 0
        if stint:
            tyre_age = current_lap - stint.start_lap + 1

        pos_change = d.grid_position - t.position

        result.append({
            'position': t.position,
            'abbreviation': d.abbreviation,
            'full_name': d.full_name,
            'number': d.number,
            'team': d.team,
            'team_color': d.team_color,
            'grid_position': d.grid_position,
            'pos_change': pos_change,
            'lap_time': t.lap_time_str,
            'delta': t.delta_str,
            'delta_ms': t.delta_to_leader_ms,
            'status': d.status,
            'compound': stint.compound if stint else 'UNKNOWN',
            'tyre_age': tyre_age,
            'pit_stops': pit_count,
            'is_fastest_lap': d.is_fastest_lap,
            'sector1': round(t.sector1_ms / 1000, 3) if t.sector1_ms else None,
            'sector2': round(t.sector2_ms / 1000, 3) if t.sector2_ms else None,
            'sector3': round(t.sector3_ms / 1000, 3) if t.sector3_ms else None,
        })

    return JsonResponse({
        'status': 'ok',
        'current_lap': current_lap,
        'total_laps': race.total_laps,
        'drivers': result,
    })


def api_laptimes(request):
    """GET /api/laptimes/ - Lap times for charts (top 5 drivers)."""
    race = _get_active_race()
    if not race:
        return JsonResponse({'status': 'no_race', 'data': {}})

    current_lap = race.current_lap

    if current_lap >= 1:
        top_timings = LapTiming.objects.filter(
            race=race, lap_number=current_lap
        ).order_by('position')[:5]
        top_drivers = [t.driver for t in top_timings]
    else:
        top_drivers = list(
            Driver.objects.filter(race=race).order_by('grid_position')[:5]
        )

    data = {}
    for driver in top_drivers:
        laps = LapTiming.objects.filter(
            race=race, driver=driver,
            lap_number__lte=current_lap,
            lap_time_ms__isnull=False,
        ).order_by('lap_number')

        data[driver.abbreviation] = {
            'color': driver.team_color,
            'laps': [lt.lap_number for lt in laps],
            'times': [round(lt.lap_time_ms / 1000, 3) for lt in laps],
        }

    return JsonResponse({
        'status': 'ok',
        'current_lap': current_lap,
        'data': data,
    })


def api_telemetry(request, abbreviation):
    """GET /api/telemetry/<abbreviation>/ - Pedal telemetry for driver."""
    race = _get_active_race()
    if not race:
        return JsonResponse({'status': 'no_race'})

    driver = Driver.objects.filter(race=race, abbreviation=abbreviation.upper()).first()
    if not driver:
        return JsonResponse({'status': 'error', 'message': 'Driver not found.'})

    current_lap = race.current_lap


    tel = Telemetry.objects.filter(
        race=race, driver=driver, lap_number__lte=current_lap
    ).order_by('-lap_number').first()

    if not tel:
        return JsonResponse({
            'status': 'ok',
            'driver': abbreviation.upper(),
            'lap': None,
            'telemetry': None,
        })

    return JsonResponse({
        'status': 'ok',
        'driver': abbreviation.upper(),
        'driver_name': driver.full_name,
        'team': driver.team,
        'team_color': driver.team_color,
        'lap': tel.lap_number,
        'telemetry': {
            'distance': json.loads(tel.distance),
            'speed': json.loads(tel.speed),
            'throttle': json.loads(tel.throttle),
            'brake': json.loads(tel.brake),
            'gear': json.loads(tel.gear),
            'drs': json.loads(tel.drs),
        }
    })


def api_incidents(request):
    """GET /api/incidents/ - Race incidents up to current lap."""
    race = _get_active_race()
    if not race:
        return JsonResponse({'status': 'no_race', 'incidents': []})

    current_lap = race.current_lap

    incidents = Incident.objects.filter(
        race=race, lap_number__lte=current_lap
    ).select_related('driver').order_by('-lap_number')

    result = []
    for inc in incidents:
        result.append({
            'lap': inc.lap_number,
            'type': inc.incident_type,
            'type_display': inc.get_incident_type_display(),
            'driver': inc.driver.abbreviation if inc.driver else None,
            'driver_name': inc.driver.full_name if inc.driver else None,
            'description': inc.description,
        })

    return JsonResponse({
        'status': 'ok',
        'current_lap': current_lap,
        'incidents': result,
    })


def api_drivers(request):
    """GET /api/drivers/ - List all drivers for telemetry select."""
    race = _get_active_race()
    if not race:
        return JsonResponse({'status': 'no_race', 'drivers': []})

    drivers = Driver.objects.filter(race=race).order_by('grid_position')

    result = []
    for d in drivers:
        has_tel = Telemetry.objects.filter(race=race, driver=d).exists()
        result.append({
            'abbreviation': d.abbreviation,
            'full_name': d.full_name,
            'number': d.number,
            'team': d.team,
            'team_color': d.team_color,
            'has_telemetry': has_tel,
        })

    return JsonResponse({
        'status': 'ok',
        'drivers': result,
    })
