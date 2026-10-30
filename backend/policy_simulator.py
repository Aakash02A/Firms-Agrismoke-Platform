"""
AgriSmoke AI - Agricultural & Economic Policy Simulator
Simulates Crop Residue Management (CRM) interventions: Pusa Bio-Decomposer,
in-situ machinery (Happy Seeder / Super SMS), and ex-situ biomass pelletization.
Calculates avoided PM2.5 emissions, public health economic benefits, and Benefit-Cost Ratios (BCR).
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field

# High-priority paddy stubble burning districts in Punjab and Haryana
DISTRICT_PROFILES = {
    "PB_SANGRUR": {
        "name": "Sangrur",
        "state": "Punjab",
        "annualFiresBaseline": 3840,
        "paddyAreaHectares": 245000,
        "stubbleGeneratedTonnes": 1592500,
        "currentMachineryCount": 4200,
        "airshedProximityRisk": "CRITICAL"
    },
    "PB_FIROZPUR": {
        "name": "Firozpur",
        "state": "Punjab",
        "annualFiresBaseline": 2980,
        "paddyAreaHectares": 182000,
        "stubbleGeneratedTonnes": 1183000,
        "currentMachineryCount": 3100,
        "airshedProximityRisk": "HIGH"
    },
    "PB_BATHINDA": {
        "name": "Bathinda",
        "state": "Punjab",
        "annualFiresBaseline": 2450,
        "paddyAreaHectares": 164000,
        "stubbleGeneratedTonnes": 1066000,
        "currentMachineryCount": 2800,
        "airshedProximityRisk": "HIGH"
    },
    "PB_TARN_TARAN": {
        "name": "Tarn Taran",
        "state": "Punjab",
        "annualFiresBaseline": 2650,
        "paddyAreaHectares": 175000,
        "stubbleGeneratedTonnes": 1137500,
        "currentMachineryCount": 2600,
        "airshedProximityRisk": "HIGH"
    },
    "PB_LUDHIANA": {
        "name": "Ludhiana",
        "state": "Punjab",
        "annualFiresBaseline": 2100,
        "paddyAreaHectares": 220000,
        "stubbleGeneratedTonnes": 1430000,
        "currentMachineryCount": 4500,
        "airshedProximityRisk": "CRITICAL"
    },
    "HR_KAITHAL": {
        "name": "Kaithal",
        "state": "Haryana",
        "annualFiresBaseline": 1280,
        "paddyAreaHectares": 165000,
        "stubbleGeneratedTonnes": 1072500,
        "currentMachineryCount": 2900,
        "airshedProximityRisk": "CRITICAL"
    },
    "HR_FATEHABAD": {
        "name": "Fatehabad",
        "state": "Haryana",
        "annualFiresBaseline": 1450,
        "paddyAreaHectares": 148000,
        "stubbleGeneratedTonnes": 962000,
        "currentMachineryCount": 2400,
        "airshedProximityRisk": "HIGH"
    },
    "HR_JIND": {
        "name": "Jind",
        "state": "Haryana",
        "annualFiresBaseline": 980,
        "paddyAreaHectares": 132000,
        "stubbleGeneratedTonnes": 858000,
        "currentMachineryCount": 2100,
        "airshedProximityRisk": "CRITICAL"
    }
}


class PolicySimulationRequest(BaseModel):
    districtId: str = Field(default="PB_SANGRUR", description="Target district ID")
    bioDecomposerAdoptionPct: float = Field(default=35.0, ge=0.0, le=100.0, description="% area with Bio-decomposer spray")
    happySeederAdoptionPct: float = Field(default=40.0, ge=0.0, le=100.0, description="% area with Happy Seeder / Super SMS")
    subsidyBudgetCrores: float = Field(default=15.0, ge=0.5, le=500.0, description="Allocated government subsidy budget (₹ Crores)")
    exSituPelletizationPct: float = Field(default=15.0, ge=0.0, le=100.0, description="% biomass diverted to thermal pellets")


class PolicySimulationResult(BaseModel):
    districtId: str
    districtName: str
    state: str
    baselineAnnualFires: int
    simulatedFiresAfterIntervention: int
    firesPrevented: int
    fireReductionPct: float
    biomassDivertedTonnes: float
    pm25AvoidedTonnes: float
    co2EquivalentAvoidedTonnes: float
    estimatedSubsidyCostCrores: float
    healthEconomicBenefitsCrores: float
    netEconomicSavingsCrores: float
    benefitCostRatio: float
    policyRating: str
    recommendedAction: str


def get_available_districts() -> List[Dict[str, Any]]:
    """Returns available district profiles for policy selection."""
    return [
        {
            "id": k,
            "name": v["name"],
            "state": v["state"],
            "annualFiresBaseline": v["annualFiresBaseline"],
            "paddyAreaHectares": v["paddyAreaHectares"],
            "airshedProximityRisk": v["airshedProximityRisk"]
        }
        for k, v in DISTRICT_PROFILES.items()
    ]


def simulate_policy_intervention(req: PolicySimulationRequest) -> PolicySimulationResult:
    """
    Computes comprehensive emissions reduction and public health economic outcomes.
    
    Calibration factors:
    - 1 hectare paddy yields ~6.5 tonnes stubble.
    - 1 tonne burned paddy straw emits ~8.5 kg fine PM2.5 and ~1.5 tonnes CO2e.
    - Bio-decomposer application cost: ~₹350/hectare (subsidized ~₹250/ha).
    - Happy Seeder capital subsidy: ~₹1.0 Lakh/machine (covers ~140 ha/season).
    - Public health & economic savings: ~₹1.42 Lakh per tonne of PM2.5 eliminated from airshed (World Bank/ICRIER).
    """
    profile = DISTRICT_PROFILES.get(req.districtId, DISTRICT_PROFILES["PB_SANGRUR"])
    paddy_area = profile["paddyAreaHectares"]
    base_fires = profile["annualFiresBaseline"]
    total_stubble = profile["stubbleGeneratedTonnes"]

    # Combined mitigation rate with overlap saturation diminishing returns
    bio_ratio = req.bioDecomposerAdoptionPct / 100.0
    happy_ratio = req.happySeederAdoptionPct / 100.0
    exsitu_ratio = req.exSituPelletizationPct / 100.0

    # Total non-burned fraction (accounting for overlapping interventions)
    mitigated_fraction = min(0.95, bio_ratio * 0.40 + happy_ratio * 0.50 + exsitu_ratio * 0.25)

    simulated_fires = max(0, round(base_fires * (1.0 - mitigated_fraction)))
    fires_prevented = base_fires - simulated_fires
    fire_reduction_pct = round((fires_prevented / base_fires) * 100.0, 1)

    # Biomass diverted from burning
    biomass_diverted_tonnes = round(total_stubble * mitigated_fraction)

    # Emissions avoided
    # 8.5 kg PM2.5 per tonne = 0.0085 tonnes PM2.5 per tonne stubble
    pm25_avoided_tonnes = round(biomass_diverted_tonnes * 0.0085, 1)
    co2e_avoided_tonnes = round(biomass_diverted_tonnes * 1.46, 1)

    # Intervention costs (₹ Crores)
    # Bio-decomposer cost: area * bio_ratio * ₹300 / 10^7
    cost_bio_cr = (paddy_area * bio_ratio * 320) / 1e7
    # Additional machinery units needed: (paddy_area * happy_ratio / 140 ha per machine) * ₹1.0 Lakh subsidy / 100
    machines_needed = max(0, int((paddy_area * happy_ratio) / 140) - profile["currentMachineryCount"] // 2)
    cost_machinery_cr = (machines_needed * 100000) / 1e7
    # Pelletization logistics support: ₹180 / tonne subsidized
    cost_pellets_cr = (total_stubble * exsitu_ratio * 180) / 1e7

    estimated_subsidy_cost = round(max(0.5, cost_bio_cr + cost_machinery_cr + cost_pellets_cr), 2)

    # Economic & Healthcare Benefits (₹ Crores)
    # Each tonne PM2.5 avoided saves ~₹1.42 Lakhs in hospitalisation, DALYs, workdays lost, and aviation delays
    health_savings_cr = round((pm25_avoided_tonnes * 142000) / 1e7, 2)
    net_savings_cr = round(health_savings_cr - estimated_subsidy_cost, 2)

    # Benefit-Cost Ratio (BCR)
    bcr = round(health_savings_cr / max(0.1, estimated_subsidy_cost), 2)

    # Rating & Action
    if bcr >= 4.0:
        rating = "HIGHLY_VIABLE (BCR > 4.0x)"
        action = f"Strong recommendation: Deploy ₹{estimated_subsidy_cost} Cr package immediately in {profile['name']} before peak harvest week."
    elif bcr >= 2.0:
        rating = "ECONOMICALLY_SOUND (BCR 2.0x - 4.0x)"
        action = f"Approved for subsidy rollout: Prioritize in-situ Happy Seeder Custom Hiring Centers across {profile['name']}."
    else:
        rating = "MODERATE_RETURN"
        action = "Reallocate budget toward bio-decomposer fungal spraying to optimize cost efficiency."

    return PolicySimulationResult(
        districtId=req.districtId,
        districtName=profile["name"],
        state=profile["state"],
        baselineAnnualFires=base_fires,
        simulatedFiresAfterIntervention=simulated_fires,
        firesPrevented=fires_prevented,
        fireReductionPct=fire_reduction_pct,
        biomassDivertedTonnes=biomass_diverted_tonnes,
        pm25AvoidedTonnes=pm25_avoided_tonnes,
        co2EquivalentAvoidedTonnes=co2e_avoided_tonnes,
        estimatedSubsidyCostCrores=estimated_subsidy_cost,
        healthEconomicBenefitsCrores=health_savings_cr,
        netEconomicSavingsCrores=net_savings_cr,
        benefitCostRatio=bcr,
        policyRating=rating,
        recommendedAction=action
    )
