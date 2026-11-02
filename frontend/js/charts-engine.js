/**
 * AgriSmoke AI - Standalone SVG & Canvas Chart Engine
 * 
 * High-performance, zero-dependency data visualization engine:
 * 1. 24-Hour Diurnal AQI & Smoke Plume Forecast Curve
 * 2. 7-Day Air Quality & Fire Trajectory Chart
 * 3. Source Apportionment Donut Chart
 * 4. District-wise Fire Count Bar Chart
 * 5. Radial AQI Dial / Speedometer Gauge
 */

class AgriSmokeChartsEngine {
    constructor() {
        this.tooltipEl = document.getElementById('chart-tooltip');
    }

    /**
     * Render 24-Hour Diurnal AQI & Stubble Contribution Forecast Chart
     */
    renderDiurnalChart(containerId, hourlyData) {
        const container = document.getElementById(containerId);
        if (!container || !hourlyData || !hourlyData.length) return;

        const width = container.clientWidth || 640;
        const height = 240;
        const margin = { top: 25, right: 30, bottom: 35, left: 45 };
        const chartW = width - margin.left - margin.right;
        const chartH = height - margin.top - margin.bottom;

        // Min & Max AQI
        const maxAqi = Math.max(500, Math.ceil(Math.max(...hourlyData.map(d => d.aqi)) * 1.1 / 50) * 50);
        const minAqi = 0;

        const xStep = chartW / (hourlyData.length - 1);
        const getY = (val) => margin.top + chartH - ((val - minAqi) / (maxAqi - minAqi)) * chartH;

        // Points for AQI line
        const aqiPoints = hourlyData.map((d, i) => ({
            x: margin.left + i * xStep,
            y: getY(d.aqi),
            data: d
        }));

        const aqiPathD = aqiPoints.reduce((acc, pt, idx) => {
            return idx === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`;
        }, "");

        const aqiAreaD = `${aqiPathD} L ${margin.left + (hourlyData.length - 1) * xStep} ${margin.top + chartH} L ${margin.left} ${margin.top + chartH} Z`;

        // SVG markup
        let svg = `
        <svg viewBox="0 0 ${width} ${height}" class="chart-svg" style="width:100%;height:100%;">
            <defs>
                <linearGradient id="aqiAreaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#ff3d00" stop-opacity="0.45"/>
                    <stop offset="70%" stop-color="#ff9100" stop-opacity="0.12"/>
                    <stop offset="100%" stop-color="#ffd600" stop-opacity="0.0"/>
                </linearGradient>
                <linearGradient id="aqiLineGrad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stop-color="#ff9100"/>
                    <stop offset="50%" stop-color="#ff3d00"/>
                    <stop offset="100%" stop-color="#d50000"/>
                </linearGradient>
            </defs>

            <!-- Background Grid & Threshold Bands -->
            <rect x="${margin.left}" y="${getY(500)}" width="${chartW}" height="${Math.max(0, getY(400) - getY(500))}" fill="rgba(74, 20, 140, 0.08)" />
            <rect x="${margin.left}" y="${getY(400)}" width="${chartW}" height="${getY(300) - getY(400)}" fill="rgba(213, 0, 0, 0.08)" />
            <rect x="${margin.left}" y="${getY(300)}" width="${chartW}" height="${getY(200) - getY(300)}" fill="rgba(255, 61, 0, 0.05)" />
            <rect x="${margin.left}" y="${getY(200)}" width="${chartW}" height="${getY(100) - getY(200)}" fill="rgba(255, 214, 0, 0.03)" />

            <!-- Y Axis Grid Lines -->
            ${[100, 200, 300, 400, 500].map(val => {
                const y = getY(val);
                return `
                    <line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e2e8f0" stroke-dasharray="3,3"/>
                    <text x="${margin.left - 8}" y="${y + 4}" fill="#64748b" font-size="10" text-anchor="end" font-family="monospace">${val}</text>
                `;
            }).join('')}

            <!-- Area & Line -->
            <path d="${aqiAreaD}" fill="url(#aqiAreaGrad)"/>
            <path d="${aqiPathD}" fill="none" stroke="url(#aqiLineGrad)" stroke-width="2.6" stroke-linecap="round"/>

            <!-- X Axis Ticks & Time Labels (Every 3 hours) -->
            ${hourlyData.map((d, i) => {
                if (i % 3 !== 0 && i !== hourlyData.length - 1) return '';
                const x = margin.left + i * xStep;
                return `
                    <line x1="${x}" y1="${margin.top + chartH}" x2="${x}" y2="${margin.top + chartH + 5}" stroke="#cbd5e1"/>
                    <text x="${x}" y="${margin.top + chartH + 18}" fill="#64748b" font-size="10" text-anchor="middle">${d.time}</text>
                `;
            }).join('')}

            <!-- Data Point Circles (Interactive) -->
            ${aqiPoints.map((pt, idx) => `
                <circle cx="${pt.x}" cy="${pt.y}" r="3.5" fill="#ffffff" stroke="#ff3d00" stroke-width="2" class="chart-point"
                    data-chart-tooltip="Time: <strong>${pt.data.time}</strong><br>Predicted AQI: <strong style='color:${pt.data.color || '#ff3d00'}'>${pt.data.aqi}</strong> (${pt.data.category || 'Very Poor'})<br>PM2.5: <strong>${pt.data.pm25} µg/m³</strong><br>Stubble Smoke Contribution: <strong>${pt.data.stubblePct}%</strong>"
                />
            `).join('')}
        </svg>`;

        container.innerHTML = svg;
        this.attachPointTooltips(container);
    }

    /**
     * Render 7-Day Trend Bar & Line Chart
     */
    renderWeeklyTrendChart(containerId, weeklyData) {
        const container = document.getElementById(containerId);
        if (!container || !weeklyData || !weeklyData.length) return;

        const width = container.clientWidth || 460;
        const height = 230;
        const margin = { top: 20, right: 35, bottom: 35, left: 45 };
        const chartW = width - margin.left - margin.right;
        const chartH = height - margin.top - margin.bottom;

        const maxAqi = 450;
        const maxFires = 2000;

        const colWidth = chartW / weeklyData.length;
        const barW = Math.max(16, colWidth * 0.45);

        let svg = `
        <svg viewBox="0 0 ${width} ${height}" class="chart-svg" style="width:100%;height:100%;">
            <!-- Left Y Axis (AQI) lines -->
            ${[100, 200, 300, 400].map(val => {
                const y = margin.top + chartH - (val / maxAqi) * chartH;
                return `
                    <line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e2e8f0"/>
                    <text x="${margin.left - 6}" y="${y + 4}" fill="#64748b" font-size="9" text-anchor="end" font-family="monospace">${val}</text>
                `;
            }).join('')}

            <!-- Bars: Active Farm Fires -->
            ${weeklyData.map((d, i) => {
                const x = margin.left + i * colWidth + (colWidth - barW) / 2;
                const barH = (d.fires / maxFires) * chartH;
                const y = margin.top + chartH - barH;
                return `
                    <rect x="${x}" y="${y}" width="${barW}" height="${barH}" rx="3" fill="#ea580c" opacity="0.8" class="chart-bar"
                        data-chart-tooltip="<strong>${d.day}</strong><br>Active Stubble Fires: <strong style='color:#ea580c'>${d.fires}</strong><br>Urban AQI: <strong>${d.aqi}</strong><br>GRAP Trigger: <strong>${d.grapStage}</strong>"
                    />
                `;
            }).join('')}

            <!-- Line: Urban AQI -->
            ${(() => {
                const pts = weeklyData.map((d, i) => {
                    const x = margin.left + i * colWidth + colWidth / 2;
                    const y = margin.top + chartH - (d.aqi / maxAqi) * chartH;
                    return { x, y, d };
                });
                const pathD = pts.reduce((acc, pt, idx) => idx === 0 ? `M ${pt.x} ${pt.y}` : `${acc} L ${pt.x} ${pt.y}`, "");
                return `
                    <path d="${pathD}" fill="none" stroke="#0284c7" stroke-width="2.4"/>
                    ${pts.map(pt => `
                        <circle cx="${pt.x}" cy="${pt.y}" r="4" fill="#ffffff" stroke="#0284c7" stroke-width="2"/>
                    `).join('')}
                `;
            })()}

            <!-- X Axis Labels -->
            ${weeklyData.map((d, i) => {
                const x = margin.left + i * colWidth + colWidth / 2;
                return `
                    <text x="${x}" y="${margin.top + chartH + 18}" fill="#64748b" font-size="9" text-anchor="middle">${d.day.split(' ')[0] + ' ' + (d.day.split(' ')[1] || '')}</text>
                `;
            }).join('')}
        </svg>`;

        container.innerHTML = svg;
        this.attachPointTooltips(container);
    }

    /**
     * Render 72-Hour Airshed Dispersion Outlook (line + 90% confidence band)
     * hourly: [{ time, aqi, aqiLower, aqiUpper, category, windSpeed, pbl, dayIndex }]
     */
    renderHourlyForecastChart(containerId, hourly) {
        const container = document.getElementById(containerId);
        if (!container || !hourly || !hourly.length) {
            if (container) container.innerHTML = '<div style="color:#64748b;font-size:12px;padding:12px;">No forecast data available.</div>';
            return;
        }

        const width = container.clientWidth || 720;
        const height = 240;
        const margin = { top: 16, right: 18, bottom: 30, left: 44 };
        const chartW = width - margin.left - margin.right;
        const chartH = height - margin.top - margin.bottom;
        const n = hourly.length;

        const upVals = hourly.map(h => h.aqiUpper || h.aqi);
        const yMax = Math.max(500, Math.ceil(Math.max(...upVals) / 100) * 100);
        const xAt = (i) => margin.left + (n > 1 ? (i / (n - 1)) * chartW : 0);
        const yAt = (v) => margin.top + chartH - (Math.min(v, yMax) / yMax) * chartH;

        const bandPath =
            hourly.map((h, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i).toFixed(1)} ${yAt(h.aqiUpper || h.aqi).toFixed(1)}`).join(' ') +
            ' ' +
            hourly.slice().reverse().map((h, j) => { const i = n - 1 - j; return `L ${xAt(i).toFixed(1)} ${yAt(h.aqiLower != null ? h.aqiLower : h.aqi).toFixed(1)}`; }).join(' ') +
            ' Z';

        const linePath = hourly.map((h, i) => `${i === 0 ? 'M' : 'L'} ${xAt(i).toFixed(1)} ${yAt(h.aqi).toFixed(1)}`).join(' ');

        const gridVals = [0.25, 0.5, 0.75, 1].map(f => Math.round(yMax * f));

        // Build a tooltip that adapts to airshed (has band/wind/pbl) vs per-city (pm2.5 only) data
        const tooltipFor = (h) => {
            let t = `<strong>${h.time || ''}</strong><br>AQI: <strong style='color:#0284c7'>${h.aqi}</strong>`;
            if (h.category) t += ` (${h.category})`;
            if (h.aqiLower != null && h.aqiUpper != null) t += `<br>Range: ${h.aqiLower}&ndash;${h.aqiUpper}`;
            if (h.windSpeed != null && h.pbl != null) t += `<br>Wind: ${h.windSpeed} km/h &bull; PBL: ${h.pbl} m`;
            else if (h.pm25 != null) t += `<br>PM2.5: ${h.pm25} \u00b5g/m\u00b3`;
            return t;
        };

        let svg = `
        <svg viewBox="0 0 ${width} ${height}" class="chart-svg" style="width:100%;height:100%;">
            ${gridVals.map(val => {
                const y = yAt(val);
                return `<line x1="${margin.left}" y1="${y}" x2="${width - margin.right}" y2="${y}" stroke="#e2e8f0"/>
                        <text x="${margin.left - 6}" y="${y + 4}" fill="#64748b" font-size="9" text-anchor="end" font-family="monospace">${val}</text>`;
            }).join('')}

            <!-- Day separators at 24h and 48h -->
            ${[24, 48].map(i => i < n ? `<line x1="${xAt(i)}" y1="${margin.top}" x2="${xAt(i)}" y2="${margin.top + chartH}" stroke="#cbd5e1" stroke-dasharray="3 3"/>` : '').join('')}

            <path d="${bandPath}" fill="#0284c7" opacity="0.12"/>
            <path d="${linePath}" fill="none" stroke="#0284c7" stroke-width="2.2"/>

            ${hourly.map((h, i) => i % 3 === 0 ? `<circle cx="${xAt(i)}" cy="${yAt(h.aqi)}" r="2.6" fill="#ffffff" stroke="#0284c7" stroke-width="1.6"
                data-chart-tooltip="${tooltipFor(h)}"
            />` : '').join('')}

            <!-- X axis labels -->
            ${[[0, 'Now'], [24, '+24h'], [48, '+48h'], [n - 1, '+72h']].map(([i, lbl]) =>
                `<text x="${xAt(i)}" y="${margin.top + chartH + 18}" fill="#64748b" font-size="9" text-anchor="middle">${lbl}</text>`).join('')}
        </svg>`;

        container.innerHTML = svg;
        this.attachPointTooltips(container);
    }

    /**
     * Render Source Apportionment Donut Chart
     */
    renderSourceDonut(containerId, sources) {
        const container = document.getElementById(containerId);
        if (!container || !sources) return;

        const size = Math.min(container.clientWidth || 220, 220);
        const radius = size / 2;
        const innerRadius = radius * 0.62;

        let cumulativePct = 0;
        const total = sources.reduce((sum, s) => sum + s.percentage, 0);

        const arcs = sources.map(s => {
            const startPct = cumulativePct;
            cumulativePct += s.percentage;
            const endPct = cumulativePct;

            const startAngle = (startPct / total) * Math.PI * 2 - Math.PI / 2;
            const endAngle = (endPct / total) * Math.PI * 2 - Math.PI / 2;

            const x1 = radius + radius * Math.cos(startAngle);
            const y1 = radius + radius * Math.sin(startAngle);
            const x2 = radius + radius * Math.cos(endAngle);
            const y2 = radius + radius * Math.sin(endAngle);

            const ix1 = radius + innerRadius * Math.cos(endAngle);
            const iy1 = radius + innerRadius * Math.sin(endAngle);
            const ix2 = radius + innerRadius * Math.cos(startAngle);
            const iy2 = radius + innerRadius * Math.sin(startAngle);

            const largeArc = (endAngle - startAngle) > Math.PI ? 1 : 0;

            const d = `
                M ${x1} ${y1}
                A ${radius} ${radius} 0 ${largeArc} 1 ${x2} ${y2}
                L ${ix1} ${iy1}
                A ${innerRadius} ${innerRadius} 0 ${largeArc} 0 ${ix2} ${iy2}
                Z
            `;

            return { d, color: s.color, source: s };
        });

        const stubbleSource = sources.find(s => s.source.includes("Stubble") || s.source.includes("Crop")) || sources[0];

        let svg = `
        <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;justify-content:center;">
            <div style="position:relative;width:${size}px;height:${size}px;">
                <svg viewBox="0 0 ${size} ${size}" style="width:100%;height:100%;">
                    ${arcs.map(arc => `
                        <path d="${arc.d}" fill="${arc.color}" class="donut-slice"
                            data-chart-tooltip="<strong>${arc.source.source}</strong>: <strong style='color:${arc.color}'>${arc.source.percentage}%</strong><br><span style='font-size:11px'>${arc.source.description}</span>"
                            style="transition:transform 0.2s;cursor:pointer;"
                        />
                    `).join('')}
                </svg>
                <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;">
                    <div style="font-size:24px;font-weight:700;color:${stubbleSource.color};line-height:1">${stubbleSource.percentage}%</div>
                    <div style="font-size:10px;color:#64748b;margin-top:2px;text-transform:uppercase;letter-spacing:0.5px">Parali Smoke</div>
                </div>
            </div>
            <div class="donut-legend" style="flex:1;min-width:180px;">
                ${sources.map(s => `
                    <div class="legend-row" style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:12px;">
                        <span style="display:flex;align-items:center;gap:8px;">
                            <span style="width:10px;height:10px;border-radius:2px;background:${s.color};display:inline-block;"></span>
                            <span style="color:#334155;">${s.source}</span>
                        </span>
                        <strong style="color:${s.color};">${s.percentage}%</strong>
                    </div>
                `).join('')}
            </div>
        </div>`;

        container.innerHTML = svg;
        this.attachPointTooltips(container);
    }

    /**
     * Render District-level Fire Count Horizontal Bar Chart
     */
    renderDistrictBars(containerId, districtData) {
        const container = document.getElementById(containerId);
        if (!container || !districtData) return;

        const maxFires = Math.max(...districtData.map(d => d.fires));

        let html = `
        <div class="district-bars-list" style="display:flex;flex-direction:column;gap:10px;">
            ${districtData.map(d => {
                const pct = Math.round((d.fires / maxFires) * 100);
                const isPunjab = d.state === "Punjab";
                const barColor = isPunjab ? "#ea580c" : "#ca8a04";
                return `
                    <div class="district-bar-item" style="display:flex;align-items:center;gap:12px;font-size:12px;">
                        <div style="width:90px;font-weight:500;color:#334155;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${d.district}</div>
                        <div style="flex:1;height:14px;background:#f1f5f9;border:1px solid #e2e8f0;border-radius:3px;overflow:hidden;position:relative;">
                            <div style="width:${pct}%;height:100%;background:${barColor};border-radius:3px;transition:width 0.6s ease;"></div>
                        </div>
                        <div style="width:55px;text-align:right;font-family:monospace;font-weight:600;color:#0f172a;">
                            ${d.fires} <span style="font-size:10px;color:#64748b">${isPunjab ? 'PB' : 'HR'}</span>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>`;

        container.innerHTML = html;
    }

    /**
     * Render Radial Gauge / Speedometer for AQI
     */
    renderAqiSpeedometer(containerId, aqi, maxAqi = 500) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const roundAqi = Math.round(aqi);
        const clampedAqi = Math.max(0, Math.min(maxAqi, roundAqi));

        // Determine CPCB category and color
        let category = "Good";
        let catColor = "#00e676";
        if (roundAqi > 400) {
            category = "Severe";
            catColor = "#d50000";
        } else if (roundAqi > 300) {
            category = "Very Poor";
            catColor = "#ff3d00";
        } else if (roundAqi > 200) {
            category = "Poor";
            catColor = "#ff9100";
        } else if (roundAqi > 100) {
            category = "Moderate";
            catColor = "#ffd600";
        } else if (roundAqi > 50) {
            category = "Satisfactory";
            catColor = "#aeea00";
        }

        const width = 280;
        const height = 210;
        const cx = 140;
        const cy = 135;
        const radius = 95;

        // CPCB Tiers on 0 - 500 scale
        const tiers = [
            { min: 0, max: 50, color: "#00e676" },
            { min: 50, max: 100, color: "#aeea00" },
            { min: 100, max: 200, color: "#ffd600" },
            { min: 200, max: 300, color: "#ff9100" },
            { min: 300, max: 400, color: "#ff3d00" },
            { min: 400, max: 500, color: "#d50000" }
        ];

        // Base Dark Track
        const bgTrackD = `M ${cx - radius} ${cy} A ${radius} ${radius} 0 0 1 ${cx + radius} ${cy}`;

        // Colored tier arc segments
        const arcPaths = tiers.map(t => {
            const a1 = -Math.PI + (t.min / maxAqi) * Math.PI;
            const a2 = -Math.PI + (t.max / maxAqi) * Math.PI;
            const x1 = (cx + radius * Math.cos(a1)).toFixed(1);
            const y1 = (cy + radius * Math.sin(a1)).toFixed(1);
            const x2 = (cx + radius * Math.cos(a2)).toFixed(1);
            const y2 = (cy + radius * Math.sin(a2)).toFixed(1);

            return `<path d="M ${x1} ${y1} A ${radius} ${radius} 0 0 1 ${x2} ${y2}"
                fill="none" stroke="${t.color}" stroke-width="14" stroke-linecap="butt" opacity="0.9"
            />`;
        }).join('');

        // Ticks and scale labels around the perimeter
        const ticks = [
            { val: 0, label: "0", anchor: "end", dx: -6, dy: 4 },
            { val: 100, label: "100", anchor: "end", dx: -4, dy: -2 },
            { val: 200, label: "200", anchor: "middle", dx: 0, dy: -6 },
            { val: 300, label: "300", anchor: "middle", dx: 0, dy: -6 },
            { val: 400, label: "400", anchor: "start", dx: 4, dy: -2 },
            { val: 500, label: "500+", anchor: "start", dx: 6, dy: 4 }
        ];

        const tickElements = ticks.map(t => {
            const angle = -Math.PI + (t.val / maxAqi) * Math.PI;
            const cos = Math.cos(angle);
            const sin = Math.sin(angle);

            const tx1 = (cx + (radius + 8) * cos).toFixed(1);
            const ty1 = (cy + (radius + 8) * sin).toFixed(1);
            const tx2 = (cx + (radius + 14) * cos).toFixed(1);
            const ty2 = (cy + (radius + 14) * sin).toFixed(1);

            const lx = (cx + (radius + 24) * cos + t.dx).toFixed(1);
            const ly = (cy + (radius + 24) * sin + t.dy).toFixed(1);

            return `
                <line x1="${tx1}" y1="${ty1}" x2="${tx2}" y2="${ty2}" stroke="#cbd5e1" stroke-width="1.5" />
                <text x="${lx}" y="${ly}" fill="#64748b" font-size="9" font-family="monospace" text-anchor="${t.anchor}">${t.label}</text>
            `;
        }).join('');

        // Needle calculations
        const needleAngleRad = -Math.PI + (clampedAqi / maxAqi) * Math.PI;
        const needleLen = radius - 18;
        const nx = (cx + needleLen * Math.cos(needleAngleRad)).toFixed(1);
        const ny = (cy + needleLen * Math.sin(needleAngleRad)).toFixed(1);

        let svg = `
        <svg viewBox="0 0 ${width} ${height}" style="width:100%;max-width:280px;height:auto;display:block;margin:0 auto;overflow:visible;">
            <defs>
                <filter id="gaugeNeedleGlow" x="-20%" y="-20%" width="140%" height="140%">
                    <feDropShadow dx="0" dy="1" stdDeviation="2" flood-color="#000000" flood-opacity="0.25"/>
                </filter>
            </defs>

            <!-- Base Light Arc Track -->
            <path d="${bgTrackD}" fill="none" stroke="#f1f5f9" stroke-width="14" stroke-linecap="butt" />

            <!-- Colored CPCB Segments -->
            ${arcPaths}

            <!-- Scale Ticks and Labels -->
            ${tickElements}

            <!-- Dynamic Gauge Needle -->
            <line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="#0f172a" stroke-width="3.5" stroke-linecap="round" filter="url(#gaugeNeedleGlow)"/>
            <circle cx="${cx}" cy="${cy}" r="7.5" fill="#0f172a"/>
            <circle cx="${cx}" cy="${cy}" r="4" fill="#ffffff"/>

            <!-- Center Live AQI Readout -->
            <text x="${cx}" y="${cy + 34}" fill="${catColor}" font-size="28" font-weight="800" font-family="monospace" text-anchor="middle">${roundAqi}</text>
            <text x="${cx}" y="${cy + 50}" fill="${catColor}" font-size="11" font-weight="700" letter-spacing="1" text-anchor="middle">${category.toUpperCase()}</text>
            <text x="${cx}" y="${cy + 66}" fill="#64748b" font-size="9.5" text-anchor="middle">CPCB Standard &bull; 0–500 Scale</text>
        </svg>`;

        container.innerHTML = svg;
    }

    attachPointTooltips(container) {
        const tooltip = this.tooltipEl || document.getElementById('chart-tooltip');
        if (!tooltip) return;

        container.querySelectorAll('[data-chart-tooltip]').forEach(el => {
            el.addEventListener('mouseenter', (e) => {
                tooltip.innerHTML = el.getAttribute('data-chart-tooltip');
                tooltip.style.display = 'block';
            });
            el.addEventListener('mousemove', (e) => {
                tooltip.style.left = `${e.pageX + 12}px`;
                tooltip.style.top = `${e.pageY - 28}px`;
            });
            el.addEventListener('mouseleave', () => {
                tooltip.style.display = 'none';
            });
        });
    }
}

// Make available globally
window.AgriSmokeChartsEngine = AgriSmokeChartsEngine;
