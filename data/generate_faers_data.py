"""Synthetic FDA FAERS Data Generator.

Generates realistic adverse event reports with embedded safety signals
that the SignalShield agents should detect:

Signal 1: Cardizol-X → cardiac arrhythmia spike (4x baseline, last 90 days)
Signal 2: Neurofen-Plus → hepatotoxicity in 65+ females (rising trend)
Signal 3: Arthrex-200 → rhabdomyolysis with statin co-prescription
"""

import json
import random
import uuid
import argparse
import logging
from datetime import datetime, timedelta
from pathlib import Path

from elasticsearch import Elasticsearch, helpers
from faker import Faker
from tqdm import tqdm

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

fake = Faker()
Faker.seed(42)
random.seed(42)

# ── Pharmaceutical Domain Data ───────────────────────────

DRUG_CATALOG = [
    # (brand_name, generic_name, indication, route)
    ("Cardizol-X", "cardizolam", "Hypertension", "Oral"),
    ("Neurofen-Plus", "ibuprofen-codeine", "Pain Management", "Oral"),
    ("Arthrex-200", "celecoxib-200", "Osteoarthritis", "Oral"),
    ("Lipitorex", "atorvastatin", "Hyperlipidemia", "Oral"),
    ("Metforin-XR", "metformin", "Type 2 Diabetes", "Oral"),
    ("Amlodex", "amlodipine", "Hypertension", "Oral"),
    ("Omeprazol-20", "omeprazole", "GERD", "Oral"),
    ("Sertralex", "sertraline", "Depression", "Oral"),
    ("Levothyra", "levothyroxine", "Hypothyroidism", "Oral"),
    ("Gabapentex", "gabapentin", "Neuropathy", "Oral"),
    ("Lisinox", "lisinopril", "Hypertension", "Oral"),
    ("Simvalex", "simvastatin", "Hyperlipidemia", "Oral"),
    ("Warfatrex", "warfarin", "Anticoagulation", "Oral"),
    ("Prednizol", "prednisolone", "Inflammation", "Oral"),
    ("Tramadex", "tramadol", "Pain Management", "Oral"),
    ("Clopidex", "clopidogrel", "Antiplatelet", "Oral"),
    ("Azithrex", "azithromycin", "Bacterial Infection", "Oral"),
    ("Fluoxetex", "fluoxetine", "Depression", "Oral"),
    ("Ramiprilex", "ramipril", "Hypertension", "Oral"),
    ("Diclofex", "diclofenac", "Pain/Inflammation", "Oral"),
]

# Realistic MedDRA Preferred Terms (adverse reactions)
REACTION_TERMS = [
    "Nausea", "Headache", "Dizziness", "Fatigue", "Diarrhoea",
    "Vomiting", "Rash", "Insomnia", "Abdominal pain", "Dyspnoea",
    "Arthralgia", "Back pain", "Cough", "Pruritus", "Constipation",
    "Myalgia", "Oedema peripheral", "Pyrexia", "Weight increased",
    "Anxiety", "Hypertension", "Tachycardia", "Hypotension",
    "Drug interaction", "Drug ineffective", "Fall", "Asthenia",
    "Pain in extremity", "Malaise", "Chest pain",
    # Serious / Signal-relevant terms
    "Cardiac arrhythmia", "Ventricular tachycardia", "QT prolongation",
    "Atrial fibrillation", "Cardiac arrest", "Myocardial infarction",
    "Hepatotoxicity", "Liver injury", "Hepatic failure",
    "Jaundice", "Hepatitis", "Transaminases increased",
    "Rhabdomyolysis", "Myopathy", "Creatine kinase increased",
    "Renal failure acute", "Nephrotoxicity",
    "Stevens-Johnson syndrome", "Anaphylaxis", "Agranulocytosis",
    "Thrombocytopenia", "Pancreatitis", "Seizure",
]

REPORTER_TYPES = ["Physician", "Pharmacist", "Nurse", "Consumer", "Lawyer", "Other"]
REPORTER_COUNTRIES = [
    ("United States", "US", 0.45),
    ("United Kingdom", "GB", 0.08),
    ("Germany", "DE", 0.06),
    ("France", "FR", 0.05),
    ("Japan", "JP", 0.07),
    ("Canada", "CA", 0.05),
    ("Australia", "AU", 0.04),
    ("Italy", "IT", 0.03),
    ("Spain", "ES", 0.03),
    ("Brazil", "BR", 0.03),
    ("India", "IN", 0.03),
    ("South Korea", "KR", 0.02),
    ("Netherlands", "NL", 0.02),
    ("Sweden", "SE", 0.01),
    ("Mexico", "MX", 0.01),
    ("Switzerland", "CH", 0.01),
    ("Other", "OT", 0.01),
]

OUTCOMES = ["Recovered", "Recovering", "Not Recovered", "Fatal", "Unknown"]
OUTCOME_DETAILS = [
    "Hospitalization", "Life-threatening", "Disability",
    "Congenital anomaly", "Required intervention", "Other serious",
]
SERIOUSNESS_CRITERIA = [
    "Death", "Life-threatening", "Hospitalization",
    "Disability", "Congenital anomaly", "Other medically important",
]

AGE_GROUPS = ["Neonate", "Infant", "Child", "Adolescent", "Adult", "Elderly"]


def _pick_country():
    """Weighted country selection."""
    r = random.random()
    cumulative = 0
    for name, code, weight in REPORTER_COUNTRIES:
        cumulative += weight
        if r <= cumulative:
            return name, code
    return "Other", "OT"


def _pick_age_group(age: int) -> str:
    if age < 1:
        return "Neonate"
    elif age < 2:
        return "Infant"
    elif age < 12:
        return "Child"
    elif age < 18:
        return "Adolescent"
    elif age < 65:
        return "Adult"
    else:
        return "Elderly"


def _pick_concomitant_drugs(primary_drug: str, count: int = None) -> list:
    """Pick random concomitant drugs (excluding the primary drug)."""
    if count is None:
        count = random.choices([0, 1, 2, 3], weights=[0.3, 0.35, 0.25, 0.1])[0]
    available = [d[0] for d in DRUG_CATALOG if d[0] != primary_drug]
    return random.sample(available, min(count, len(available)))


def generate_baseline_report(report_date: datetime) -> dict:
    """Generate a standard (non-signal) adverse event report."""
    drug = random.choice(DRUG_CATALOG)
    age = random.randint(18, 90)
    sex = random.choice(["Male", "Female"])
    country_name, country_code = _pick_country()
    is_serious = random.random() < 0.25
    reaction = random.choice(REACTION_TERMS[:30])  # Common reactions

    outcome = random.choices(
        OUTCOMES, weights=[0.35, 0.25, 0.20, 0.05, 0.15]
    )[0]

    return {
        "report_id": f"FAERS-{uuid.uuid4().hex[:12].upper()}",
        "report_date": report_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "receive_date": (report_date + timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reporter_type": random.choice(REPORTER_TYPES),
        "reporter_country": country_name,
        "reporter_country_code": country_code,
        "report_source": random.choice(["Direct", "Literature", "Study", "Other"]),
        "serious": is_serious,
        "seriousness_criteria": random.choice(SERIOUSNESS_CRITERIA) if is_serious else None,
        "patient_age": age,
        "patient_age_group": _pick_age_group(age),
        "patient_sex": sex,
        "patient_weight_kg": round(random.gauss(75, 15), 1),
        "drug_name": drug[0],
        "drug_generic_name": drug[1],
        "drug_characterization": random.choice(["Primary suspect", "Secondary suspect", "Concomitant"]),
        "drug_indication": drug[2],
        "drug_route": drug[3],
        "drug_dose": f"{random.choice([5, 10, 20, 25, 50, 100, 200, 500])}mg daily",
        "concomitant_drugs": _pick_concomitant_drugs(drug[0]),
        "reaction_term": reaction,
        "reaction_meddra_pt": reaction,
        "reaction_outcome": outcome,
        "outcome_detail": random.choice(OUTCOME_DETAILS) if is_serious else None,
        "narrative": f"Patient ({age}y {sex}) reported {reaction.lower()} while taking {drug[0]} for {drug[2].lower()}.",
    }


# ── Signal Generators ────────────────────────────────────

def generate_signal_1_cardizol_cardiac(report_date: datetime) -> dict:
    """Signal 1: Cardizol-X → cardiac arrhythmia spike.
    
    Dramatically increased cardiac events in the last 90 days.
    """
    age = random.randint(45, 85)
    sex = random.choice(["Male", "Female"])
    country_name, country_code = _pick_country()

    cardiac_reactions = [
        "Cardiac arrhythmia", "Ventricular tachycardia",
        "QT prolongation", "Atrial fibrillation",
        "Cardiac arrest", "Tachycardia",
    ]
    reaction = random.choice(cardiac_reactions)
    outcome = random.choices(
        OUTCOMES, weights=[0.15, 0.20, 0.25, 0.20, 0.20]
    )[0]

    return {
        "report_id": f"FAERS-{uuid.uuid4().hex[:12].upper()}",
        "report_date": report_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "receive_date": (report_date + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reporter_type": random.choice(["Physician", "Pharmacist", "Nurse"]),
        "reporter_country": country_name,
        "reporter_country_code": country_code,
        "report_source": "Direct",
        "serious": True,
        "seriousness_criteria": random.choice(["Life-threatening", "Hospitalization", "Death"]),
        "patient_age": age,
        "patient_age_group": _pick_age_group(age),
        "patient_sex": sex,
        "patient_weight_kg": round(random.gauss(80, 18), 1),
        "drug_name": "Cardizol-X",
        "drug_generic_name": "cardizolam",
        "drug_characterization": "Primary suspect",
        "drug_indication": "Hypertension",
        "drug_route": "Oral",
        "drug_dose": f"{random.choice([50, 100, 200])}mg daily",
        "concomitant_drugs": _pick_concomitant_drugs("Cardizol-X"),
        "reaction_term": reaction,
        "reaction_meddra_pt": reaction,
        "reaction_outcome": outcome,
        "outcome_detail": random.choice(["Hospitalization", "Life-threatening", "Required intervention"]),
        "narrative": f"Patient ({age}y {sex}) developed {reaction.lower()} after starting Cardizol-X for hypertension. ECG confirmed {reaction.lower()}.",
    }


def generate_signal_2_neurofen_hepato(report_date: datetime) -> dict:
    """Signal 2: Neurofen-Plus → hepatotoxicity in elderly females."""
    age = random.randint(60, 88)
    sex = random.choices(["Female", "Male"], weights=[0.78, 0.22])[0]
    country_name, country_code = _pick_country()

    hepato_reactions = [
        "Hepatotoxicity", "Liver injury", "Hepatic failure",
        "Jaundice", "Hepatitis", "Transaminases increased",
    ]
    reaction = random.choice(hepato_reactions)

    return {
        "report_id": f"FAERS-{uuid.uuid4().hex[:12].upper()}",
        "report_date": report_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "receive_date": (report_date + timedelta(days=random.randint(1, 21))).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reporter_type": random.choice(["Physician", "Pharmacist"]),
        "reporter_country": country_name,
        "reporter_country_code": country_code,
        "report_source": "Direct",
        "serious": True,
        "seriousness_criteria": random.choice(["Hospitalization", "Life-threatening"]),
        "patient_age": age,
        "patient_age_group": "Elderly",
        "patient_sex": sex,
        "patient_weight_kg": round(random.gauss(68, 12), 1),
        "drug_name": "Neurofen-Plus",
        "drug_generic_name": "ibuprofen-codeine",
        "drug_characterization": "Primary suspect",
        "drug_indication": "Pain Management",
        "drug_route": "Oral",
        "drug_dose": f"{random.choice([200, 400])}mg/12.8mg twice daily",
        "concomitant_drugs": _pick_concomitant_drugs("Neurofen-Plus"),
        "reaction_term": reaction,
        "reaction_meddra_pt": reaction,
        "reaction_outcome": random.choices(OUTCOMES, weights=[0.20, 0.25, 0.30, 0.10, 0.15])[0],
        "outcome_detail": "Hospitalization",
        "narrative": f"Elderly {sex.lower()} patient ({age}y) developed {reaction.lower()} after prolonged use of Neurofen-Plus. LFTs significantly elevated.",
    }


def generate_signal_3_arthrex_rhabdo(report_date: datetime) -> dict:
    """Signal 3: Arthrex-200 → rhabdomyolysis with statin co-prescription."""
    age = random.randint(50, 80)
    sex = random.choice(["Male", "Female"])
    country_name, country_code = _pick_country()

    rhabdo_reactions = [
        "Rhabdomyolysis", "Myopathy", "Creatine kinase increased",
    ]
    reaction = random.choice(rhabdo_reactions)

    # Always co-prescribed with a statin
    statin = random.choice(["Lipitorex", "Simvalex"])
    other_concomitant = _pick_concomitant_drugs("Arthrex-200", count=random.randint(0, 2))
    concomitant = [statin] + [d for d in other_concomitant if d not in [statin]]

    return {
        "report_id": f"FAERS-{uuid.uuid4().hex[:12].upper()}",
        "report_date": report_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "receive_date": (report_date + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reporter_type": random.choice(["Physician", "Pharmacist"]),
        "reporter_country": country_name,
        "reporter_country_code": country_code,
        "report_source": "Direct",
        "serious": True,
        "seriousness_criteria": random.choice(["Hospitalization", "Life-threatening"]),
        "patient_age": age,
        "patient_age_group": _pick_age_group(age),
        "patient_sex": sex,
        "patient_weight_kg": round(random.gauss(82, 15), 1),
        "drug_name": "Arthrex-200",
        "drug_generic_name": "celecoxib-200",
        "drug_characterization": "Primary suspect",
        "drug_indication": "Osteoarthritis",
        "drug_route": "Oral",
        "drug_dose": "200mg daily",
        "concomitant_drugs": concomitant,
        "reaction_term": reaction,
        "reaction_meddra_pt": reaction,
        "reaction_outcome": random.choices(OUTCOMES, weights=[0.15, 0.30, 0.30, 0.10, 0.15])[0],
        "outcome_detail": "Hospitalization",
        "narrative": f"Patient ({age}y {sex}) on Arthrex-200 + {statin} developed {reaction.lower()}. CK levels markedly elevated. Possible drug interaction.",
    }


# ── Main Generation Logic ────────────────────────────────

def generate_all_reports(total_count: int) -> list[dict]:
    """Generate all FAERS reports with embedded signals.
    
    Distribution over 2 years:
    - Baseline: ~90% of reports (normal adverse events across all drugs)
    - Signal 1 (Cardizol-X cardiac): Low baseline + spike in last 90 days
    - Signal 2 (Neurofen-Plus hepato): Gradual increase over last 6 months
    - Signal 3 (Arthrex-200 rhabdo): Consistent but detectable with statin co-use
    """
    reports = []
    now = datetime(2026, 2, 1)
    start_date = now - timedelta(days=730)  # 2 years back

    # ── Baseline reports ──────────────────────────────
    baseline_count = int(total_count * 0.88)
    logger.info(f"Generating {baseline_count:,} baseline reports...")
    for _ in tqdm(range(baseline_count), desc="Baseline"):
        days_ago = random.randint(0, 730)
        report_date = now - timedelta(days=days_ago)
        reports.append(generate_baseline_report(report_date))

    # ── Signal 1: Cardizol-X cardiac spike ────────────
    # Low baseline (2% of Cardizol reports are cardiac) for months 1-21
    # Then 4x spike in last 90 days
    signal_1_baseline = int(total_count * 0.02)
    signal_1_spike = int(total_count * 0.04)

    logger.info(f"Generating Signal 1: {signal_1_baseline:,} baseline + {signal_1_spike:,} spike cardiac events...")
    for _ in tqdm(range(signal_1_baseline), desc="Signal 1 baseline"):
        days_ago = random.randint(90, 730)
        report_date = now - timedelta(days=days_ago)
        reports.append(generate_signal_1_cardizol_cardiac(report_date))

    for _ in tqdm(range(signal_1_spike), desc="Signal 1 spike"):
        days_ago = random.randint(0, 89)
        report_date = now - timedelta(days=days_ago)
        reports.append(generate_signal_1_cardizol_cardiac(report_date))

    # ── Signal 2: Neurofen-Plus hepato (gradual rise) ─
    signal_2_count = int(total_count * 0.03)
    logger.info(f"Generating Signal 2: {signal_2_count:,} hepatotoxicity events (gradual rise)...")
    for _ in tqdm(range(signal_2_count), desc="Signal 2"):
        # Weight towards recent dates (more reports in recent months)
        days_ago = int(abs(random.gauss(0, 90)))
        days_ago = min(days_ago, 365)
        report_date = now - timedelta(days=days_ago)
        reports.append(generate_signal_2_neurofen_hepato(report_date))

    # ── Signal 3: Arthrex-200 rhabdo (statin interaction) ─
    signal_3_count = int(total_count * 0.03)
    logger.info(f"Generating Signal 3: {signal_3_count:,} rhabdomyolysis events...")
    for _ in tqdm(range(signal_3_count), desc="Signal 3"):
        days_ago = random.randint(0, 365)
        report_date = now - timedelta(days=days_ago)
        reports.append(generate_signal_3_arthrex_rhabdo(report_date))

    random.shuffle(reports)
    logger.info(f"Total reports generated: {len(reports):,}")
    return reports


# ── Elasticsearch Ingestion ──────────────────────────────

def create_index(es: Elasticsearch, index_name: str = "faers_reports"):
    """Create the FAERS index with proper mappings."""
    mappings_path = Path(__file__).parent / "index_mappings.json"
    with open(mappings_path) as f:
        mappings = json.load(f)

    if es.indices.exists(index=index_name):
        logger.info(f"Deleting existing index: {index_name}")
        es.indices.delete(index=index_name)

    logger.info(f"Creating index: {index_name}")
    es.indices.create(
        index=index_name,
        body=mappings[index_name],
    )


def bulk_ingest(es: Elasticsearch, reports: list[dict], index_name: str = "faers_reports"):
    """Bulk index reports into Elasticsearch."""
    def _actions():
        for report in reports:
            yield {
                "_index": index_name,
                "_id": report["report_id"],
                "_source": report,
            }

    logger.info(f"Bulk indexing {len(reports):,} reports into {index_name}...")
    success, errors = helpers.bulk(
        es,
        _actions(),
        chunk_size=2000,
        request_timeout=120,
        raise_on_error=False,
    )
    logger.info(f"Indexed: {success:,} | Errors: {len(errors) if isinstance(errors, list) else errors}")

    es.indices.refresh(index=index_name)
    count = es.count(index=index_name)
    logger.info(f"Total documents in {index_name}: {count['count']:,}")


# ── CLI ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic FAERS data")
    parser.add_argument("--es-url", required=True, help="Elasticsearch URL")
    parser.add_argument("--api-key", required=True, help="Elasticsearch API key")
    parser.add_argument("--count", type=int, default=500_000, help="Total record count")
    parser.add_argument("--index", default="faers_reports", help="Index name")
    args = parser.parse_args()

    es = Elasticsearch(
        args.es_url,
        api_key=args.api_key,
        request_timeout=60,
    )

    # Verify connection
    info = es.info()
    logger.info(f"Connected to Elasticsearch: {info['version']['number']}")

    # Generate data
    reports = generate_all_reports(args.count)

    # Create index and ingest
    create_index(es, args.index)
    bulk_ingest(es, reports, args.index)

    logger.info("Data generation complete!")
    logger.info("Embedded signals:")
    logger.info("  1. Cardizol-X: Cardiac arrhythmia spike in last 90 days (4x baseline)")
    logger.info("  2. Neurofen-Plus: Hepatotoxicity in 65+ females (gradual rise)")
    logger.info("  3. Arthrex-200: Rhabdomyolysis with statin co-prescription")


if __name__ == "__main__":
    main()
