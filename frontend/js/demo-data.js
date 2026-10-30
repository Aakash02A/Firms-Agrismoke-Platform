/**
 * AgriSmoke AI / AeroPredict Delhi-NCR
 * Demonstration Dataset & Air Quality Standards Reference
 * 
 * NOTE: This dataset represents calibrated demonstration and seasonal historical
 * data for the Northern Indian Indo-Gangetic Plain stubble-burning season (Oct - Nov).
 * All metrics are clearly designated as demonstration data when live APIs are disconnected.
 */

const DEMO_DATA = {
    metadata: {
        systemName: "AgriSmoke AI - Crop-Burning & Urban Air Quality Prediction System",
        region: "Indo-Gangetic Plain (Punjab, Haryana, Delhi-NCR, Western UP)",
        mode: "Demonstration & Calibrated Physical-Empirical AI Model",
        season: "Post-Monsoon Kharif Paddy Residue Burning Season",
        lastUpdated: "2026-10-27 10:30 IST",
        dataSourceNotes: "Demonstration data calibrated against historical CPCB, SAFAR, and NASA VIIRS/MODIS fire anomaly benchmarks."
    },

    // Current Urban Air Quality Summary (Delhi-NCR Benchmark)
    currentUrbanStatus: {
        aqi: 382,
        category: "Very Poor",
        statusColor: "#ff3d00",
        dominantPollutant: "PM2.5",
        pm25: 236.4, // ug/m3 (24h avg)
        pm10: 388.2, // ug/m3
        no2: 54.8,   // ug/m3
        so2: 18.2,   // ug/m3
        co: 2.1,     // mg/m3
        ozone: 42.1, // ug/m3
        paraliContributionPct: 34.6, // % of PM2.5 from stubble burning
        temperature: 24.2, // deg C
        humidity: 62,      // %
        windSpeed: 11.5,   // km/h
        windDirectionDeg: 305, // North-West (blows toward SE / Delhi)
        windDirectionLabel: "NW (North-Westerly)",
        pblHeight: 480,    // Planetary boundary layer height in meters
        activeFireCount: 1684, // Current active thermal anomalies detected
        airshedRiskScore: 84  // Out of 100 (Severe risk)
    },

    // CPCB (Central Pollution Control Board, India) AQI Scale Definition
    aqiCategories: [
        { min: 0, max: 50, label: "Good", color: "#00e676", bg: "rgba(0, 230, 118, 0.15)", advisory: "Minimal impact. Enjoy normal outdoor activities." },
        { min: 51, max: 100, label: "Satisfactory", color: "#aeea00", bg: "rgba(174, 234, 0, 0.15)", advisory: "Minor breathing discomfort to sensitive people." },
        { min: 101, max: 200, label: "Moderate", color: "#ffd600", bg: "rgba(255, 214, 0, 0.15)", advisory: "Breathing discomfort to people with asthma and heart diseases." },
        { min: 201, max: 300, label: "Poor", color: "#ff9100", bg: "rgba(255, 145, 0, 0.15)", advisory: "Breathing discomfort to most people on prolonged exposure." },
        { min: 301, max: 400, label: "Very Poor", color: "#ff3d00", bg: "rgba(255, 61, 0, 0.15)", advisory: "Respiratory illness on prolonged exposure. Pronounced effect on sensitive groups." },
        { min: 401, max: 500, label: "Severe", color: "#d50000", bg: "rgba(213, 0, 0, 0.2)", advisory: "Affects healthy people and seriously impacts those with existing diseases." },
        { min: 501, max: 999, label: "Severe+ / Emergency", color: "#4a148c", bg: "rgba(74, 20, 140, 0.25)", advisory: "Public health emergency. Avoid all outdoor physical activity. Keep windows shut." }
    ],

    // Source Apportionment Breakdown (Demonstration Estimate)
    sourceApportionment: [
        { source: "Agricultural Stubble Smoke", percentage: 35, color: "#ff5722", description: "Direct parali smoke transported from Punjab & Haryana via NW winds" },
        { source: "Vehicular Emissions", percentage: 26, color: "#00b0ff", description: "Urban tailpipe diesel & petrol emissions" },
        { source: "Secondary Aerosols", percentage: 17, color: "#e040fb", description: "Atmospheric chemical transformations of SOx, NOx, VOCs" },
        { source: "Road Dust & Construction", percentage: 12, color: "#ffab00", description: "Suspended road particulate matter and construction activity" },
        { source: "Industrial & Power Plants", percentage: 10, color: "#00e676", description: "Surrounding industrial units, brick kilns, and thermal stations" }
    ],

    // Real-world representative monitoring stations in Delhi-NCR
    monitoringStations: [
        {
            id: "del_anand_vihar",
            name: "Anand Vihar, Delhi",
            type: "Urban / Traffic Inter-State Hub",
            lat: 28.6508,
            lng: 77.3152,
            aqi: 442,
            category: "Severe",
            pm25: 312.0,
            pm10: 486.0,
            paraliPct: 39,
            trend: "up"
        },
        {
            id: "del_punjabi_bagh",
            name: "Punjabi Bagh, West Delhi",
            type: "Urban Residential / Arterial",
            lat: 28.6740,
            lng: 77.1310,
            aqi: 395,
            category: "Very Poor",
            pm25: 248.5,
            pm10: 398.0,
            paraliPct: 36,
            trend: "up"
        },
        {
            id: "del_mandir_marg",
            name: "Mandir Marg, Central Delhi",
            type: "Urban Institutional",
            lat: 28.6364,
            lng: 77.1996,
            aqi: 348,
            category: "Very Poor",
            pm25: 210.0,
            pm10: 340.0,
            paraliPct: 31,
            trend: "stable"
        },
        {
            id: "del_rk_puram",
            name: "R.K. Puram, South Delhi",
            type: "Urban Residential",
            lat: 28.5660,
            lng: 77.1767,
            aqi: 372,
            category: "Very Poor",
            pm25: 228.0,
            pm10: 365.0,
            paraliPct: 33,
            trend: "up"
        },
        {
            id: "del_igi_airport",
            name: "IGI Airport T3, Delhi",
            type: "Commercial / Transport",
            lat: 28.5562,
            lng: 77.1000,
            aqi: 335,
            category: "Very Poor",
            pm25: 198.0,
            pm10: 315.0,
            paraliPct: 30,
            trend: "stable"
        },
        {
            id: "del_bawana",
            name: "Bawana, North-West Delhi",
            type: "Industrial / Upwind Inflow",
            lat: 28.7762,
            lng: 77.0511,
            aqi: 468,
            category: "Severe",
            pm25: 345.0,
            pm10: 512.0,
            paraliPct: 44,
            trend: "up"
        },
        {
            id: "noida_sec62",
            name: "Sector 62, Noida (UP)",
            type: "Suburban Commercial / IT",
            lat: 28.6272,
            lng: 77.3725,
            aqi: 388,
            category: "Very Poor",
            pm25: 240.0,
            pm10: 382.0,
            paraliPct: 35,
            trend: "up"
        },
        {
            id: "ggn_teri_gram",
            name: "Teri Gram, Gurugram (Haryana)",
            type: "Semi-Urban / South Inflow",
            lat: 28.4289,
            lng: 77.1557,
            aqi: 340,
            category: "Very Poor",
            pm25: 204.0,
            pm10: 332.0,
            paraliPct: 29,
            trend: "stable"
        },
        {
            id: "faridabad_sec16",
            name: "Sector 16A, Faridabad (Haryana)",
            type: "Industrial / Suburban",
            lat: 28.4112,
            lng: 77.3178,
            aqi: 378,
            category: "Very Poor",
            pm25: 232.0,
            pm10: 374.0,
            paraliPct: 32,
            trend: "up"
        }
    ],

    // High-activity Agricultural Fire Clusters (Punjab & Haryana Stubble Hotspots)
    fireHotspots: [
        {
            id: "fire_sangrur_1",
            district: "Sangrur",
            state: "Punjab",
            lat: 30.2458,
            lng: 75.8421,
            fireCount: 384,
            avgFRP: 42.8, // Fire Radiative Power in MW
            status: "High Density Cluster",
            harvestProgress: "82% Harvested",
            confidence: "98% (VIIRS High)",
            smokeIntensity: "High"
        },
        {
            id: "fire_firozpur_1",
            district: "Firozpur",
            state: "Punjab",
            lat: 30.9237,
            lng: 74.6122,
            fireCount: 295,
            avgFRP: 38.4,
            status: "Intense Burning",
            harvestProgress: "78% Harvested",
            confidence: "95%",
            smokeIntensity: "High"
        },
        {
            id: "fire_tarn_taran_1",
            district: "Tarn Taran",
            state: "Punjab",
            lat: 31.4519,
            lng: 74.9282,
            fireCount: 218,
            avgFRP: 35.1,
            status: "Moderate-High Density",
            harvestProgress: "85% Harvested",
            confidence: "94%",
            smokeIntensity: "Moderate"
        },
        {
            id: "fire_bathinda_1",
            district: "Bathinda",
            state: "Punjab",
            lat: 30.2110,
            lng: 74.9455,
            fireCount: 186,
            avgFRP: 31.2,
            status: "Active Cluster",
            harvestProgress: "74% Harvested",
            confidence: "92%",
            smokeIntensity: "Moderate"
        },
        {
            id: "fire_amritsar_1",
            district: "Amritsar",
            state: "Punjab",
            lat: 31.6340,
            lng: 74.8723,
            fireCount: 142,
            avgFRP: 29.5,
            status: "Scattered Fires",
            harvestProgress: "90% Harvested",
            confidence: "91%",
            smokeIntensity: "Moderate"
        },
        {
            id: "fire_ludhiana_1",
            district: "Ludhiana",
            state: "Punjab",
            lat: 30.9010,
            lng: 75.8573,
            fireCount: 154,
            avgFRP: 33.7,
            status: "Active Perimeter",
            harvestProgress: "80% Harvested",
            confidence: "93%",
            smokeIntensity: "Moderate"
        },
        {
            id: "fire_kaithal_1",
            district: "Kaithal",
            state: "Haryana",
            lat: 29.8015,
            lng: 76.3996,
            fireCount: 96,
            avgFRP: 26.4,
            status: "Moderate Cluster",
            harvestProgress: "88% Harvested",
            confidence: "89%",
            smokeIntensity: "Moderate"
        },
        {
            id: "fire_fatehabad_1",
            district: "Fatehabad",
            state: "Haryana",
            lat: 29.5140,
            lng: 75.4542,
            fireCount: 112,
            avgFRP: 28.0,
            status: "Active Burning",
            harvestProgress: "84% Harvested",
            confidence: "90%",
            smokeIntensity: "Moderate"
        },
        {
            id: "fire_karnal_1",
            district: "Karnal",
            state: "Haryana",
            lat: 29.6857,
            lng: 76.9905,
            fireCount: 65,
            avgFRP: 22.3,
            status: "Localized Fires",
            harvestProgress: "91% Harvested",
            confidence: "87%",
            smokeIntensity: "Low-Moderate"
        },
        {
            id: "fire_jind_1",
            district: "Jind",
            state: "Haryana",
            lat: 29.3140,
            lng: 76.3150,
            fireCount: 52,
            avgFRP: 20.1,
            status: "Scattered Fires",
            harvestProgress: "86% Harvested",
            confidence: "85%",
            smokeIntensity: "Low"
        }
    ],

    // 24-Hour Diurnal Forecast Data (Next 24 hours simulation)
    hourlyForecast: [
        { time: "11:00", aqi: 382, pm25: 236, stubblePct: 35, windSpeed: 11.5, pbl: 480 },
        { time: "12:00", aqi: 374, pm25: 228, stubblePct: 34, windSpeed: 12.0, pbl: 540 },
        { time: "13:00", aqi: 360, pm25: 218, stubblePct: 32, windSpeed: 13.2, pbl: 620 },
        { time: "14:00", aqi: 348, pm25: 205, stubblePct: 30, windSpeed: 13.8, pbl: 680 },
        { time: "15:00", aqi: 355, pm25: 212, stubblePct: 31, windSpeed: 13.0, pbl: 650 },
        { time: "16:00", aqi: 370, pm25: 224, stubblePct: 33, windSpeed: 11.8, pbl: 580 },
        { time: "17:00", aqi: 395, pm25: 245, stubblePct: 36, windSpeed: 9.5,  pbl: 450 },
        { time: "18:00", aqi: 418, pm25: 268, stubblePct: 38, windSpeed: 7.8,  pbl: 360 },
        { time: "19:00", aqi: 435, pm25: 285, stubblePct: 40, windSpeed: 6.5,  pbl: 310 },
        { time: "20:00", aqi: 448, pm25: 302, stubblePct: 42, windSpeed: 5.4,  pbl: 270 },
        { time: "21:00", aqi: 456, pm25: 315, stubblePct: 44, windSpeed: 4.8,  pbl: 240 },
        { time: "22:00", aqi: 462, pm25: 322, stubblePct: 45, windSpeed: 4.5,  pbl: 220 },
        { time: "23:00", aqi: 468, pm25: 330, stubblePct: 46, windSpeed: 4.2,  pbl: 210 },
        { time: "00:00", aqi: 474, pm25: 338, stubblePct: 46, windSpeed: 4.0,  pbl: 200 },
        { time: "01:00", aqi: 479, pm25: 344, stubblePct: 47, windSpeed: 3.8,  pbl: 190 },
        { time: "02:00", aqi: 482, pm25: 348, stubblePct: 47, windSpeed: 3.7,  pbl: 185 },
        { time: "03:00", aqi: 486, pm25: 352, stubblePct: 48, windSpeed: 3.6,  pbl: 180 },
        { time: "04:00", aqi: 490, pm25: 356, stubblePct: 48, windSpeed: 3.5,  pbl: 175 },
        { time: "05:00", aqi: 492, pm25: 360, stubblePct: 49, windSpeed: 3.6,  pbl: 180 },
        { time: "06:00", aqi: 488, pm25: 355, stubblePct: 48, windSpeed: 4.2,  pbl: 210 },
        { time: "07:00", aqi: 475, pm25: 340, stubblePct: 46, windSpeed: 5.5,  pbl: 260 },
        { time: "08:00", aqi: 450, pm25: 315, stubblePct: 43, windSpeed: 7.2,  pbl: 330 },
        { time: "09:00", aqi: 422, pm25: 280, stubblePct: 39, windSpeed: 9.0,  pbl: 410 },
        { time: "10:00", aqi: 395, pm25: 250, stubblePct: 36, windSpeed: 10.5, pbl: 470 }
    ],

    // 7-Day Trend Comparison
    weeklyTrend: [
        { day: "Oct 21", aqi: 242, fires: 620,  pm25: 145, stubblePct: 18, grapStage: "Stage II" },
        { day: "Oct 22", aqi: 278, fires: 840,  pm25: 168, stubblePct: 22, grapStage: "Stage II" },
        { day: "Oct 23", aqi: 315, fires: 1120, pm25: 194, stubblePct: 26, grapStage: "Stage III" },
        { day: "Oct 24", aqi: 342, fires: 1390, pm25: 212, stubblePct: 30, grapStage: "Stage III" },
        { day: "Oct 25", aqi: 365, fires: 1540, pm25: 225, stubblePct: 32, grapStage: "Stage III" },
        { day: "Oct 26", aqi: 378, fires: 1610, pm25: 232, stubblePct: 33, grapStage: "Stage III" },
        { day: "Oct 27 (Today)", aqi: 382, fires: 1684, pm25: 236, stubblePct: 35, grapStage: "Stage III" }
    ],

    // District-wise Fire Count Comparison
    districtFireCounts: [
        { district: "Sangrur", fires: 384, state: "Punjab" },
        { district: "Firozpur", fires: 295, state: "Punjab" },
        { district: "Tarn Taran", fires: 218, state: "Punjab" },
        { district: "Bathinda", fires: 186, state: "Punjab" },
        { district: "Ludhiana", fires: 154, state: "Punjab" },
        { district: "Amritsar", fires: 142, state: "Punjab" },
        { district: "Fatehabad", fires: 112, state: "Haryana" },
        { district: "Kaithal", fires: 96, state: "Haryana" },
        { district: "Karnal", fires: 65, state: "Haryana" },
        { district: "Jind", fires: 52, state: "Haryana" }
    ],

    // Graded Response Action Plan (GRAP) Guidelines from Commission for Air Quality Management (CAQM)
    grapStages: [
        {
            stage: "Stage I",
            title: "Poor (AQI 201 - 300)",
            active: false,
            actions: [
                "Strict enforcement of dust control at construction sites > 500 sq.m",
                "Periodic mechanized road sweeping and water sprinkling",
                "Strict checks on polluting vehicles and non-destined commercial trucks",
                "Ban on open burning of municipal solid waste and biomass"
            ]
        },
        {
            stage: "Stage II",
            title: "Very Poor (AQI 301 - 400)",
            active: true, // Current active stage
            actions: [
                "Daily water sprinkling along with dust suppressants on major transit corridors",
                "Enhanced parking fees to discourage private transport usage",
                "Augment CNG/electric bus and metro services with higher frequency",
                "Uninterrupted power supply to prevent diesel generator (DG) usage"
            ]
        },
        {
            stage: "Stage III",
            title: "Severe (AQI 401 - 450)",
            active: false,
            upcomingNotice: "Forecasted threshold entry expected between 18:00 - 22:00 IST today",
            actions: [
                "Strict ban on non-essential construction and demolition activities",
                "Prohibition on plying of BS-III petrol and BS-IV diesel 4-wheelers in Delhi-NCR",
                "Closure of stone crushers and mining activities across NCR",
                "States may discontinue physical classes for children up to Class V"
            ]
        },
        {
            stage: "Stage IV",
            title: "Severe+ / Emergency (AQI > 450)",
            active: false,
            actions: [
                "Ban on entry of non-electric / non-CNG trucks into Delhi (except essential commodities)",
                "Prohibition on running of commercial diesel light goods vehicles registered outside Delhi",
                "Closure of all construction and public project development",
                "Online mode for educational institutions (Classes VI - IX and XI)",
                "Work from home for 50% staff in public and private offices"
            ]
        }
    ],

    // Active Early Warning Alerts
    activeAlerts: [
        {
            id: "alt_01",
            level: "CRITICAL",
            type: "Severe Smog Influx",
            timestamp: "10:15 IST",
            title: "North-Westerly Wind Vector Transporting Dense Stubble Plume to NCR",
            detail: "Thermal satellite telemetry shows 1,684 active fires across Punjab & Haryana. North-westerly winds (11.5 km/h) combined with lowering nocturnal boundary layer (<250m) are projected to push Delhi AQI past 440 by midnight.",
            actionRequired: "Enforce GRAP Stage III preemptive bans on polluting vehicles; advise vulnerable populations to remain indoors."
        },
        {
            id: "alt_02",
            level: "WARNING",
            type: "Boundary Layer Trapping",
            timestamp: "09:40 IST",
            title: "Severe Temperature Inversion & Calm Surface Winds Expected Tonight",
            detail: "Mixing height expected to compress to 175m at 04:00 IST. Pollutants from agricultural burning and vehicular emissions will remain trapped near ground level.",
            actionRequired: "Deploy mechanized mist sprayers and anti-smog guns across 13 identified NCR hotspots."
        },
        {
            id: "alt_03",
            level: "ADVISORY",
            type: "Public Health Warning",
            timestamp: "08:00 IST",
            title: "High Particulate PM2.5 Exposure Advisory for High-Risk Demographics",
            detail: "Ambient PM2.5 levels exceed 230 µg/m³ (approx 15 times the WHO safe guideline). Asthma patients and elderly citizens must avoid outdoor exercise.",
            actionRequired: "Wear certified N95 masks if outdoors; operate indoor HEPA purifiers in closed rooms."
        }
    ],

    // Simulation Presets for Testing & Demonstration
    presets: {
        peakBurning: {
            name: "Peak Stubble Burning & Severe Inversion (Post-Harvest Nov)",
            fireCount: 3450,
            windSpeed: 8.5,
            windDirectionDeg: 315, // NW direct to Delhi
            pblHeight: 220,
            burnAreaHectares: 120000,
            urbanBaselineAqi: 220,
            bioDecomposerAdoption: 15,
            happySeederAdoption: 25,
            description: "Simulates peak November harvest with thousands of fires, low planetary boundary layer, and direct NW winds carrying smoke plumes into Delhi."
        },
        favorableWind: {
            name: "Favorable Dispersion (Strong Easterly Wind Shift)",
            fireCount: 1800,
            windSpeed: 22.0,
            windDirectionDeg: 90, // Easterly - blows smoke AWAY from Delhi
            pblHeight: 850,
            burnAreaHectares: 75000,
            urbanBaselineAqi: 180,
            bioDecomposerAdoption: 30,
            happySeederAdoption: 40,
            description: "High burning in Punjab/Haryana, but easterly wind shift diverts the smoke plume away from the Delhi metropolitan airshed."
        },
        aggressiveMitigation: {
            name: "Aggressive In-Situ & Ex-Situ Stubble Mitigation",
            fireCount: 420,
            windSpeed: 12.0,
            windDirectionDeg: 310,
            pblHeight: 520,
            burnAreaHectares: 25000,
            urbanBaselineAqi: 160,
            bioDecomposerAdoption: 75,
            happySeederAdoption: 70,
            description: "Simulates massive government subsidy deployment, high Happy Seeder adoption, and bio-decomposer spraying reducing parali fires by >75%."
        },
        monsoonClean: {
            name: "Monsoon Baseline (Clean Airshed)",
            fireCount: 15,
            windSpeed: 18.0,
            windDirectionDeg: 140, // SE monsoon
            pblHeight: 1200,
            burnAreaHectares: 2000,
            urbanBaselineAqi: 65,
            bioDecomposerAdoption: 90,
            happySeederAdoption: 85,
            description: "Baseline scenario representing clear post-rain atmospheric conditions with negligible agricultural burning."
        }
    }
};

// Make DEMO_DATA available globally
window.DEMO_DATA = DEMO_DATA;
