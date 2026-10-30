/**
 * AgriSmoke AI - Main Application Controller
 * 
 * Orchestrates UI tabs, interactive prediction calculator, map engine,
 * SVG charts, alerts system, scenario presets, data export,
 * and Python FastAPI / SQLite backend connectivity.
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize Engines
    const model = new AgriSmokePredictionModel();
    const charts = new AgriSmokeChartsEngine();
    let map = null;

    // Backend API Base Configuration
    const isLocalBackend = window.location.protocol.startsWith('http') && (window.location.port === '8000');
    const API_BASE = isLocalBackend ? '' : 'http://127.0.0.1:8000';
    let isBackendConnected = false;
    let predictDebounceTimer = null;

    // Current State
    let currentInputs = {
        fireCount: 1684,
        windSpeed: 11.5,
        windDirectionDeg: 305,
        pblHeight: 480,
        burnAreaHectares: 75000,
        urbanBaselineAqi: 180,
        bioDecomposerAdoption: 25,
        happySeederAdoption: 30
    };

    let activeAlertThreshold = {
        aqi: 400,
        fires: 2000
    };

    let liveSimulationInterval = null;
    let lastTelemetryTime = Date.now();
    let tickerInterval = null;
    let lastCalculatedPred = null;
    let lastCalculatedHourly = null;

    // Animated Numeric Counter for Fluid Real-Time Feedback
    function animateNumber(element, targetVal, duration = 350, decimals = 0, prefix = '', suffix = '') {
        if (!element) return;
        if (typeof targetVal !== 'number' || isNaN(targetVal)) {
            element.textContent = `${prefix}${targetVal}${suffix}`;
            return;
        }
        const startVal = (typeof element._animValue === 'number') ? element._animValue : targetVal;
        element._animValue = targetVal;

        if (Math.abs(startVal - targetVal) < (decimals > 0 ? 0.05 : 0.5)) {
            element.textContent = `${prefix}${decimals > 0 ? targetVal.toFixed(decimals) : Math.round(targetVal).toLocaleString()}${suffix}`;
            return;
        }

        const startTime = performance.now();
        const step = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(1.0, elapsed / duration);
            // Cubic ease out
            const ease = 1 - Math.pow(1 - progress, 3);
            const current = startVal + (targetVal - startVal) * ease;

            element.textContent = `${prefix}${decimals > 0 ? current.toFixed(decimals) : Math.round(current).toLocaleString()}${suffix}`;

            if (progress < 1.0) {
                requestAnimationFrame(step);
            } else {
                element.textContent = `${prefix}${decimals > 0 ? targetVal.toFixed(decimals) : Math.round(targetVal).toLocaleString()}${suffix}`;
            }
        };
        requestAnimationFrame(step);
    }

    // Dynamic Reactive Slider Glow Fill
    function updateSliderProgress(slider) {
        if (!slider) return;
        const min = parseFloat(slider.min) || 0;
        const max = parseFloat(slider.max) || 100;
        const val = parseFloat(slider.value) || 0;
        const pct = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));

        const isMitigation = slider.id.includes('bio') || slider.id.includes('happy');
        const color1 = isMitigation ? '#16a34a' : '#ea580c';
        const color2 = isMitigation ? '#2563eb' : '#f97316';

        slider.style.background = `linear-gradient(to right, ${color1} 0%, ${color2} ${pct}%, #e2e8f0 ${pct}%, #e2e8f0 100%)`;
    }

    // 2. Setup Navigation Tabs
    const navButtons = document.querySelectorAll('.nav-tab-btn');
    const tabPanels = document.querySelectorAll('.tab-panel');

    function switchTab(tabId) {
        navButtons.forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-tab') === tabId);
        });
        tabPanels.forEach(panel => {
            panel.classList.toggle('active', panel.id === `tab-${tabId}`);
        });

        // If map tab is selected, trigger resize and re-init particles
        if (tabId === 'map' && map) {
            setTimeout(() => {
                map.resize();
                map.reinitParticles();
            }, 60);
        }

        // Render charts if tab contains them
        if (tabId === 'dashboard') {
            setTimeout(() => updateVisualizations(), 50);
        }

        if (tabId === 'calculator') {
            updateAllSliderFills();
        }
    }

    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            switchTab(tabId);
        });
    });

    // 3. Initialize Map Engine
    try {
        map = new AgriSmokeMapEngine('geospatial-canvas', 'map-container');
        map.updateWind(currentInputs.windSpeed, currentInputs.windDirectionDeg);
    } catch (err) {
        console.error("Map initialization error:", err);
    }

    // Handle Map item clicks
    window.addEventListener('map-item-selected', (e) => {
        const item = e.detail;
        showDetailModal(item);
    });

    // 4. Bind Calculator Sliders & Controls
    const sliderFireCount = document.getElementById('input-fire-count');
    const valFireCount = document.getElementById('val-fire-count');

    const sliderWindSpeed = document.getElementById('input-wind-speed');
    const valWindSpeed = document.getElementById('val-wind-speed');

    const sliderWindDir = document.getElementById('input-wind-dir');
    const valWindDir = document.getElementById('val-wind-dir');
    const compassWindLabel = document.getElementById('compass-wind-label');

    const sliderPbl = document.getElementById('input-pbl-height');
    const valPbl = document.getElementById('val-pbl-height');

    const sliderUrbanBase = document.getElementById('input-urban-base');
    const valUrbanBase = document.getElementById('val-urban-base');

    const sliderBioDec = document.getElementById('input-bio-decomposer');
    const valBioDec = document.getElementById('val-bio-decomposer');

    const sliderHappySeed = document.getElementById('input-happy-seeder');
    const valHappySeed = document.getElementById('val-happy-seeder');

    function updateAllSliderFills() {
        [sliderFireCount, sliderWindSpeed, sliderWindDir, sliderPbl, sliderUrbanBase, sliderBioDec, sliderHappySeed].forEach(el => {
            if (el) updateSliderProgress(el);
        });
    }

    function syncInputsFromUI() {
        if (sliderFireCount) currentInputs.fireCount = parseInt(sliderFireCount.value, 10);
        if (sliderWindSpeed) currentInputs.windSpeed = parseFloat(sliderWindSpeed.value);
        if (sliderWindDir) currentInputs.windDirectionDeg = parseInt(sliderWindDir.value, 10);
        if (sliderPbl) currentInputs.pblHeight = parseInt(sliderPbl.value, 10);
        if (sliderUrbanBase) currentInputs.urbanBaselineAqi = parseInt(sliderUrbanBase.value, 10);
        if (sliderBioDec) currentInputs.bioDecomposerAdoption = parseInt(sliderBioDec.value, 10);
        if (sliderHappySeed) currentInputs.happySeederAdoption = parseInt(sliderHappySeed.value, 10);

        // Update labels
        if (valFireCount) valFireCount.textContent = currentInputs.fireCount.toLocaleString();
        if (valWindSpeed) valWindSpeed.textContent = `${currentInputs.windSpeed.toFixed(1)} km/h`;
        if (valWindDir) {
            const dirLabel = getCompassDirection(currentInputs.windDirectionDeg);
            valWindDir.textContent = `${currentInputs.windDirectionDeg}° (${dirLabel})`;
            if (compassWindLabel) compassWindLabel.textContent = dirLabel;
        }
        if (valPbl) valPbl.textContent = `${currentInputs.pblHeight} m`;
        if (valUrbanBase) valUrbanBase.textContent = `${currentInputs.urbanBaselineAqi} AQI`;
        if (valBioDec) valBioDec.textContent = `${currentInputs.bioDecomposerAdoption}%`;
        if (valHappySeed) valHappySeed.textContent = `${currentInputs.happySeederAdoption}%`;

        // Update live weather badge in header telemetry strip
        const liveWindBadge = document.getElementById('live-wind-badge');
        if (liveWindBadge) {
            const dirLabel = getCompassDirection(currentInputs.windDirectionDeg);
            liveWindBadge.textContent = `💨 ${currentInputs.windSpeed.toFixed(1)} km/h ${dirLabel} (${currentInputs.windDirectionDeg}°)`;
        }

        // Update slider track gradient progress fills
        updateAllSliderFills();

        // Update map particle wind angle & speed
        if (map) {
            map.updateWind(currentInputs.windSpeed, currentInputs.windDirectionDeg);
        }

        runModelAndUpdateUI();
    }

    function setInputsToUI(params) {
        if (sliderFireCount && params.fireCount !== undefined) sliderFireCount.value = params.fireCount;
        if (sliderWindSpeed && params.windSpeed !== undefined) sliderWindSpeed.value = params.windSpeed;
        if (sliderWindDir && params.windDirectionDeg !== undefined) sliderWindDir.value = params.windDirectionDeg;
        if (sliderPbl && params.pblHeight !== undefined) sliderPbl.value = params.pblHeight;
        if (sliderUrbanBase && params.urbanBaselineAqi !== undefined) sliderUrbanBase.value = params.urbanBaselineAqi;
        if (sliderBioDec && params.bioDecomposerAdoption !== undefined) sliderBioDec.value = params.bioDecomposerAdoption;
        if (sliderHappySeed && params.happySeederAdoption !== undefined) sliderHappySeed.value = params.happySeederAdoption;

        syncInputsFromUI();
    }

    [sliderFireCount, sliderWindSpeed, sliderWindDir, sliderPbl, sliderUrbanBase, sliderBioDec, sliderHappySeed].forEach(el => {
        el?.addEventListener('input', syncInputsFromUI);
    });

    // 5. Compass direction helper
    function getCompassDirection(deg) {
        const directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ];
        const idx = Math.round(deg / 22.5) % 16;
        return directions[idx];
    }

    // 6. Prediction Model Execution & UI Updates
    function runModelAndUpdateUI() {
        // Immediate local calculation for zero input lag
        const localPred = model.predict(currentInputs);
        const localHourly = model.generateHourlyForecast(currentInputs);
        applyPredictionToUI(localPred, localHourly);

        // If backend is active, dispatch async ML inference call
        if (isBackendConnected) {
            if (predictDebounceTimer) clearTimeout(predictDebounceTimer);
            predictDebounceTimer = setTimeout(() => {
                fetch(`${API_BASE}/api/predict`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(currentInputs)
                })
                .then(res => {
                    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
                    return res.json();
                })
                .then(data => {
                    if (data && data.prediction) {
                        applyPredictionToUI(data.prediction, data.hourlyForecast);
                    }
                })
                .catch(err => {
                    console.log("[Backend Predict] Using local model fallback:", err);
                });
            }, 120);
        }
    }

    function applyPredictionToUI(pred, hourly) {
        lastCalculatedPred = pred;
        lastCalculatedHourly = hourly;

        // Update Key KPI Badges & Elements with smooth number animation
        const elAqi = document.getElementById('kpi-aqi-value');
        const elCategory = document.getElementById('kpi-aqi-category');
        const elPm25 = document.getElementById('kpi-pm25-val');
        const elPm10 = document.getElementById('kpi-pm10-val');
        const elParaliPct = document.getElementById('kpi-parali-pct');
        const elFires = document.getElementById('kpi-active-fires');
        const elGrapBadge = document.getElementById('kpi-grap-badge');
        const elAirshedScore = document.getElementById('kpi-airshed-score');
        const elTransportLag = document.getElementById('kpi-transport-lag');

        if (elAqi) {
            animateNumber(elAqi, pred.predictedAqi, 350, 0);
            elAqi.style.color = pred.categoryColor;
        }
        if (elCategory) {
            elCategory.textContent = pred.category;
            elCategory.style.backgroundColor = pred.categoryColor + '33';
            elCategory.style.color = pred.categoryColor;
            elCategory.style.borderColor = pred.categoryColor;
        }
        if (elPm25) animateNumber(elPm25, pred.totalPm25, 350, 1, '', ' µg/m³');
        if (elPm10) animateNumber(elPm10, pred.totalPm10, 350, 1, '', ' µg/m³');
        if (elParaliPct) animateNumber(elParaliPct, pred.paraliPct, 350, 1, '', '%');
        if (elFires) animateNumber(elFires, currentInputs.fireCount, 350, 0);
        if (elAirshedScore) animateNumber(elAirshedScore, pred.airshedScore, 350, 0, '', '/100');
        if (elTransportLag) animateNumber(elTransportLag, pred.transportHours, 350, 1, '~', ' hrs');

        if (elGrapBadge) {
            elGrapBadge.textContent = pred.grapStage === "None" ? "Normal Baseline" : `GRAP ${pred.grapStage}`;
            elGrapBadge.className = `badge grap-badge ${pred.grapStage.toLowerCase().replace(' ', '-')}`;
        }

        // Update Calculator Results Card
        const calcAqi = document.getElementById('calc-res-aqi');
        const calcPm25 = document.getElementById('calc-res-pm25');
        const calcStubblePm25 = document.getElementById('calc-res-stubble-pm25');
        const calcParaliPct = document.getElementById('calc-res-parali-pct');
        const calcCategory = document.getElementById('calc-res-category');
        const calcDirFactor = document.getElementById('calc-res-dir-factor');
        const calcInversionFactor = document.getElementById('calc-res-inversion');
        const calcMitigationDrop = document.getElementById('calc-res-mitigation-drop');

        if (calcAqi) {
            animateNumber(calcAqi, pred.predictedAqi, 350, 0);
            calcAqi.style.color = pred.categoryColor;
        }
        if (calcPm25) animateNumber(calcPm25, pred.totalPm25, 350, 1, '', ' µg/m³');
        if (calcStubblePm25) animateNumber(calcStubblePm25, pred.stubblePm25, 350, 1, '+', ' µg/m³');
        if (calcParaliPct) animateNumber(calcParaliPct, pred.paraliPct, 350, 1, '', '%');
        if (calcCategory) {
            calcCategory.textContent = `${pred.category} (${pred.grapStage})`;
            calcCategory.style.color = pred.categoryColor;
        }
        if (calcDirFactor) animateNumber(calcDirFactor, pred.dirFactor, 350, 0, '', '%');
        if (calcInversionFactor) animateNumber(calcInversionFactor, pred.pblTrappingFactor, 350, 2, '', 'x');
        if (calcMitigationDrop) {
            const drop = pred.mitigationSavings ? pred.mitigationSavings.aqiDrop : 35;
            calcMitigationDrop.textContent = `-${drop} AQI points`;
        }

        // Update Health Advisory Text
        updateHealthAdvisory(pred);

        // Check if custom alerts trigger
        checkAlertTriggers(pred.predictedAqi, currentInputs.fireCount);

        // Update Dynamic GRAP Matrix tab
        updateGrapMatrixCards(pred);

        // Update Charts
        if (hourly && hourly.length) {
            charts.renderDiurnalChart('chart-diurnal-forecast', hourly);
        }
        charts.renderAqiSpeedometer('gauge-aqi-speedometer', pred.predictedAqi);

        // Source apportionment donut update
        const dynamicSources = [
            { source: "Agricultural Stubble Smoke", percentage: Math.max(5, Math.min(80, Math.round(pred.paraliPct))), color: "#ff5722", description: "Direct parali smoke transported via NW winds" },
            { source: "Vehicular Emissions", percentage: Math.max(10, Math.round((100 - pred.paraliPct) * 0.42)), color: "#00b0ff", description: "Urban tailpipe emissions" },
            { source: "Secondary Aerosols", percentage: Math.max(8, Math.round((100 - pred.paraliPct) * 0.28)), color: "#e040fb", description: "Atmospheric chemical transformations" },
            { source: "Road Dust & Construction", percentage: Math.max(5, Math.round((100 - pred.paraliPct) * 0.18)), color: "#ffab00", description: "Suspended road and construction dust" },
            { source: "Industrial & Power Plants", percentage: Math.max(5, Math.round((100 - pred.paraliPct) * 0.12)), color: "#00e676", description: "Surrounding industrial units & brick kilns" }
        ];
        charts.renderSourceDonut('chart-source-donut', dynamicSources);
    }

    function updateGrapMatrixCards(pred) {
        const grapStageCards = document.querySelectorAll('.grap-stage-card');
        grapStageCards.forEach(card => {
            card.classList.remove('active-stage');
            const oldBadge = card.querySelector('.grap-stage-badge');
            if (oldBadge) oldBadge.remove();

            const titleEl = card.querySelector('.grap-stage-title');
            if (titleEl && pred.grapStage && pred.grapStage !== "None") {
                const titleText = titleEl.textContent.toLowerCase();
                const predStage = pred.grapStage.toLowerCase();
                if (titleText.includes(predStage)) {
                    card.classList.add('active-stage');
                    const badge = document.createElement('span');
                    badge.className = 'badge grap-stage-badge';
                    badge.style.background = pred.categoryColor;
                    badge.style.color = '#000000';
                    badge.style.fontWeight = '700';
                    badge.textContent = 'ACTIVE NOW';
                    card.insertBefore(badge, card.firstChild);
                }
            }
        });
    }

    function updateHealthAdvisory(pred) {
        const generalText = document.getElementById('advisory-general');
        const sensitiveText = document.getElementById('advisory-sensitive');
        const outdoorText = document.getElementById('advisory-outdoor');

        const cat = DEMO_DATA.aqiCategories.find(c => pred.predictedAqi >= c.min && pred.predictedAqi <= c.max) || DEMO_DATA.aqiCategories[DEMO_DATA.aqiCategories.length - 1];

        if (generalText) generalText.textContent = cat.advisory;
        if (sensitiveText) {
            if (pred.predictedAqi > 400) {
                sensitiveText.textContent = "High respiratory risk. Avoid going outdoors completely. Operate HEPA air purifiers in sealed indoor rooms.";
            } else if (pred.predictedAqi > 300) {
                sensitiveText.textContent = "Asthma and cardiac patients should keep rescue inhalers accessible; strictly avoid morning and evening walks.";
            } else {
                sensitiveText.textContent = "Sensitive individuals should wear protective N95 masks during heavy outdoor traffic hours.";
            }
        }
        if (outdoorText) {
            if (pred.predictedAqi > 400) {
                outdoorText.textContent = "Mandatory N95 respirator masks required for traffic police, construction workers, and delivery personnel.";
            } else {
                outdoorText.textContent = "Avoid high-intensity outdoor cardio/running between 18:00 and 09:00 IST.";
            }
        }
    }

    function updateVisualizations() {
        charts.renderWeeklyTrendChart('chart-weekly-trend', DEMO_DATA.weeklyTrend);
        charts.renderDistrictBars('chart-district-bars', DEMO_DATA.districtFireCounts);

        if (lastCalculatedPred) {
            charts.renderAqiSpeedometer('gauge-aqi-speedometer', lastCalculatedPred.predictedAqi);
            if (lastCalculatedHourly) {
                charts.renderDiurnalChart('chart-diurnal-forecast', lastCalculatedHourly);
            }
            const dynamicSources = [
                { source: "Agricultural Stubble Smoke", percentage: Math.max(5, Math.min(80, Math.round(lastCalculatedPred.paraliPct))), color: "#ff5722", description: "Direct parali smoke transported via NW winds" },
                { source: "Vehicular Emissions", percentage: Math.max(10, Math.round((100 - lastCalculatedPred.paraliPct) * 0.42)), color: "#00b0ff", description: "Urban tailpipe emissions" },
                { source: "Secondary Aerosols", percentage: Math.max(8, Math.round((100 - lastCalculatedPred.paraliPct) * 0.28)), color: "#e040fb", description: "Atmospheric chemical transformations" },
                { source: "Road Dust & Construction", percentage: Math.max(5, Math.round((100 - lastCalculatedPred.paraliPct) * 0.18)), color: "#ffab00", description: "Suspended road and construction dust" },
                { source: "Industrial & Power Plants", percentage: Math.max(5, Math.round((100 - lastCalculatedPred.paraliPct) * 0.12)), color: "#00e676", description: "Surrounding industrial units & brick kilns" }
            ];
            charts.renderSourceDonut('chart-source-donut', dynamicSources);
        }
    }

    // 7. Scenario Presets Handler
    document.querySelectorAll('[data-preset]').forEach(btn => {
        btn.addEventListener('click', () => {
            const presetKey = btn.getAttribute('data-preset');
            const preset = DEMO_DATA.presets[presetKey];
            if (preset) {
                setInputsToUI(preset);
                showNotification(`Applied Preset: ${preset.name}`, "info");
            }
        });
    });

    // 8. Alerts & Threshold Trigger Engine
    function checkAlertTriggers(aqi, fires) {
        const banner = document.getElementById('active-alert-banner');
        if (!banner) return;

        if (aqi >= activeAlertThreshold.aqi || fires >= activeAlertThreshold.fires) {
            banner.classList.add('visible');
            document.getElementById('banner-alert-msg').textContent = 
                `CRITICAL THRESHOLD TRIGGERED: Current predicted AQI (${aqi}) or Active Fires (${fires}) exceeds your safety threshold (AQI > ${activeAlertThreshold.aqi} / Fires > ${activeAlertThreshold.fires}).`;
        } else {
            banner.classList.remove('visible');
        }
    }

    // Custom Threshold Inputs
    const inputThreshAqi = document.getElementById('thresh-aqi-input');
    const inputThreshFires = document.getElementById('thresh-fires-input');
    const btnSaveThresh = document.getElementById('btn-save-threshold');

    btnSaveThresh?.addEventListener('click', () => {
        activeAlertThreshold.aqi = parseInt(inputThreshAqi.value, 10) || 400;
        activeAlertThreshold.fires = parseInt(inputThreshFires.value, 10) || 2000;

        if (isBackendConnected) {
            fetch(`${API_BASE}/api/thresholds`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(activeAlertThreshold)
            }).catch(console.error);
        }

        showNotification(`Alert thresholds updated: AQI > ${activeAlertThreshold.aqi}, Fires > ${activeAlertThreshold.fires}`, "success");
        runModelAndUpdateUI();
    });

    // Test Alert Audio Chime Demo (Uses browser Web Audio API, zero dependencies!)
    const handleSoundClick = () => {
        playAlertAudioChime();
        showNotification("Emergency Alert Tone Triggered (Web Audio API Synthesizer)", "warning");
    };
    document.getElementById('btn-test-alert-sound')?.addEventListener('click', handleSoundClick);
    document.getElementById('btn-test-alert-sound-tab')?.addEventListener('click', handleSoundClick);

    function playAlertAudioChime() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            const ctx = new AudioContext();
            if (ctx.state === 'suspended') {
                ctx.resume();
            }
            
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'triangle';
            osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
            osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.15); // A5
            osc.frequency.setValueAtTime(587.33, ctx.currentTime + 0.30);
            osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.45);

            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.7);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start();
            osc.stop(ctx.currentTime + 0.75);
        } catch (e) {
            console.log("AudioContext blocked or unavailable:", e);
        }
    }

    // 9. Item Detail Modal (Stations & Hotspots)
    const modal = document.getElementById('detail-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalContent = document.getElementById('modal-content');
    const modalClose = document.getElementById('modal-close');

    function showDetailModal(item) {
        if (!modal) return;
        if (item.type === 'station') {
            const st = item.data;
            modalTitle.textContent = `Monitoring Station: ${st.name}`;
            modalContent.innerHTML = `
                <div class="modal-grid">
                    <div class="modal-kpi">
                        <div class="kpi-label">AQI</div>
                        <div class="kpi-num" style="color:${map.getAqiColor(st.aqi)}">${st.aqi}</div>
                        <div class="kpi-sub">${st.category}</div>
                    </div>
                    <div class="modal-kpi">
                        <div class="kpi-label">PM2.5 (24h)</div>
                        <div class="kpi-num">${st.pm25} <span style="font-size:12px">µg/m³</span></div>
                        <div class="kpi-sub">Dominant Pollutant</div>
                    </div>
                    <div class="modal-kpi">
                        <div class="kpi-label">Parali Smoke %</div>
                        <div class="kpi-num" style="color:#ff7043">${st.paraliPct}%</div>
                        <div class="kpi-sub">Upwind Contribution</div>
                    </div>
                </div>
                <div style="margin-top:16px;font-size:13px;line-height:1.6;color:#475569;">
                    <p><strong>Geographic Coordinates:</strong> ${st.lat.toFixed(4)}°N, ${st.lng.toFixed(4)}°E</p>
                    <p><strong>Station Classification:</strong> ${st.type}</p>
                    <p><strong>Airshed Inflow Exposure:</strong> Direct path for smoke plumes entering through the North-West corridor during north-westerly wind regimes.</p>
                </div>
            `;
        } else if (item.type === 'fire') {
            const f = item.data;
            modalTitle.textContent = `Fire Anomaly Cluster: ${f.district}, ${f.state}`;
            modalContent.innerHTML = `
                <div class="modal-grid">
                    <div class="modal-kpi">
                        <div class="kpi-label">Active Thermal Fires</div>
                        <div class="kpi-num" style="color:#ea580c">${f.fireCount}</div>
                        <div class="kpi-sub">${f.status}</div>
                    </div>
                    <div class="modal-kpi">
                        <div class="kpi-label">Avg Fire Radiative Power</div>
                        <div class="kpi-num">${f.avgFRP} <span style="font-size:12px">MW</span></div>
                        <div class="kpi-sub">Thermal Intensity</div>
                    </div>
                    <div class="modal-kpi">
                        <div class="kpi-label">Harvest Status</div>
                        <div class="kpi-num" style="font-size:18px">${f.harvestProgress}</div>
                        <div class="kpi-sub">${f.confidence}</div>
                    </div>
                </div>
                <div style="margin-top:16px;font-size:13px;line-height:1.6;color:#475569;">
                    <p><strong>Hotspot Center:</strong> ${f.lat.toFixed(4)}°N, ${f.lng.toFixed(4)}°E</p>
                    <p><strong>Smoke Emission Potential:</strong> Estimated ${(f.fireCount * 45).toLocaleString()} hectares of paddy residue under immediate post-harvest clearing.</p>
                    <p><strong>Downwind Trajectory:</strong> Plume dispersion vector points toward Delhi NCR with estimated transport travel time of 16-24 hours at prevailing wind speeds.</p>
                </div>
            `;
        }
        modal.classList.add('visible');
    }

    modalClose?.addEventListener('click', () => {
        modal.classList.remove('visible');
    });

    modal?.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('visible');
    });

    // 10. Data Export (CSV Download via Backend or Client-Side Blob)
    document.getElementById('btn-export-csv')?.addEventListener('click', () => {
        if (isBackendConnected) {
            const query = new URLSearchParams(currentInputs).toString();
            window.location.href = `${API_BASE}/api/export/csv?${query}`;
            showNotification("Downloading ML telemetry report from Python backend...", "success");
        } else {
            exportDiagnosticCSV();
        }
    });

    function exportDiagnosticCSV() {
        const pred = model.predict(currentInputs);
        const hourly = model.generateHourlyForecast(currentInputs);

        let csv = "Time,Predicted_AQI,PM25_ug_m3,Stubble_Smoke_Contribution_Pct,PBL_Height_m,Wind_Speed_kmh,Category\n";
        hourly.forEach(row => {
            csv += `"${row.time}",${row.aqi},${row.pm25},${row.stubblePct},${row.pbl},${row.windSpeed},"${row.category}"\n`;
        });

        csv += "\n# System Metadata\n";
        csv += `"Generated At","${new Date().toISOString()}"\n`;
        csv += `"Active Stubble Fires",${currentInputs.fireCount}\n`;
        csv += `"Wind Direction","${currentInputs.windDirectionDeg} deg (${getCompassDirection(currentInputs.windDirectionDeg)})"\n`;
        csv += `"Summary Predicted 24h AQI",${pred.predictedAqi}\n`;
        csv += `"GRAP Stage","${pred.grapStage}"\n`;
        csv += `"Data Label","Demonstration & Physical-Empirical AI Simulation"\n`;

        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.setAttribute('href', url);
        link.setAttribute('download', `AgriSmoke_AI_Air_Quality_Report_${new Date().toISOString().slice(0, 10)}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        showNotification("Diagnostic CSV Report successfully generated and downloaded.", "success");
    }

    // 11. Print Briefing View with Official Executive Template Population
    document.getElementById('btn-print-report')?.addEventListener('click', () => {
        populatePrintBriefingTemplate();
        setTimeout(() => {
            window.print();
        }, 120);
    });

    function populatePrintBriefingTemplate() {
        const pred = model.predict(currentInputs);
        const hourly = model.generateHourlyForecast(currentInputs);

        // Metadata
        const now = new Date();
        const elDate = document.getElementById('print-timestamp');
        const elRepId = document.getElementById('print-report-id');
        const elModelName = document.getElementById('print-model-name');
        const elHash = document.getElementById('print-auth-hash');

        if (elDate) {
            elDate.textContent = now.toLocaleDateString('en-IN', {
                day: '2-digit', month: 'short', year: 'numeric'
            }) + ' ' + now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) + ' IST';
        }
        if (elRepId) {
            const dateStr = now.toISOString().slice(0, 10).replace(/-/g, '');
            elRepId.textContent = `NCR-ENV-${dateStr}-${pred.predictedAqi}`;
        }
        if (elModelName) {
            elModelName.textContent = isBackendConnected 
                ? "GradientBoostingRegressor (ML R²=0.9886) + SQLite Telemetry"
                : "Calibrated Physics-Informed Atmospheric Dispersion Engine";
        }
        if (elHash) {
            elHash.textContent = `AGRI-${Math.random().toString(36).substring(2, 7).toUpperCase()}-NCR`;
        }

        // Section 1: KPI Snapshot
        const pAqi = document.getElementById('print-kpi-aqi');
        const pCat = document.getElementById('print-kpi-category');
        const pPm25 = document.getElementById('print-kpi-pm25');
        const pPm10 = document.getElementById('print-kpi-pm10');
        const pStubblePct = document.getElementById('print-kpi-stubble-pct');
        const pStubblePm25 = document.getElementById('print-kpi-stubble-pm25');
        const pAirshed = document.getElementById('print-kpi-airshed-score');
        const pInversion = document.getElementById('print-kpi-inversion');
        const pLag = document.getElementById('print-kpi-lag');

        if (pAqi) pAqi.textContent = pred.predictedAqi;
        if (pCat) pCat.textContent = `${pred.category} (${pred.riskLevel} Risk)`;
        if (pPm25) pPm25.innerHTML = `${pred.totalPm25} <small>µg/m³</small>`;
        if (pPm10) pPm10.textContent = `${pred.totalPm10} µg/m³`;
        if (pStubblePct) pStubblePct.textContent = `${pred.paraliPct}%`;
        if (pStubblePm25) pStubblePm25.textContent = `+${pred.stubblePm25} µg/m³`;
        if (pAirshed) pAirshed.textContent = `${pred.airshedScore} / 100`;
        if (pInversion) pInversion.textContent = `${pred.pblTrappingFactor}x`;
        if (pLag) pLag.textContent = `~${pred.transportHours} hrs`;

        // Section 2: Meteorological
        const pMetFires = document.getElementById('print-met-fires');
        const pMetWindSpeed = document.getElementById('print-met-wind-speed');
        const pMetWindDir = document.getElementById('print-met-wind-dir');
        const pMetPbl = document.getElementById('print-met-pbl');
        const pMetDirFactor = document.getElementById('print-met-dir-factor');
        const pMetBaseline = document.getElementById('print-met-baseline');

        if (pMetFires) pMetFires.textContent = currentInputs.fireCount.toLocaleString();
        if (pMetWindSpeed) pMetWindSpeed.textContent = `${currentInputs.windSpeed} km/h`;
        if (pMetWindDir) pMetWindDir.textContent = `${currentInputs.windDirectionDeg}° ${getCompassDirection(currentInputs.windDirectionDeg)}`;
        if (pMetPbl) pMetPbl.textContent = `${currentInputs.pblHeight} meters`;
        if (pMetDirFactor) pMetDirFactor.textContent = `${pred.dirFactor}% alignment to NCR`;
        if (pMetBaseline) pMetBaseline.textContent = `${currentInputs.urbanBaselineAqi} AQI`;

        // Section 3: GRAP Badge & Directives
        const pGrapBadge = document.getElementById('print-grap-stage-badge');
        const pGrapList = document.getElementById('print-grap-directives-list');
        if (pGrapBadge) {
            pGrapBadge.textContent = pred.grapStage === "None" ? "NORMAL AIRSHED BASELINE" : `GRAP ${pred.grapStage.toUpperCase()} • ${pred.category.toUpperCase()} (AQI ${pred.predictedAqi})`;
        }
        if (pGrapList) {
            const currentStageObj = DEMO_DATA.grapStages.find(g => g.stage === pred.grapStage) || DEMO_DATA.grapStages[1];
            pGrapList.innerHTML = currentStageObj.actions.map(act => `<li>${act}</li>`).join('');
        }

        // Section 4: Source Apportionment
        const pSrcStubble = document.getElementById('print-src-stubble');
        const pSrcStubbleVal = document.getElementById('print-src-stubble-val');
        const pSrcVehicles = document.getElementById('print-src-vehicles');
        const pSrcVehiclesVal = document.getElementById('print-src-vehicles-val');
        const pSrcSec = document.getElementById('print-src-secondary');
        const pSrcSecVal = document.getElementById('print-src-secondary-val');
        const pSrcDust = document.getElementById('print-src-dust');
        const pSrcDustVal = document.getElementById('print-src-dust-val');
        const pSrcInd = document.getElementById('print-src-industry');
        const pSrcIndVal = document.getElementById('print-src-industry-val');

        const stubblePct = Math.max(5, Math.min(80, Math.round(pred.paraliPct)));
        const remPct = 100 - stubblePct;
        const vehPct = Math.round(remPct * 0.42);
        const secPct = Math.round(remPct * 0.28);
        const dustPct = Math.round(remPct * 0.18);
        const indPct = Math.max(2, 100 - stubblePct - vehPct - secPct - dustPct);

        if (pSrcStubble) pSrcStubble.textContent = `${stubblePct}.0%`;
        if (pSrcStubbleVal) pSrcStubbleVal.textContent = `${(pred.totalPm25 * stubblePct / 100).toFixed(1)} µg/m³`;
        if (pSrcVehicles) pSrcVehicles.textContent = `${vehPct}.0%`;
        if (pSrcVehiclesVal) pSrcVehiclesVal.textContent = `${(pred.totalPm25 * vehPct / 100).toFixed(1)} µg/m³`;
        if (pSrcSec) pSrcSec.textContent = `${secPct}.0%`;
        if (pSrcSecVal) pSrcSecVal.textContent = `${(pred.totalPm25 * secPct / 100).toFixed(1)} µg/m³`;
        if (pSrcDust) pSrcDust.textContent = `${dustPct}.0%`;
        if (pSrcDustVal) pSrcDustVal.textContent = `${(pred.totalPm25 * dustPct / 100).toFixed(1)} µg/m³`;
        if (pSrcInd) pSrcInd.textContent = `${indPct}.0%`;
        if (pSrcIndVal) pSrcIndVal.textContent = `${(pred.totalPm25 * indPct / 100).toFixed(1)} µg/m³`;

        // Section 5: Diurnal Checkpoints
        const pDiurnalTbody = document.getElementById('print-diurnal-tbody');
        if (pDiurnalTbody && hourly && hourly.length) {
            const checkpoints = [4, 8, 12, 15, 19, 23];
            const rows = checkpoints.map(ch => {
                const hData = hourly.find(d => d.hourNum === ch) || hourly[0];
                let regime = "Standard Boundary Dispersion";
                if (ch === 4) regime = "Nocturnal Cold Radiation Inversion Peak";
                else if (ch === 8) regime = "Morning Rush Traffic + Low Mixing";
                else if (ch === 12) regime = "Midday Convective Solar Heating";
                else if (ch === 15) regime = "Maximum Boundary Layer Expansion (Day Low)";
                else if (ch === 19) regime = "Evening Boundary Layer Compression Onset";
                else if (ch === 23) regime = "Nocturnal Plume Trapping";

                return `
                    <tr>
                        <td><strong>${hData.time}</strong></td>
                        <td>${regime}</td>
                        <td><strong>${hData.aqi}</strong></td>
                        <td>${hData.category}</td>
                        <td>${hData.pm25} µg/m³</td>
                        <td>${hData.stubblePct}%</td>
                        <td>${hData.pbl} m</td>
                    </tr>
                `;
            });
            pDiurnalTbody.innerHTML = rows.join('');
        }

        // Section 6: Monitoring Stations Table
        const pStationsTbody = document.getElementById('print-stations-tbody');
        if (pStationsTbody && DEMO_DATA.monitoringStations) {
            const topStations = DEMO_DATA.monitoringStations.slice(0, 6);
            pStationsTbody.innerHTML = topStations.map(st => `
                <tr>
                    <td><strong>${st.name}</strong></td>
                    <td>${st.type}</td>
                    <td><strong>${st.aqi}</strong></td>
                    <td>${st.category}</td>
                    <td>${st.pm25}</td>
                    <td>${st.pm10}</td>
                    <td><strong>${st.paraliPct}%</strong></td>
                </tr>
            `).join('');
        }

        // Section 7: Upwind Fire Clusters Table
        const pHotspotsTbody = document.getElementById('print-hotspots-tbody');
        if (pHotspotsTbody && DEMO_DATA.fireHotspots) {
            const topFires = DEMO_DATA.fireHotspots.slice(0, 6);
            pHotspotsTbody.innerHTML = topFires.map(f => `
                <tr>
                    <td><strong>${f.district}</strong></td>
                    <td>${f.state}</td>
                    <td><strong>${f.fireCount} fires</strong></td>
                    <td>${f.avgFRP} MW</td>
                    <td>${f.harvestProgress}</td>
                    <td>${f.smokeIntensity} Plume Inflow</td>
                </tr>
            `).join('');
        }

        // Section 8: Health Advisories
        const pAdvGen = document.getElementById('print-health-general');
        const pAdvSens = document.getElementById('print-health-sensitive');
        const pAdvOut = document.getElementById('print-health-outdoor');
        const cat = DEMO_DATA.aqiCategories.find(c => pred.predictedAqi >= c.min && pred.predictedAqi <= c.max) || DEMO_DATA.aqiCategories[DEMO_DATA.aqiCategories.length - 1];

        if (pAdvGen) pAdvGen.textContent = cat.advisory;
        if (pAdvSens) {
            pAdvSens.textContent = pred.predictedAqi > 400 
                ? "Severe respiratory risk. Avoid outdoor exposure entirely. Keep medical bronchodilator inhalers accessible; run HEPA air filtration."
                : "Asthma and cardiac patients should strictly avoid morning/evening walks and carry prescribed rescue medication.";
        }
        if (pAdvOut) {
            pAdvOut.textContent = pred.predictedAqi > 400
                ? "Mandatory certified N95 or FFP2 respirators required for all outdoor staff, traffic police, and construction monitors."
                : "Avoid heavy cardiovascular workouts outdoors during traffic hours (18:00 - 09:00 IST).";
        }
    }

    // 12. Toast Notification Helper
    function showNotification(msg, type = "info") {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toast = document.createElement('div');
        toast.className = `toast-item toast-${type}`;
        toast.innerHTML = `
            <div class="toast-text">${msg}</div>
            <button class="toast-close">&times;</button>
        `;

        toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add('fade-out');
            setTimeout(() => toast.remove(), 400);
        }, 4500);
    }

    // 13. Live Simulation Toggle (Simulate minor micro-variations)
    const toggleLiveSim = document.getElementById('toggle-live-sim');
    toggleLiveSim?.addEventListener('change', (e) => {
        if (e.target.checked) {
            startLiveSim();
            showNotification("Live simulation loop active: Simulating micro-variations every 3.5s", "info");
        } else {
            stopLiveSim();
            showNotification("Live simulation paused", "info");
        }
    });

    function startLiveSim() {
        if (liveSimulationInterval) clearInterval(liveSimulationInterval);
        lastTelemetryTime = Date.now();

        liveSimulationInterval = setInterval(() => {
            lastTelemetryTime = Date.now();

            // Apply slight natural atmospheric turbulence variance
            const windDelta = (Math.random() - 0.5) * 0.7;
            currentInputs.windSpeed = Math.max(3.5, Math.min(28, currentInputs.windSpeed + windDelta));
            if (sliderWindSpeed) sliderWindSpeed.value = currentInputs.windSpeed.toFixed(1);

            const dirDelta = (Math.random() - 0.5) * 2.2;
            currentInputs.windDirectionDeg = (Math.round(currentInputs.windDirectionDeg + dirDelta) + 360) % 360;
            if (sliderWindDir) sliderWindDir.value = currentInputs.windDirectionDeg;

            // Subtle thermal anomaly fire count fluctuation
            const fireDelta = Math.round((Math.random() - 0.5) * 6);
            currentInputs.fireCount = Math.max(100, Math.min(5000, currentInputs.fireCount + fireDelta));
            if (sliderFireCount) sliderFireCount.value = currentInputs.fireCount;

            syncInputsFromUI();
            updateTelemetryTickerText();
        }, 3500);

        if (!tickerInterval) {
            tickerInterval = setInterval(updateTelemetryTickerText, 1000);
        }
    }

    function updateTelemetryTickerText() {
        const syncEl = document.getElementById('telemetry-sync-time');
        if (!syncEl) return;
        const elapsedSec = Math.floor((Date.now() - lastTelemetryTime) / 1000);
        if (elapsedSec <= 1) {
            syncEl.textContent = "Synced just now";
        } else {
            syncEl.textContent = `Synced ${elapsedSec}s ago`;
        }
    }

    function stopLiveSim() {
        if (liveSimulationInterval) {
            clearInterval(liveSimulationInterval);
            liveSimulationInterval = null;
        }
    }

    // Bind Station Pills in the Live Telemetry Ticker
    document.querySelectorAll('.station-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            const stId = chip.getAttribute('data-station-id');
            const station = DEMO_DATA.monitoringStations.find(s => s.id === stId);
            if (station) {
                showDetailModal({ type: 'station', data: station });
            }
        });
    });

    // 13b. NASA FIRMS Satellite Telemetry Controls
    const firmsSensorSelect = document.getElementById('firms-sensor-select');
    const firmsClassFilter = document.getElementById('firms-class-filter');
    const btnSyncFirms = document.getElementById('btn-sync-firms');
    const firmsSyncSpinner = document.getElementById('firms-sync-spinner');
    const firmsProviderBadge = document.getElementById('firms-provider-badge');
    const firmsCountPill = document.getElementById('firms-count-pill');

    if (firmsClassFilter) {
        firmsClassFilter.addEventListener('change', (e) => {
            if (map) {
                map.setClassFilter(e.target.value);
            }
        });
    }

    if (btnSyncFirms) {
        btnSyncFirms.addEventListener('click', async () => {
            const sensor = firmsSensorSelect ? firmsSensorSelect.value : 'VIIRS_NOAA20_NRT';
            btnSyncFirms.disabled = true;
            if (firmsSyncSpinner) firmsSyncSpinner.style.display = 'inline-block';

            try {
                showNotification(`Initiating satellite synchronization for ${sensor}...`, 'info');
                const res = await fetch(`${API_BASE}/api/v1/firms/sync`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sensor: sensor, region: 'indo_gangetic_airshed', day_range: 3 })
                });

                if (res.ok) {
                    const result = await res.json();
                    if (result.status === 'SUCCESS') {
                        showNotification(`Satellite sync successful: ${result.records_inserted} new, ${result.records_skipped} duplicate observations.`, 'success');
                        await loadFirmsData();
                    } else {
                        showNotification(`Sync warning: ${result.message}`, 'warning');
                    }
                } else {
                    const err = await res.json();
                    showNotification(`Sync error: ${err.detail || 'Failed to sync with NASA FIRMS'}`, 'error');
                }
            } catch (err) {
                showNotification(`Network error during satellite sync: ${err.message}`, 'error');
            } finally {
                btnSyncFirms.disabled = false;
                if (firmsSyncSpinner) firmsSyncSpinner.style.display = 'none';
            }
        });
    }

    async function loadFirmsData() {
        if (!isBackendConnected) return;
        try {
            const [statusRes, obsRes] = await Promise.all([
                fetch(`${API_BASE}/api/v1/firms/status`),
                fetch(`${API_BASE}/api/v1/firms/observations?limit=1000`)
            ]);

            if (statusRes.ok) {
                const pStatus = await statusRes.json();
                if (firmsProviderBadge) {
                    if (pStatus.configured) {
                        firmsProviderBadge.style.background = '#ecfdf5';
                        firmsProviderBadge.style.color = '#059669';
                        firmsProviderBadge.style.borderColor = '#a7f3d0';
                        firmsProviderBadge.textContent = `● NASA Earthdata: Connected (${pStatus.masked_key})`;
                    } else {
                        firmsProviderBadge.style.background = '#fffbeb';
                        firmsProviderBadge.style.color = '#b45309';
                        firmsProviderBadge.style.borderColor = '#fde68a';
                        firmsProviderBadge.textContent = `⚠️ NASA Earthdata: Key Unconfigured`;
                    }
                }
            }

            if (obsRes.ok) {
                const observations = await obsRes.json();
                if (firmsCountPill) {
                    firmsCountPill.textContent = `${observations.length} Satellite Detections Loaded`;
                }
                if (map && observations && observations.length > 0) {
                    map.setObservations(observations);
                }
            }
        } catch (e) {
            console.log("[NASA FIRMS] Live satellite data loading deferred:", e);
        }
    }

    // 14. Check Backend API Connectivity & Hydrate Live Data
    async function checkBackendConnectivity() {
        const statusPill = document.querySelector('.status-pill');
        const demoBannerContent = document.querySelector('.demo-banner-content');

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2500);

            const res = await fetch(`${API_BASE}/api/status`, { signal: controller.signal });
            clearTimeout(timeoutId);

            if (res.ok) {
                const data = await res.json();
                isBackendConnected = true;

                // Update UI Badges to indicate live Python backend
                if (statusPill) {
                    statusPill.className = "status-pill online";
                    statusPill.innerHTML = `<span class="pulse-dot"></span> ⚡ Python Backend & ML Active`;
                    statusPill.title = `Connected to FastAPI + SQLite. ML Model: ${data.mlModel} (R² = ${data.mlAccuracyR2})`;
                }

                if (demoBannerContent) {
                    demoBannerContent.innerHTML = `
                        <strong>⚡ Live Python 3.13 + SQLite Backend Active</strong>
                        <p>Connected to FastAPI server. Predictions powered by trained <strong>${data.mlModel}</strong> (Accuracy R²: <strong>${data.mlAccuracyR2}</strong>) with real-time SQLite persistence.</p>
                    `;
                }

                // Hydrate database data
                loadDatabaseData();
                showNotification("Connected to Python FastAPI & SQLite Backend with trained ML model!", "success");
            }
        } catch (e) {
            isBackendConnected = false;
            console.log("[Notice] Python backend not detected at " + API_BASE + ". Operating in Standalone Offline Simulation Mode.");
            if (statusPill) {
                statusPill.className = "status-pill demo";
                statusPill.innerHTML = `<span class="pulse-dot"></span> Standalone Offline Mode`;
                statusPill.title = "Running locally. Start 'python backend/run.py' for Python backend & SQLite persistence.";
            }
        }
    }

    async function loadDatabaseData() {
        try {
            const [stationsRes, hotspotsRes, trendsRes, districtsRes, thresholdsRes] = await Promise.all([
                fetch(`${API_BASE}/api/stations`),
                fetch(`${API_BASE}/api/hotspots`),
                fetch(`${API_BASE}/api/trends/weekly`),
                fetch(`${API_BASE}/api/districts`),
                fetch(`${API_BASE}/api/thresholds`)
            ]);

            if (stationsRes.ok) {
                const stations = await stationsRes.json();
                if (stations && stations.length) DEMO_DATA.monitoringStations.splice(0, DEMO_DATA.monitoringStations.length, ...stations);
            }
            if (hotspotsRes.ok) {
                const hotspots = await hotspotsRes.json();
                if (hotspots && hotspots.length) DEMO_DATA.fireHotspots.splice(0, DEMO_DATA.fireHotspots.length, ...hotspots);
            }
            if (trendsRes.ok) {
                const trends = await trendsRes.json();
                if (trends && trends.length) {
                    DEMO_DATA.weeklyTrend.splice(0, DEMO_DATA.weeklyTrend.length, ...trends);
                    charts.renderWeeklyTrendChart('chart-weekly-trend', DEMO_DATA.weeklyTrend);
                }
            }
            if (districtsRes.ok) {
                const districts = await districtsRes.json();
                if (districts && districts.length) {
                    DEMO_DATA.districtFireCounts.splice(0, DEMO_DATA.districtFireCounts.length, ...districts);
                    charts.renderDistrictBars('chart-district-bars', DEMO_DATA.districtFireCounts);
                }
            }
            if (thresholdsRes.ok) {
                const th = await thresholdsRes.json();
                activeAlertThreshold = th;
                if (inputThreshAqi) inputThreshAqi.value = th.aqi;
                if (inputThreshFires) inputThreshFires.value = th.fires;
            }

            // Hydrate live NASA FIRMS observations
            await loadFirmsData();
        } catch (err) {
            console.error("Error hydrating data from SQLite:", err);
        }
    }

    // 15. Initial Load
    syncInputsFromUI();
    updateVisualizations();
    checkBackendConnectivity();

    // Auto-start live simulation loop by default
    if (toggleLiveSim && toggleLiveSim.checked) {
        startLiveSim();
    } else {
        startLiveSim();
    }

    // Responsive window resize debounced handler
    let resizeDebounce = null;
    window.addEventListener('resize', () => {
        if (resizeDebounce) clearTimeout(resizeDebounce);
        resizeDebounce = setTimeout(() => {
            if (map) map.resize();
            updateVisualizations();
        }, 150);
    });

    console.log("AgriSmoke AI initialized.");
});
