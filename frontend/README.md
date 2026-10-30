# 🌾 AgriSmoke AI &bull; Crop-Burning & Urban Air Quality Prediction System
### *Indo-Gangetic Airshed (Punjab, Haryana & Delhi-NCR)*

A fully self-contained, high-performance web platform designed to analyze, simulate, and predict the transboundary atmospheric transport of crop-residue (parali) burning smoke and its impact on urban air quality across the Delhi National Capital Region (NCR).

---

## ⚡ Zero-Installation & Offline Readiness Guarantee
- **No package installations required**: Zero `npm install`, zero `pip install`, zero build scripts.
- **Works directly via `file:///`**: Simply double-click [index.html](file:///c:/Users/dhara/Downloads/evs%20fine/index.html) or open it in **Microsoft Edge**.
- **No development server needed**: Runs offline with zero external CDN dependencies (no external Google fonts, no remote mapping tiles, no remote charting libraries).

---

## 🔬 Core System Modules & Features

### 1. 📊 Executive Air Quality Dashboard
- **Real-Time Delhi-NCR Composite AQI**: Dynamic CPCB color-coded KPI badge, category indicator (Good, Satisfactory, Moderate, Poor, Very Poor, Severe, Emergency).
- **SAFAR-Calibrated Source Apportionment**: Interactive SVG Donut chart displaying the fraction of fine particulates originating from agricultural burning (~35%) vs. vehicular emissions (~26%), secondary aerosols (~17%), road dust (~12%), and industry (~10%).
- **24-Hour Diurnal AQI & Smoke Plume Forecast Curve**: High-resolution pure SVG chart tracking the day-night boundary layer compression and evening smoke transport surges.
- **7-Day Trend Comparison**: Comparative bar-and-line chart showing farm fire anomaly counts against Delhi air quality levels.
- **Speedometer AQI Radial Gauge**: Calibrated against the Central Pollution Control Board (CPCB) 0–500 scale.
- **Top Burning Districts Bar Chart**: Ranking high-density burning zones (Sangrur, Firozpur, Tarn Taran, Bathinda, Ludhiana, etc.).
- **Health Advisory Matrix**: Actionable clinical guidance tailored for general citizens, sensitive groups (asthmatics/children), and outdoor workers.

### 2. 🗺️ Geospatial Fire & Smoke Plume Map (Interactive Canvas)
- **Zero-Dependency Native Canvas Geospatial Engine**: Equirectangular projection mapped to real geographic coordinates ($27.8^\circ\text{N} - 32.6^\circ\text{N}$, $73.8^\circ\text{E} - 78.8^\circ\text{E}$).
- **Animated Smoke Plume Particle Flow**: Hundreds of continuous smoke particles drift along real-time wind vectors from Punjab and Haryana fire hotspots directly toward Delhi-NCR.
- **Active Thermal Anomalies (VIIRS/MODIS)**: Pulsing heat signatures with Fire Radiative Power (FRP in MW) data.
- **Delhi-NCR Monitoring Stations**: Anand Vihar, Punjabi Bagh, Mandir Marg, R.K. Puram, IGI Airport T3, Bawana, Noida Sector 62, Gurugram, and Faridabad with click-to-inspect popups.
- **Interactive Layer Toggles**: Thermal Fires, Smoke Plume Particles, Wind Streamlines, Urban Stations, and Regional Boundaries.
- **Navigation Controls**: Pan & drag, scroll to zoom, zoom buttons, reset view, and orientation compass.

### 3. 🧮 AI Prediction & Scenario Engine
- **Deterministic Multi-Variable Atmospheric Dispersion Model**:
  - Incorporates Gaussian plume dispersion concepts, wind directional alignment factors ($\cos^{1.8}(\theta - 312^\circ)$), boundary layer volume trapping ($C \propto 1/H_{PBL}^{0.75}$), and CPCB piecewise linear PM2.5-to-AQI conversion.
- **Interactive Sliders**:
  1. Active Farm Fires (0 to 5,000)
  2. Transport Wind Speed (2 to 35 km/h)
  3. Wind Direction Angle ($0^\circ - 360^\circ$ with live compass label)
  4. Planetary Boundary Layer Mixing Height (150m to 1,500m)
  5. Delhi Internal Baseline AQI (40 to 300)
  6. Pusa Bio-Decomposer Adoption Rate (0% to 100%)
  7. In-Situ Machinery Adoption (Happy Seeder / Super SMS) (0% to 100%)
- **Instant Model Output Card**: Predicts 24h Delhi AQI, resulting PM2.5 ($\mu\text{g/m}^3$), Parali smoke contribution percentage, wind alignment efficiency, and potential AQI points saved through mitigation.
- **Scenario Presets**:
  - *Peak Stubble Burning & Low Inversion (November)*
  - *Favorable Easterly Wind Shift*
  - *Aggressive In-Situ Mitigation*
  - *Clean Baseline (Post-Rain Monsoon)*

### 4. 🚨 GRAP Stages & Early Warning Center
- **CAQM Graded Response Action Plan Matrix**: Complete breakdown of Stages I, II, III, and IV (Emergency measures including BS-III/IV bans, construction bans, truck restrictions).
- **Automated Early Warning Feed**: Critical, Warning, and Advisory level alerts with operational recommendations.
- **Custom Safety Thresholds**: Configure alerts for specific AQI or active fire levels.
- **Web Audio API Synthesizer Chime**: Generates emergency warning audio tones entirely inside the browser without external audio files.

### 5. 🌱 Policy & Mitigation Simulator
- Quantifies the public health ROI of agricultural interventions:
  - In-situ machinery subsidies (Happy Seeder, Super SMS, Balers)
  - Pusa bio-decomposer fungal spraying
  - Ex-situ biomass pelletization for thermal power plants

### 6. 📊 Data Export & Diagnostic Reporting
- **Export CSV**: Instant client-side generation and download of 24h hourly forecast telemetry via Blob and Object URL.
- **Print Briefing**: Styled `@media print` layout for one-click PDF generation or executive printing.

---

## 📁 Project Directory Structure
```
c:\Users\dhara\Downloads\evs fine\
│
├── index.html               # Main semantic single-page application structure
├── README.md                # System documentation & usage guide
│
├── css/
│   └── styles.css           # Modern dark UI, glassmorphism, responsive grid & animations
│
└── js/
    ├── demo-data.js         # Calibrated demonstration data & CPCB/NAAQS reference scales
    ├── prediction-model.js  # Atmospheric dispersion & empirical AI inference engine
    ├── map-engine.js        # Canvas geospatial map with animated smoke particles
    ├── charts-engine.js     # Standalone SVG chart rendering (Diurnal curve, donut, bars)
    └── app.js               # Application controller, tab router, alerts, and export
```

---

## 🚀 How to Open
1. Open File Explorer to `C:\Users\dhara\Downloads\evs fine`.
2. Double-click [index.html](file:///c:/Users/dhara/Downloads/evs%20fine/index.html) (or right-click &rarr; Open with &rarr; Microsoft Edge).
3. The platform will load instantly and function with complete interactivity offline.
