/**
 * AgriSmoke AI - High-Fidelity Interactive Geospatial Canvas & Plume Engine
 * 
 * Fully self-contained local map engine with real coordinate projection,
 * active fire thermal anomalies, animated smoke plume dispersion particles,
 * and Delhi-NCR urban air monitoring stations.
 * 
 * Works 100% offline in Edge file:/// mode with zero external CDN dependencies.
 */

class AgriSmokeMapEngine {
    constructor(canvasId, containerId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.container = document.getElementById(containerId);

        // Geographic Bounding Box (Indo-Gangetic Plain: Punjab, Haryana, Delhi, Western UP)
        this.geoBounds = {
            minLat: 27.8, // South of Delhi/NCR
            maxLat: 32.6, // North Punjab & Himalayan foothills
            minLng: 73.8, // West Punjab border (near Fazilka/Firozpur)
            maxLng: 78.8  // East UP (Meerut, Aligarh)
        };

        // Pan and Zoom viewport state
        this.scale = 1.0;
        this.panX = 0;
        this.panY = 0;
        this.isDragging = false;
        this.dragStartX = 0;
        this.dragStartY = 0;

        // Visual Layer toggles
        this.layers = {
            fires: true,
            plumeParticles: true,
            windVectors: true,
            stations: true,
            boundaries: true
        };

        // Smoke Plume Particle System
        this.particles = [];
        this.maxParticles = 320;
        this.windSpeed = 11.5;
        this.windAngleRad = (305 * Math.PI) / 180; // 305 deg (NW blowing toward SE)

        // Active selection / hover
        this.hoveredItem = null;
        this.selectedItem = null;

        // NASA FIRMS Satellite Observations & Live Telemetry
        this.fireObservations = [];
        this.filteredObservations = [];
        this.currentClassFilter = 'all';

        // Tooltip element
        this.tooltip = document.getElementById('map-tooltip');

        // Delhi-NCR impact target (kept in sync from app.js via setTarget)
        this.targetAqi = null;
        this.targetColor = null;

        this.init();
    }

    setObservations(obsList) {
        if (!obsList || !Array.isArray(obsList)) return;
        this.fireObservations = obsList;
        this.applyClassFilter();
        // Re-initialize smoke plume particles from real observation centroids
        this.initParticles();
    }

    setClassFilter(filterValue) {
        this.currentClassFilter = filterValue || 'all';
        this.applyClassFilter();
    }

    applyClassFilter() {
        if (this.currentClassFilter === 'all') {
            this.filteredObservations = this.fireObservations.slice();
        } else {
            this.filteredObservations = this.fireObservations.filter(o => 
                (o.classification || '').toLowerCase() === this.currentClassFilter.toLowerCase()
            );
        }
    }

    init() {
        this.resize();
        window.addEventListener('resize', () => this.resize());
        this.setupEventHandlers();
        this.initParticles();
        this.startAnimationLoop();
    }

    resize() {
        const parent = this.canvas.parentElement;
        const rect = parent ? parent.getBoundingClientRect() : null;
        let w = (rect && rect.width > 100) ? rect.width : (parent ? parent.clientWidth : 0);
        if (!w || w < 100) {
            // Container or parent may be in an inactive tab; use map-container or window width fallback
            const mapContainer = document.getElementById('map-container');
            w = (mapContainer && mapContainer.clientWidth > 100)
                ? mapContainer.clientWidth
                : (window.innerWidth ? Math.min(1440, Math.max(700, window.innerWidth - 64)) : 1080);
        }
        let h = (rect && rect.height > 200) ? rect.height : (parent ? parent.clientHeight : 0);
        if (!h || h < 200) {
            h = 580;
        }

        this.width = Math.max(600, w);
        this.height = Math.max(480, h);

        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = Math.round(this.width * dpr);
        this.canvas.height = Math.round(this.height * dpr);
        this.canvas.style.width = `${this.width}px`;
        this.canvas.style.height = `${this.height}px`;

        // CRITICAL: Always reset transformation matrix before scaling to avoid cumulative DPR compounding!
        this.ctx.setTransform(1, 0, 0, 1, 0, 0);
        this.ctx.scale(dpr, dpr);

        // If particles have not been created or were spawned with zero width, re-initialize them
        if (!this.particles || this.particles.length === 0 || !this.particles[0] || isNaN(this.particles[0].spreadOffset)) {
            this.initParticles();
        }
    }

    reinitParticles() {
        this.initParticles();
    }

    // Convert Lat/Lng to Screen Canvas coordinates
    geoToScreen(lat, lng) {
        const normX = (lng - this.geoBounds.minLng) / (this.geoBounds.maxLng - this.geoBounds.minLng);
        // Invert Y because latitude increases northward while canvas Y increases downward
        const normY = 1.0 - ((lat - this.geoBounds.minLat) / (this.geoBounds.maxLat - this.geoBounds.minLat));

        const baseMargin = 40;
        const availWidth = this.width - baseMargin * 2;
        const availHeight = this.height - baseMargin * 2;

        const rawX = baseMargin + normX * availWidth;
        const rawY = baseMargin + normY * availHeight;

        // Apply Pan & Zoom
        const centerX = this.width / 2;
        const centerY = this.height / 2;

        const screenX = centerX + (rawX - centerX + this.panX) * this.scale;
        const screenY = centerY + (rawY - centerY + this.panY) * this.scale;

        return { x: screenX, y: screenY };
    }

    initParticles() {
        this.particles = [];
        for (let i = 0; i < this.maxParticles; i++) {
            this.particles.push(this.spawnParticle(true));
        }
    }

    spawnParticle(randomLifetime = false) {
        let originLat, originLng, sourceId;
        if (this.filteredObservations && this.filteredObservations.length > 0) {
            const obs = this.filteredObservations[Math.floor(Math.random() * this.filteredObservations.length)];
            originLat = obs.latitude;
            originLng = obs.longitude;
            sourceId = obs.id;
        } else {
            const hotspots = DEMO_DATA.fireHotspots;
            const source = hotspots[Math.floor(Math.random() * hotspots.length)];
            originLat = source.lat;
            originLng = source.lng;
            sourceId = source.id;
        }
        const origin = this.geoToScreen(originLat, originLng);

        const progress = randomLifetime ? Math.random() : 0;
        const life = 140 + Math.random() * 100;

        return {
            sourceId: sourceId,
            originLat: originLat,
            originLng: originLng,
            age: progress * life,
            maxLife: life,
            spreadOffset: (Math.random() - 0.5) * 24, // Lateral dispersion
            radius: 2 + Math.random() * 3,
            alpha: 0.15 + Math.random() * 0.35
        };
    }

    updateWind(speed, directionDeg) {
        this.windSpeed = speed;
        // DirectionDeg is where wind is coming FROM. Smoke travels in direction TOWARD (dir + 180)
        // Convert to standard math radians where 0 is East, 90 is South (canvas Y is down)
        const travelDirDeg = (directionDeg + 180) % 360;
        // Compass 0 is North (canvas -Y), 90 is East (+X), 180 is South (+Y), 270 is West (-X)
        const rad = ((travelDirDeg - 90) * Math.PI) / 180;
        this.windAngleRad = rad;
    }

    setupEventHandlers() {
        this.canvas.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.dragStartX = e.clientX - this.panX;
            this.dragStartY = e.clientY - this.panY;
            this.canvas.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            if (this.isDragging) {
                this.panX = e.clientX - this.dragStartX;
                this.panY = e.clientY - this.dragStartY;
            } else if (mouseX >= 0 && mouseX <= this.width && mouseY >= 0 && mouseY <= this.height) {
                this.checkHover(mouseX, mouseY);
            }
        });

        window.addEventListener('mouseup', () => {
            if (this.isDragging) {
                this.isDragging = false;
                this.canvas.style.cursor = 'default';
            }
        });

        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const zoomDelta = e.deltaY < 0 ? 1.15 : 0.87;
            this.setZoom(this.scale * zoomDelta);
        });

        this.canvas.addEventListener('click', (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            this.handleClick(mouseX, mouseY);
        });

        // Zoom button controls
        document.getElementById('map-zoom-in')?.addEventListener('click', () => this.setZoom(this.scale * 1.25));
        document.getElementById('map-zoom-out')?.addEventListener('click', () => this.setZoom(this.scale * 0.8));
        document.getElementById('map-reset')?.addEventListener('click', () => this.resetView());

        // Layer toggles
        document.querySelectorAll('[data-map-layer]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const layer = btn.getAttribute('data-map-layer');
                this.layers[layer] = !this.layers[layer];
                btn.classList.toggle('active', this.layers[layer]);
            });
        });
    }

    setZoom(newScale) {
        this.scale = Math.max(0.65, Math.min(3.8, newScale));
    }

    resetView() {
        this.scale = 1.0;
        this.panX = 0;
        this.panY = 0;
    }

    checkHover(screenX, screenY) {
        let found = null;

        // Check Stations
        if (this.layers.stations) {
            for (let st of DEMO_DATA.monitoringStations) {
                const pos = this.geoToScreen(st.lat, st.lng);
                const dist = Math.hypot(screenX - pos.x, screenY - pos.y);
                if (dist <= 14) {
                    found = { type: 'station', data: st, x: pos.x, y: pos.y };
                    break;
                }
            }
        }

        // Check NASA Satellite Observations
        if (!found && this.layers.fires && this.filteredObservations && this.filteredObservations.length > 0) {
            for (let obs of this.filteredObservations) {
                const pos = this.geoToScreen(obs.latitude, obs.longitude);
                const dist = Math.hypot(screenX - pos.x, screenY - pos.y);
                if (dist <= 14) {
                    found = { type: 'firms_obs', data: obs, x: pos.x, y: pos.y };
                    break;
                }
            }
        }

        // Check Fire Hotspots (Fallback)
        if (!found && this.layers.fires) {
            for (let fire of DEMO_DATA.fireHotspots) {
                const pos = this.geoToScreen(fire.lat, fire.lng);
                const dist = Math.hypot(screenX - pos.x, screenY - pos.y);
                if (dist <= 16) {
                    found = { type: 'fire', data: fire, x: pos.x, y: pos.y };
                    break;
                }
            }
        }

        this.hoveredItem = found;
        this.updateTooltip();
    }

    handleClick(screenX, screenY) {
        if (this.hoveredItem) {
            this.selectedItem = this.hoveredItem;
            // Dispatch custom event for UI panels
            const event = new CustomEvent('map-item-selected', { detail: this.selectedItem });
            window.dispatchEvent(event);
        }
    }

    updateTooltip() {
        if (!this.tooltip) return;

        if (!this.hoveredItem) {
            this.tooltip.style.display = 'none';
            return;
        }

        const item = this.hoveredItem;
        this.tooltip.style.display = 'block';
        this.tooltip.style.left = `${item.x + 16}px`;
        this.tooltip.style.top = `${item.y - 12}px`;

        if (item.type === 'station') {
            const st = item.data;
            this.tooltip.innerHTML = `
                <div class="tooltip-header station">
                    <span class="badge aqi-badge" style="background:${this.getAqiColor(st.aqi)}">${st.aqi} AQI</span>
                    <strong>${st.name}</strong>
                </div>
                <div class="tooltip-body">
                    <div>Type: <span>${st.type}</span></div>
                    <div>PM2.5: <strong>${st.pm25} µg/m³</strong> | PM10: <strong>${st.pm10}</strong></div>
                    <div>Parali Smoke Contribution: <strong style="color:#ff7043">${st.paraliPct}%</strong></div>
                    <div class="hint">Click to inspect monitoring station details</div>
                </div>
            `;
        } else if (item.type === 'firms_obs') {
            const obs = item.data;
            const isAgri = obs.classification === 'agricultural';
            const badgeColor = isAgri ? '#ea580c' : (obs.classification === 'industrial' ? '#8b5cf6' : '#10b981');
            const classLabel = isAgri ? '🌾 Agricultural Stubble Burning' : (obs.classification === 'industrial' ? '🏭 Industrial Heat Anomaly' : '🌲 Forest / Wildland');
            const confPct = Math.round((obs.confidence_normalized || obs.confidence_score || 0.65) * 100);

            this.tooltip.innerHTML = `
                <div class="tooltip-header fire" style="border-left: 4px solid ${badgeColor};">
                    <span class="badge" style="background:${badgeColor};color:#fff;">${classLabel}</span>
                    <strong>${obs.district || 'Regional Airshed'}, ${obs.state || 'India'}</strong>
                </div>
                <div class="tooltip-body">
                    <div>Satellite Platform: <strong>${obs.satellite} (${obs.instrument || 'VIIRS'})</strong></div>
                    <div>Fire Radiative Power (FRP): <strong style="color:#ef4444">${obs.frp} MW</strong></div>
                    <div>Detection Confidence: <strong>${confPct}% (${obs.confidence_raw || obs.confidence || 'Nominal'})</strong></div>
                    <div>Acquisition UTC: <span>${obs.acquisition_timestamp || (obs.acq_date + ' ' + obs.acq_time)}</span></div>
                    <div>Coordinates: <span style="font-family:monospace;font-size:11px;">${obs.latitude.toFixed(4)}°N, ${obs.longitude.toFixed(4)}°E</span></div>
                    <div class="hint">Verified NASA FIRMS Satellite Telemetry</div>
                </div>
            `;
        } else if (item.type === 'fire') {
            const fire = item.data;
            this.tooltip.innerHTML = `
                <div class="tooltip-header fire">
                    <span class="badge fire-badge">🔥 Active Hotspot</span>
                    <strong>${fire.district}, ${fire.state}</strong>
                </div>
                <div class="tooltip-body">
                    <div>Active Thermal Fires: <strong style="color:#ff3d00">${fire.fireCount}</strong></div>
                    <div>Avg Fire Radiative Power: <strong>${fire.avgFRP} MW</strong></div>
                    <div>Status: <span>${fire.status}</span></div>
                    <div>Harvest Progress: <span>${fire.harvestProgress}</span></div>
                    <div class="hint">Click to inspect district biomass profile</div>
                </div>
            `;
        }
    }

    getAqiColor(aqi) {
        if (aqi <= 50) return '#00e676';
        if (aqi <= 100) return '#aeea00';
        if (aqi <= 200) return '#ffd600';
        if (aqi <= 300) return '#ff9100';
        if (aqi <= 400) return '#ff3d00';
        if (aqi <= 450) return '#d50000';
        return '#4a148c';
    }

    startAnimationLoop() {
        const render = () => {
            try {
                this.draw();
            } catch (err) {
                console.warn("AgriSmokeMapEngine draw frame skipped:", err);
            }
            requestAnimationFrame(render);
        };
        requestAnimationFrame(render);
    }

    draw() {
        if (!this.width || this.width < 100 || !this.height || this.height < 100) {
            this.resize();
        }
        if (!this.width || this.width < 100) return;

        this.ctx.clearRect(0, 0, this.width, this.height);

        // 1. Draw Map Canvas Background & Grid
        this.drawMapBase();

        // 2. Draw Regional Boundaries & Geographical Features
        if (this.layers.boundaries) {
            this.drawGeographicalRegions();
            this.drawDelhiTarget();
        }

        // 3. Draw Wind Vectors & Streamlines
        if (this.layers.windVectors) {
            this.drawWindField();
        }

        // 4. Draw Smoke Plume Particles
        if (this.layers.plumeParticles) {
            this.drawAndAnimateParticles();
        }

        // 5. Draw Active Fire Hotspots
        if (this.layers.fires) {
            this.drawFireHotspots();
        }

        // 6. Draw Urban Monitoring Stations
        if (this.layers.stations) {
            this.drawMonitoringStations();
        }

        // 7. Draw Map Scale & Compass
        this.drawCompassAndScale();
    }

    drawMapBase() {
        const ctx = this.ctx;
        // Dark geospatial canvas gradient
        const bgGrad = ctx.createRadialGradient(
            this.width / 2, this.height / 2, 80,
            this.width / 2, this.height / 2, Math.max(this.width, this.height)
        );
        bgGrad.addColorStop(0, '#0c1322');
        bgGrad.addColorStop(1, '#060a12');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(0, 0, this.width, this.height);

        // Subtle coordinate grid lines
        ctx.save();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.035)';
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 6]);

        for (let lat = 28.0; lat <= 32.5; lat += 1.0) {
            const p1 = this.geoToScreen(lat, this.geoBounds.minLng);
            const p2 = this.geoToScreen(lat, this.geoBounds.maxLng);
            ctx.beginPath();
            ctx.moveTo(0, p1.y);
            ctx.lineTo(this.width, p2.y);
            ctx.stroke();

            // Lat text
            ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.font = '10px monospace';
            ctx.fillText(`${lat.toFixed(1)}°N`, 8, p1.y - 4);
        }

        for (let lng = 74.0; lng <= 78.5; lng += 1.0) {
            const p1 = this.geoToScreen(this.geoBounds.minLat, lng);
            const p2 = this.geoToScreen(this.geoBounds.maxLat, lng);
            ctx.beginPath();
            ctx.moveTo(p1.x, 0);
            ctx.lineTo(p2.x, this.height);
            ctx.stroke();

            // Lng text
            ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
            ctx.font = '10px monospace';
            ctx.fillText(`${lng.toFixed(1)}°E`, p1.x + 4, this.height - 8);
        }
        ctx.restore();
    }

    drawGeographicalRegions() {
        const ctx = this.ctx;
        ctx.save();

        // Approximate regional zones for Indo-Gangetic visual reference
        const regions = [
            {
                name: "PUNJAB (Primary Burning Basin)",
                color: "rgba(255, 87, 34, 0.06)",
                border: "rgba(255, 87, 34, 0.35)",
                points: [
                    { lat: 32.4, lng: 75.6 },
                    { lat: 31.8, lng: 76.2 },
                    { lat: 30.6, lng: 76.8 },
                    { lat: 29.9, lng: 75.8 },
                    { lat: 29.8, lng: 74.4 },
                    { lat: 30.8, lng: 74.1 },
                    { lat: 32.1, lng: 74.8 }
                ],
                labelLat: 31.2,
                labelLng: 75.2
            },
            {
                name: "HARYANA (Secondary Burning Belt)",
                color: "rgba(255, 171, 0, 0.05)",
                border: "rgba(255, 171, 0, 0.3)",
                points: [
                    { lat: 30.4, lng: 76.8 },
                    { lat: 29.9, lng: 77.2 },
                    { lat: 28.5, lng: 77.3 },
                    { lat: 28.0, lng: 76.2 },
                    { lat: 29.1, lng: 75.4 },
                    { lat: 29.9, lng: 75.8 }
                ],
                labelLat: 29.3,
                labelLng: 76.1
            },
            {
                name: "DELHI-NCR (Target Urban Airshed)",
                color: "rgba(255, 61, 0, 0.14)",
                border: "rgba(255, 61, 0, 0.7)",
                points: [
                    { lat: 28.85, lng: 77.05 },
                    { lat: 28.85, lng: 77.35 },
                    { lat: 28.45, lng: 77.40 },
                    { lat: 28.40, lng: 77.00 }
                ],
                labelLat: 28.64,
                labelLng: 77.21
            },
            {
                name: "WESTERN UTTAR PRADESH",
                color: "rgba(33, 150, 243, 0.03)",
                border: "rgba(33, 150, 243, 0.2)",
                points: [
                    { lat: 30.2, lng: 77.5 },
                    { lat: 29.2, lng: 78.4 },
                    { lat: 28.0, lng: 78.5 },
                    { lat: 28.2, lng: 77.5 }
                ],
                labelLat: 28.9,
                labelLng: 77.9
            }
        ];

        regions.forEach(reg => {
            ctx.beginPath();
            reg.points.forEach((pt, idx) => {
                const screenPt = this.geoToScreen(pt.lat, pt.lng);
                if (idx === 0) ctx.moveTo(screenPt.x, screenPt.y);
                else ctx.lineTo(screenPt.x, screenPt.y);
            });
            ctx.closePath();
            ctx.fillStyle = reg.color;
            ctx.fill();
            ctx.strokeStyle = reg.border;
            ctx.lineWidth = 1.4;
            ctx.stroke();

            // Label
            const lbl = this.geoToScreen(reg.labelLat, reg.labelLng);
            ctx.fillStyle = reg.border;
            ctx.font = '600 11px system-ui, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(reg.name, lbl.x, lbl.y);
        });

        // Representative Yamuna River Line (Yamunanagar -> Panipat -> Delhi -> Mathura)
        const yamunaPts = [
            { lat: 30.15, lng: 77.32 },
            { lat: 29.40, lng: 77.10 },
            { lat: 28.80, lng: 77.20 },
            { lat: 28.65, lng: 77.26 },
            { lat: 28.40, lng: 77.35 },
            { lat: 27.90, lng: 77.60 }
        ];

        ctx.beginPath();
        yamunaPts.forEach((pt, idx) => {
            const p = this.geoToScreen(pt.lat, pt.lng);
            if (idx === 0) ctx.moveTo(p.x, p.y);
            else ctx.lineTo(p.x, p.y);
        });
        ctx.strokeStyle = 'rgba(64, 196, 255, 0.4)';
        ctx.lineWidth = 2.0;
        ctx.stroke();

        const yLbl = this.geoToScreen(28.75, 77.22);
        ctx.fillStyle = 'rgba(64, 196, 255, 0.6)';
        ctx.font = 'italic 10px sans-serif';
        ctx.fillText("Yamuna Basin", yLbl.x + 40, yLbl.y);

        ctx.restore();
    }

    drawWindField() {
        const ctx = this.ctx;
        ctx.save();
        // High-contrast cyan with a soft glow so the vectors read clearly on the dark basemap.
        ctx.strokeStyle = 'rgba(129, 154, 161, 0.75)';
        ctx.fillStyle = 'rgba(157, 188, 195, 0.95)';
        ctx.lineWidth = 2;
        ctx.lineCap = 'round';
        ctx.shadowColor = 'rgba(197, 197, 197, 0.9)';
        ctx.shadowBlur = 6;

        const arrowLen = Math.min(46, 20 + this.windSpeed * 1.3);
        const cos = Math.cos(this.windAngleRad);
        const sin = Math.sin(this.windAngleRad);

        // Grid of wind streamlines
        for (let lat = 28.4; lat <= 32.2; lat += 0.9) {
            for (let lng = 74.4; lng <= 78.0; lng += 0.9) {
                const pos = this.geoToScreen(lat, lng);
                const endX = pos.x + cos * arrowLen;
                const endY = pos.y + sin * arrowLen;

                ctx.beginPath();
                ctx.moveTo(pos.x, pos.y);
                ctx.lineTo(endX, endY);
                ctx.stroke();

                // Arrow head
                const headLen = 8;
                ctx.beginPath();
                ctx.moveTo(endX, endY);
                ctx.lineTo(
                    endX - headLen * Math.cos(this.windAngleRad - Math.PI / 6),
                    endY - headLen * Math.sin(this.windAngleRad - Math.PI / 6)
                );
                ctx.lineTo(
                    endX - headLen * Math.cos(this.windAngleRad + Math.PI / 6),
                    endY - headLen * Math.sin(this.windAngleRad + Math.PI / 6)
                );
                ctx.closePath();
                ctx.fill();
            }
        }
        ctx.restore();
    }

    drawAndAnimateParticles() {
        const ctx = this.ctx;
        const cos = Math.cos(this.windAngleRad);
        const sin = Math.sin(this.windAngleRad);
        // Normal vector for perpendicular spread
        const normX = -sin;
        const normY = cos;

        const speedFactor = 0.6 + (Math.max(1, this.windSpeed) / 15) * 1.1;

        ctx.save();
        for (let i = 0; i < this.particles.length; i++) {
            const p = this.particles[i];
            if (!p) continue;
            p.age += 1;

            if (p.age >= p.maxLife) {
                this.particles[i] = this.spawnParticle(false);
                continue;
            }

            const origin = this.geoToScreen(p.originLat, p.originLng);
            if (!Number.isFinite(origin.x) || !Number.isFinite(origin.y)) {
                this.particles[i] = this.spawnParticle(false);
                continue;
            }

            const dist = p.age * speedFactor * 1.6;

            // Lateral Gaussian dispersion expands as particle travels downstream
            const lateralDispersion = p.spreadOffset * (1.0 + (p.age / p.maxLife) * 2.8);

            const currX = origin.x + cos * dist + normX * lateralDispersion;
            const currY = origin.y + sin * dist + normY * lateralDispersion;

            if (!Number.isFinite(currX) || !Number.isFinite(currY)) continue;

            // Fade in then fade out
            const progress = p.age / p.maxLife;
            let alpha = p.alpha;
            if (progress < 0.15) alpha = p.alpha * (progress / 0.15);
            else if (progress > 0.65) alpha = p.alpha * (1.0 - (progress - 0.65) / 0.35);

            // Expanding radius safely guarded against <= 0
            const currentRadius = Math.max(1, (p.radius + progress * 14) * this.scale);

            try {
                const smokeGrad = ctx.createRadialGradient(
                    currX, currY, 0,
                    currX, currY, currentRadius
                );
                smokeGrad.addColorStop(0, `rgba(255, 110, 64, ${Math.max(0, Math.min(1, alpha * 0.85))})`);
                smokeGrad.addColorStop(0.4, `rgba(220, 80, 40, ${Math.max(0, Math.min(1, alpha * 0.45))})`);
                smokeGrad.addColorStop(1, 'rgba(100, 40, 20, 0)');

                ctx.fillStyle = smokeGrad;
                ctx.beginPath();
                ctx.arc(currX, currY, currentRadius, 0, Math.PI * 2);
                ctx.fill();
            } catch (err) {
                // Ignore gradient calculation error on outer frame boundaries
            }
        }
        ctx.restore();
    }

    drawFireHotspots() {
        const ctx = this.ctx;
        const time = Date.now() * 0.004;

        // Render Real NASA FIRMS Satellite Observations if loaded
        if (this.filteredObservations && this.filteredObservations.length > 0) {
            this.filteredObservations.forEach(obs => {
                const pos = this.geoToScreen(obs.latitude, obs.longitude);
                const isHovered = this.hoveredItem && this.hoveredItem.data.id === obs.id;

                ctx.save();
                const isAgri = obs.classification === 'agricultural';
                const isInd = obs.classification === 'industrial';
                const isForest = obs.classification === 'forest_vegetation';

                const coreColor = isAgri ? '#ff3d00' : (isInd ? '#a855f7' : (isForest ? '#10b981' : '#f59e0b'));
                const glowRgba = isAgri ? 'rgba(255, 61, 0, ' : (isInd ? 'rgba(168, 85, 247, ' : 'rgba(16, 185, 129, ');

                const pulse = 1.0 + Math.sin(time + obs.latitude * 10) * 0.25;
                const baseRadius = Math.max(3, Math.min(14, 3 + Math.sqrt(obs.frp || 2) * 1.4));
                const radius = baseRadius * pulse * this.scale;

                // Thermal Glow
                const glowGrad = ctx.createRadialGradient(pos.x, pos.y, 1, pos.x, pos.y, radius * 2.2);
                glowGrad.addColorStop(0, `${glowRgba}0.85)`);
                glowGrad.addColorStop(0.4, `${glowRgba}0.35)`);
                glowGrad.addColorStop(1, `${glowRgba}0)`);

                ctx.fillStyle = glowGrad;
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, radius * 2.2, 0, Math.PI * 2);
                ctx.fill();

                // Core Dot
                ctx.fillStyle = '#fff7c2';
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, Math.max(2.5, 3.5 * this.scale), 0, Math.PI * 2);
                ctx.fill();

                if (isHovered) {
                    ctx.strokeStyle = '#ffffff';
                    ctx.lineWidth = 2;
                    ctx.beginPath();
                    ctx.arc(pos.x, pos.y, radius * 1.4, 0, Math.PI * 2);
                    ctx.stroke();
                }

                ctx.restore();
            });
            return;
        }

        // Fallback: Default hotspots
        DEMO_DATA.fireHotspots.forEach(fire => {
            const pos = this.geoToScreen(fire.lat, fire.lng);
            const isHovered = this.hoveredItem && this.hoveredItem.data.id === fire.id;

            ctx.save();

            // Pulsing thermal glow
            const pulse = 1.0 + Math.sin(time + fire.fireCount) * 0.35;
            const radius = Math.min(18, 6 + (fire.fireCount / 40)) * pulse * this.scale;

            const glowGrad = ctx.createRadialGradient(pos.x, pos.y, 2, pos.x, pos.y, radius * 2.5);
            glowGrad.addColorStop(0, 'rgba(255, 61, 0, 0.9)');
            glowGrad.addColorStop(0.35, 'rgba(255, 110, 0, 0.5)');
            glowGrad.addColorStop(1, 'rgba(255, 61, 0, 0)');

            ctx.fillStyle = glowGrad;
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, radius * 2.5, 0, Math.PI * 2);
            ctx.fill();

            // Core flame icon/dot
            ctx.fillStyle = '#fff7c2';
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, Math.max(3, 4.5 * this.scale), 0, Math.PI * 2);
            ctx.fill();

            // Fire count label
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 10px system-ui, sans-serif';
            ctx.textAlign = 'center';
            ctx.shadowColor = '#000000';
            ctx.shadowBlur = 4;
            ctx.fillText(`${fire.district} (${fire.fireCount})`, pos.x, pos.y + radius + 11);

            if (isHovered) {
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, radius * 1.3, 0, Math.PI * 2);
                ctx.stroke();
            }

            ctx.restore();
        });
    }

    drawMonitoringStations() {
        const ctx = this.ctx;
        DEMO_DATA.monitoringStations.forEach(st => {
            if (st.lat == null || st.lng == null) return;
            const pos = this.geoToScreen(st.lat, st.lng);
            const color = this.getAqiColor(st.aqi);
            const isHovered = this.hoveredItem && this.hoveredItem.data.id === st.id;
            const r = (isHovered ? 14 : 11) * this.scale;

            ctx.save();

            // Dark backing halo so the marker reads on any basemap
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, r + 3, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(15, 23, 42, 0.6)';
            ctx.fill();

            // AQI-coloured ring with light face
            ctx.lineWidth = isHovered ? 2.5 : 1.8;
            ctx.strokeStyle = color;
            ctx.fillStyle = 'rgba(248, 250, 252, 0.96)';
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();

            // AQI value centred inside the ring (declutters the dense NCR cluster)
            ctx.fillStyle = color;
            ctx.font = `700 ${Math.max(9, 10 * this.scale)}px system-ui, sans-serif`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(String(st.aqi != null ? st.aqi : '--'), pos.x, pos.y + 0.5);
            ctx.textBaseline = 'alphabetic';

            // Name label only when zoomed in or hovered, to avoid overlapping tags
            if (isHovered || this.scale >= 1.5) {
                ctx.fillStyle = '#e2e8f0';
                ctx.font = '600 10px system-ui, sans-serif';
                ctx.shadowColor = '#000000';
                ctx.shadowBlur = 5;
                ctx.fillText(`${st.name.split(',')[0]}`, pos.x, pos.y - r - 5);
            }

            ctx.restore();
        });
    }

    // Sets the live Delhi-NCR impact-zone reading shown on the map.
    setTarget(aqi, color) {
        this.targetAqi = aqi;
        this.targetColor = color;
    }

    drawDelhiTarget() {
        const ctx = this.ctx;
        const delhi = { lat: 28.6139, lng: 77.2090 };
        const pos = this.geoToScreen(delhi.lat, delhi.lng);
        if (!Number.isFinite(pos.x) || !Number.isFinite(pos.y)) return;

        const t = Date.now() * 0.0016;
        const pulse = 1 + Math.sin(t) * 0.12;
        const baseR = 16 * this.scale;

        ctx.save();
        // Impact-zone concentric rings
        ctx.strokeStyle = 'rgba(255, 61, 0, 0.6)';
        ctx.lineWidth = 1.5;
        for (let i = 1; i <= 2; i++) {
            ctx.globalAlpha = 0.55 / i;
            ctx.beginPath();
            ctx.arc(pos.x, pos.y, baseR * i * pulse, 0, Math.PI * 2);
            ctx.stroke();
        }
        ctx.globalAlpha = 1;

        // Target cross + core
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(pos.x - 6, pos.y); ctx.lineTo(pos.x + 6, pos.y);
        ctx.moveTo(pos.x, pos.y - 6); ctx.lineTo(pos.x, pos.y + 6);
        ctx.stroke();
        ctx.fillStyle = this.targetColor || '#ff3d00';
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, 3.5, 0, Math.PI * 2);
        ctx.fill();

        // Label with the live AQI
        ctx.fillStyle = '#fecaca';
        ctx.font = '700 11px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.shadowColor = '#000000';
        ctx.shadowBlur = 5;
        const aqiTxt = this.targetAqi != null ? ` \u2022 AQI ${Math.round(this.targetAqi)}` : '';
        ctx.fillText(`DELHI-NCR IMPACT ZONE${aqiTxt}`, pos.x, pos.y + baseR * 2 + 14);
        ctx.restore();
    }

    drawCompassAndScale() {
        const ctx = this.ctx;
        ctx.save();

        // 1. Compass Rose (Top Right)
        const compassX = this.width - 50;
        const compassY = 50;

        ctx.translate(compassX, compassY);
        ctx.fillStyle = 'rgba(15, 23, 42, 0.7)';
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(0, 0, 24, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // North pointer
        ctx.fillStyle = '#ff3d00';
        ctx.beginPath();
        ctx.moveTo(0, -18);
        ctx.lineTo(5, -2);
        ctx.lineTo(-5, -2);
        ctx.closePath();
        ctx.fill();

        // South pointer
        ctx.fillStyle = '#94a3b8';
        ctx.beginPath();
        ctx.moveTo(0, 18);
        ctx.lineTo(5, 2);
        ctx.lineTo(-5, 2);
        ctx.closePath();
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('N', 0, -20);

        ctx.restore();

        // 2. Map Scale Bar (Bottom Left)
        ctx.save();
        const p1 = this.geoToScreen(28.0, 75.0);
        const p2 = this.geoToScreen(28.0, 76.0);
        // Approx 1 deg longitude at 28 deg N is ~98 km
        let pixelPer100Km = (p2.x - p1.x) * (100 / 98);
        if (!Number.isFinite(pixelPer100Km) || pixelPer100Km <= 10) {
            pixelPer100Km = 80;
        }

        const scaleX = 24;
        const scaleY = this.height - 24;

        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(scaleX, scaleY);
        ctx.lineTo(scaleX + pixelPer100Km, scaleY);
        ctx.moveTo(scaleX, scaleY - 4);
        ctx.lineTo(scaleX, scaleY + 4);
        ctx.moveTo(scaleX + pixelPer100Km, scaleY - 4);
        ctx.lineTo(scaleX + pixelPer100Km, scaleY + 4);
        ctx.stroke();

        ctx.fillStyle = '#ffffff';
        ctx.font = '10px monospace';
        ctx.textAlign = 'center';
        ctx.fillText('100 km (Indo-Gangetic Airshed)', scaleX + pixelPer100Km / 2, scaleY - 8);

        ctx.restore();
    }
}

// Make available globally
window.AgriSmokeMapEngine = AgriSmokeMapEngine;
