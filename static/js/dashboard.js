/**
 * F1 Live Dashboard – hlavní JavaScript soubor.
 * Live aktualizace: race/ranking/incidents/laptimes každých 3s, telemetrie 1.5s
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log('🏎️ F1 Live Dashboard loaded');    // ===== STAV =====
    let lapTimesChart = null;
    let telemetryChart = null;
    let selectedDriver = '';
    let driversLoaded = false;
    let lastLap = -1;
    let previousPositions = {};  // track position changes

    // ===== DOM ELEMENTY =====
    const $ = (sel) => document.querySelector(sel);
    const statusDot = $('.status-dot');
    const statusText = $('#race-status');
    const raceName = $('#race-name');
    const circuitName = $('#circuit-name');
    const currentLapEl = $('#current-lap');
    const weatherEl = $('#weather');
    const safetyCarEl = $('#safety-car');
    const standingsBody = $('#standings-body');
    const incidentsList = $('#incidents-list');
    const driverSelect = $('#driver-select');

    // ===== POMOCNÉ FUNKCE =====
    async function fetchJSON(url) {
        try {
            const res = await fetch(url);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return await res.json();
        } catch (e) {
            console.error(`Fetch error ${url}:`, e);
            return null;
        }
    }

    function formatLapTime(seconds) {
        if (!seconds) return '—';
        const min = Math.floor(seconds / 60);
        const sec = (seconds % 60).toFixed(3);
        return `${min}:${sec.padStart(6, '0')}`;
    }

    // ===== 1. RACE INFO =====
    async function updateRaceInfo() {
        const data = await fetchJSON('/api/race/');
        if (!data || data.status !== 'ok') {
            statusDot.classList.remove('live');
            statusText.textContent = 'OFFLINE';
            raceName.textContent = 'Žádný závod';
            return;
        }

        const r = data.race;
        raceName.textContent = `${r.grand_prix} – ${r.country}`;
        circuitName.textContent = r.circuit;
        currentLapEl.textContent = `${r.current_lap} / ${r.total_laps}`;

        // Počasí + teploty
        let weatherStr = r.weather || '—';
        if (r.air_temp) weatherStr += ` | Vzduch ${r.air_temp}°C`;
        if (r.track_temp) weatherStr += ` | Trať ${r.track_temp}°C`;
        weatherEl.textContent = weatherStr;

        // Safety car
        const scMap = { 'NONE': '—', 'SC': '🟡 SAFETY CAR', 'VSC': '🟡 VSC', 'RED': '🔴 RED FLAG' };
        safetyCarEl.textContent = scMap[r.safety_car] || '—';
        safetyCarEl.className = 'info-value' + (r.safety_car !== 'NONE' ? ' sc-active' : '');

        // Status
        if (r.is_running) {
            statusDot.classList.add('live');
            statusText.textContent = 'LIVE';
        } else if (r.is_finished) {
            statusDot.classList.remove('live');
            statusText.textContent = 'DOKONČENO';
        } else {
            statusDot.classList.remove('live');
            statusText.textContent = 'PŘIPRAVENO';
        }

        // Rychlé kolo
        if (r.fastest_lap) {
            const flInfo = `${r.fastest_lap.driver} – ${r.fastest_lap.time} (kolo ${r.fastest_lap.lap})`;
            let flEl = $('#fastest-lap-val');
            if (flEl) flEl.textContent = flInfo;
        }
    }    // ===== 2. RANKING =====
    async function updateRanking() {
        const data = await fetchJSON('/api/ranking/');
        if (!data || data.status !== 'ok' || !data.drivers.length) return;

        let html = '';
        for (const d of data.drivers) {
            // Změna pozice
            let posChangeHtml = '';
            if (d.pos_change > 0) {
                posChangeHtml = `<span class="pos-change up">▲${d.pos_change}</span>`;
            } else if (d.pos_change < 0) {
                posChangeHtml = `<span class="pos-change down">▼${Math.abs(d.pos_change)}</span>`;
            } else {
                posChangeHtml = `<span class="pos-change same">—</span>`;
            }

            // Tyre badge (kruhové)
            const compound = d.compound || 'UNKNOWN';
            const tyreHtml = `<span class="tyre-badge ${compound}">${compound.charAt(0)}</span>`;
            const tyreAge = d.tyre_age > 0 ? `<span class="tyre-age">${d.tyre_age}L</span>` : '';

            // Delta
            let deltaClass = '';
            if (d.delta === 'LEADER') deltaClass = '';
            else if (d.delta_ms > 0) deltaClass = 'positive';
            else if (d.delta_ms < 0) deltaClass = 'negative';

            // Fastest lap indicator
            const flIcon = d.is_fastest_lap ? ' 🟣' : '';

            // Team color bar
            const colorBar = `<span class="team-color-bar" style="background:${d.team_color}"></span>`;

            // Lap time
            const lapTimeClass = d.is_fastest_lap ? 'lap-time fastest' : 'lap-time';

            // Interval display
            let intervalDisplay = '—';
            if (d.position > 1 && d.delta_ms && data.drivers[d.position - 2]) {
                const carAhead = data.drivers[d.position - 2];
                const interval = (d.delta_ms - (carAhead.delta_ms || 0)) / 1000;
                if (interval > 0) intervalDisplay = `+${interval.toFixed(3)}s`;
            }

            // Determine row animation class
            let rowClass = '';
            const prevPos = previousPositions[d.abbreviation];
            if (prevPos !== undefined) {
                if (d.position < prevPos) rowClass = 'row-pos-up';
                else if (d.position > prevPos) rowClass = 'row-pos-down';
            }

            html += `
            <tr class="${rowClass}">
                <td class="pos">${d.position}${posChangeHtml}</td>
                <td class="driver-cell">${colorBar}<span class="driver-name">${d.abbreviation}</span>${flIcon}</td>
                <td class="team-name">${d.team}</td>
                <td class="${lapTimeClass}">${d.lap_time}</td>
                <td class="delta ${deltaClass}">${d.delta}</td>
                <td class="interval">${intervalDisplay}</td>
                <td class="tyre-cell">${tyreHtml}${tyreAge}</td>
                <td class="pit-count">${d.pit_stops}</td>
            </tr>`;

            // Track position
            previousPositions[d.abbreviation] = d.position;
        }

        standingsBody.innerHTML = html;
    }

    // ===== 3. INCIDENTS =====
    async function updateIncidents() {
        const data = await fetchJSON('/api/incidents/');
        if (!data || data.status !== 'ok') return;

        if (!data.incidents.length) {
            incidentsList.innerHTML = '<li class="incident-item incident-item--empty">Žádné incidenty</li>';
            return;
        }

        let html = '';
        for (const inc of data.incidents) {
            const badge = `<span class="incident-badge ${inc.type}">${inc.type}</span>`;
            const driver = inc.driver ? ` ${inc.driver}` : '';
            html += `<li class="incident-item">${badge}<span class="incident-lap">Kolo ${inc.lap}</span>${driver} – ${inc.description}</li>`;
        }
        incidentsList.innerHTML = html;
    }

    // ===== 4. LAP TIMES CHART =====
    async function updateLapTimesChart() {
        const data = await fetchJSON('/api/laptimes/');
        if (!data || data.status !== 'ok') return;

        const datasets = [];
        for (const [abbr, info] of Object.entries(data.data)) {
            datasets.push({
                label: abbr,
                data: info.laps.map((lap, i) => ({ x: lap, y: info.times[i] })),
                borderColor: info.color,
                backgroundColor: info.color + '33',
                borderWidth: 1.5,
                pointRadius: 0,
                pointHoverRadius: 4,
                tension: 0.2,
                fill: false,
            });
        }

        if (lapTimesChart) {
            lapTimesChart.data.datasets = datasets;
            lapTimesChart.update('none');
        } else {
            const ctx = $('#lap-times-chart').getContext('2d');
            lapTimesChart = new Chart(ctx, {
                type: 'line',
                data: { datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: { mode: 'nearest', intersect: false },
                    plugins: {
                        legend: {
                            labels: { color: '#9898b0', font: { size: 11, family: 'Inter' } }
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.dataset.label}: ${formatLapTime(ctx.parsed.y)}`
                            }
                        }
                    },
                    scales: {
                        x: {
                            type: 'linear',
                            title: { display: true, text: 'Kolo', color: '#9898b0' },
                            ticks: { color: '#5a5a72' },
                            grid: { color: '#2a2a3d' },
                        },
                        y: {
                            title: { display: true, text: 'Čas (s)', color: '#9898b0' },
                            ticks: {
                                color: '#5a5a72',
                                callback: (v) => formatLapTime(v),
                            },
                            grid: { color: '#2a2a3d' },
                        }
                    }
                }
            });
        }
    }

    // ===== 5. DRIVERS LIST =====
    async function loadDriversList() {
        const data = await fetchJSON('/api/drivers/');
        if (!data || data.status !== 'ok') return;

        let html = '<option value="">Vyberte jezdce</option>';
        for (const d of data.drivers) {
            const tel = d.has_telemetry ? '' : ' (bez telemetrie)';
            html += `<option value="${d.abbreviation}" ${!d.has_telemetry ? 'disabled' : ''}>${d.abbreviation} – ${d.full_name}${tel}</option>`;
        }
        driverSelect.innerHTML = html;
        driversLoaded = true;

        // Auto-select prvního s telemetrií
        if (!selectedDriver) {
            const first = data.drivers.find(d => d.has_telemetry);
            if (first) {
                selectedDriver = first.abbreviation;
                driverSelect.value = selectedDriver;
            }
        }
    }

    // ===== 6. TELEMETRY CHART =====
    async function updateTelemetry() {
        if (!selectedDriver) return;

        const data = await fetchJSON(`/api/telemetry/${selectedDriver}/`);
        if (!data || data.status !== 'ok' || !data.telemetry) return;

        const tel = data.telemetry;
        const distances = tel.distance;

        const datasets = [
            {
                label: 'Plyn (%)',
                data: distances.map((d, i) => ({ x: d, y: tel.throttle[i] })),
                borderColor: '#00e676',
                backgroundColor: '#00e67622',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: true,
                yAxisID: 'y',
            },
            {
                label: 'Brzda (%)',
                data: distances.map((d, i) => ({ x: d, y: (tel.brake[i] || 0) * 100 })),
                borderColor: '#e10600',
                backgroundColor: '#e1060022',
                borderWidth: 1.5,
                pointRadius: 0,
                fill: true,
                yAxisID: 'y',
            },
            {
                label: 'Rychlost (km/h)',
                data: distances.map((d, i) => ({ x: d, y: tel.speed[i] })),
                borderColor: '#2196f3',
                borderWidth: 1,
                pointRadius: 0,
                fill: false,
                yAxisID: 'y1',
            },
        ];

        // Aktualizuj title
        const title = `Telemetrie – ${data.driver_name || data.driver} | Kolo ${data.lap}`;
        const titleEl = $('#telemetry-card .panel__title');
        if (titleEl) titleEl.textContent = title;

        if (telemetryChart) {
            telemetryChart.data.datasets = datasets;
            telemetryChart.update('none');
        } else {
            const ctx = $('#telemetry-chart').getContext('2d');
            telemetryChart = new Chart(ctx, {
                type: 'line',
                data: { datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    interaction: { mode: 'nearest', intersect: false },
                    plugins: {
                        legend: {
                            labels: { color: '#9898b0', font: { size: 11, family: 'Inter' } }
                        }
                    },
                    scales: {
                        x: {
                            type: 'linear',
                            title: { display: true, text: 'Vzdálenost (m)', color: '#9898b0' },
                            ticks: { color: '#5a5a72' },
                            grid: { color: '#2a2a3d' },
                        },
                        y: {
                            position: 'left',
                            min: 0,
                            max: 105,
                            title: { display: true, text: 'Plyn / Brzda (%)', color: '#9898b0' },
                            ticks: { color: '#5a5a72' },
                            grid: { color: '#2a2a3d' },
                        },
                        y1: {
                            position: 'right',
                            min: 0,
                            title: { display: true, text: 'Rychlost (km/h)', color: '#9898b0' },
                            ticks: { color: '#5a5a72' },
                            grid: { drawOnChartArea: false },
                        }
                    }
                }
            });
        }
    }

    // ===== EVENT LISTENERS =====
    driverSelect.addEventListener('change', (e) => {
        selectedDriver = e.target.value;
        updateTelemetry();
    });

    // ===== HLAVNÍ SMYČKY =====

    // Aktualizace race/ranking/incidents/laptimes – každé 3s
    async function mainLoop() {
        await updateRaceInfo();
        await updateRanking();
        await updateIncidents();
        await updateLapTimesChart();

        if (!driversLoaded) {
            await loadDriversList();
        }
    }

    // Telemetrie – každých 1.5s
    async function telemetryLoop() {
        await updateTelemetry();
    }

    // Počáteční načtení
    mainLoop();
    telemetryLoop();

    // Intervaly
    setInterval(mainLoop, 3000);
    setInterval(telemetryLoop, 1500);

    console.log('🏎️ F1 Live Dashboard – live aktualizace spuštěny');
});
