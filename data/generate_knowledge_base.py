"""Pharma Knowledge Base Generator for RAG with Semantic Search.

Generates and indexes realistic pharmaceutical knowledge documents
into Elasticsearch with semantic embeddings (ELSER v2) so agents
can perform true RAG-based semantic lookups for:
  - Drug label information (indications, warnings, contraindications)
  - FDA safety communications & guidelines
  - Pharmacovigilance methodology (PRR, ROR, EBGM, etc.)
  - ICH guidelines & regulatory standards
  - Signal detection best practices

Uses Elasticsearch's semantic_text field type which auto-generates
embeddings at index time using ELSER v2.
"""

import json
import argparse
import logging
from datetime import datetime

from elasticsearch import Elasticsearch

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


# ── Knowledge Documents ──────────────────────────────────

KNOWLEDGE_DOCS = [
    # ── Drug Labels ──────────────────────────────────────
    {
        "doc_id": "label-cardizol-x",
        "title": "Cardizol-X (Cardizolam) — Prescribing Information",
        "category": "drug_label",
        "drug_name": "Cardizol-X",
        "content": """CARDIZOL-X (cardizolam) Tablets — Full Prescribing Information

INDICATIONS AND USAGE:
Cardizol-X is a calcium channel blocker indicated for the treatment of hypertension in adults. It may be used alone or in combination with other antihypertensive agents.

DOSAGE AND ADMINISTRATION:
- Starting dose: 50mg once daily
- May increase to 100mg once daily after 2 weeks
- Maximum dose: 200mg once daily
- Take with or without food. Swallow whole, do not crush.

CONTRAINDICATIONS:
- Known hypersensitivity to cardizolam or any excipients
- Severe aortic stenosis
- Decompensated heart failure (NYHA III-IV)
- Sick sinus syndrome or 2nd/3rd degree AV block (without pacemaker)

WARNINGS AND PRECAUTIONS:
- Cardiac Conduction: May cause bradycardia or AV block. Monitor ECG in patients with pre-existing conduction abnormalities.
- QT Prolongation: Dose-dependent QT interval prolongation has been observed in clinical trials. Avoid use with other QT-prolonging agents. Perform baseline and periodic ECG monitoring.
- Hypotension: Symptomatic hypotension may occur, especially in volume-depleted patients. Correct volume depletion before initiating therapy.
- Hepatic Impairment: Reduce dose by 50% in patients with moderate hepatic impairment (Child-Pugh B). Not recommended in severe hepatic impairment.
- Heart Failure: Use with caution in patients with compensated heart failure. May worsen cardiac function.

ADVERSE REACTIONS:
Most common (>=5%): Headache, dizziness, peripheral edema, fatigue, nausea, bradycardia.
Serious: Cardiac arrhythmia (1.2%), QT prolongation (0.8%), severe hypotension (0.5%), hepatic enzyme elevation (0.3%).

Post-marketing: Cases of ventricular tachycardia, torsades de pointes, and cardiac arrest have been reported, predominantly in patients taking doses >=150mg or with concomitant QT-prolonging medications.

DRUG INTERACTIONS:
- Strong CYP3A4 inhibitors: Increase cardizolam exposure by 3-fold. Reduce dose by 50%.
- QT-prolonging agents: Additive effect on QT interval. Avoid concomitant use.
- Beta-blockers: Additive negative chronotropic and dromotropic effects. Monitor heart rate.
- Digoxin: Cardizolam increases digoxin levels by 20%. Monitor digoxin levels.

CLINICAL PHARMACOLOGY:
Mechanism of Action: Cardizolam blocks L-type calcium channels in cardiac and vascular smooth muscle, reducing peripheral vascular resistance and myocardial oxygen demand. It also has mild potassium channel blocking activity, which may contribute to QT prolongation at higher doses.

Half-life: 8-12 hours. Metabolism: Hepatic via CYP3A4. Excretion: 60% renal, 35% fecal.""",
    },
    {
        "doc_id": "label-neurofen-plus",
        "title": "Neurofen-Plus (Ibuprofen/Codeine) — Prescribing Information",
        "category": "drug_label",
        "drug_name": "Neurofen-Plus",
        "content": """NEUROFEN-PLUS (ibuprofen 200mg / codeine phosphate 12.8mg) Tablets

INDICATIONS AND USAGE:
For the short-term symptomatic treatment of acute moderate pain in adults when other analgesics are inadequate. Not indicated for long-term use.

DOSAGE AND ADMINISTRATION:
- Adults: 1-2 tablets every 4-6 hours as needed
- Maximum: 6 tablets in 24 hours
- Duration: Do not use for more than 3 days without medical advice
- Take with food or milk to reduce GI irritation

CONTRAINDICATIONS:
- Active GI bleeding or peptic ulcer
- Severe hepatic impairment or active liver disease
- Severe renal impairment (CrCl <30 mL/min)
- Third trimester of pregnancy
- Known codeine ultra-rapid metabolizer status (CYP2D6)
- Children under 12 years

WARNINGS AND PRECAUTIONS:
- Hepatotoxicity: Ibuprofen and codeine are both hepatically metabolized. Risk of liver injury increases with prolonged use, higher doses, pre-existing liver disease, and advanced age (>=65). Monitor LFTs in patients using >7 days.
- GI Risk: NSAIDs increase risk of serious GI adverse events including bleeding, ulceration, and perforation. Elderly patients are at greater risk.
- Opioid Risks: Codeine is an opioid. Risks include respiratory depression, dependence, and abuse.
- Elderly Patients: Increased risk of hepatotoxicity, GI bleeding, and renal impairment. Use lowest effective dose for shortest duration.
- Renal Impairment: May cause fluid retention and edema. Use with caution in renal insufficiency.

ADVERSE REACTIONS:
Common (>=5%): Nausea, constipation, drowsiness, dizziness, dyspepsia.
Hepatic: Elevated transaminases (ALT/AST >3x ULN) reported in 1.8% of patients in clinical trials, primarily in elderly females using >14 days. Cases of cholestatic hepatitis and hepatic failure reported post-marketing.

SPECIAL POPULATIONS:
- Elderly (>=65 years): Higher risk of hepatotoxicity. Female patients over 65 have shown a 3-fold increase in hepatic adverse events compared to younger patients. Monitor LFTs at baseline and periodically.
- Hepatic impairment: Contraindicated in severe impairment. Use with extreme caution in mild-moderate impairment.""",
    },
    {
        "doc_id": "label-arthrex-200",
        "title": "Arthrex-200 (Celecoxib-200) — Prescribing Information",
        "category": "drug_label",
        "drug_name": "Arthrex-200",
        "content": """ARTHREX-200 (celecoxib-200) Capsules

INDICATIONS AND USAGE:
Arthrex-200 is a COX-2 selective NSAID for the management of osteoarthritis, rheumatoid arthritis, and acute pain in adults.

DOSAGE AND ADMINISTRATION:
- Osteoarthritis: 200mg once daily or 100mg twice daily
- Acute pain: 400mg initially, then 200mg on the same day, followed by 200mg twice daily as needed
- Use the lowest effective dose for the shortest duration

CONTRAINDICATIONS:
- Known sulfonamide allergy
- CABG surgery setting
- Active GI bleeding
- Severe hepatic impairment

WARNINGS AND PRECAUTIONS:
- Cardiovascular Risk: NSAIDs may increase the risk of serious cardiovascular thrombotic events, including MI and stroke. Risk increases with duration of use.
- Rhabdomyolysis with Statin Co-prescription: POST-MARKETING SAFETY SIGNAL — Reports of rhabdomyolysis and myopathy have been received in patients taking Arthrex-200 concomitantly with HMG-CoA reductase inhibitors (statins), particularly atorvastatin and simvastatin. Arthrex-200 may inhibit CYP2C9-mediated metabolism of certain statins, leading to elevated statin plasma levels and increased risk of muscle toxicity.
  - Monitor CK levels in patients on concurrent statin therapy
  - Consider dose reduction of the statin
  - Advise patients to report unexplained muscle pain, tenderness, or weakness
- GI Risk: Serious GI events including bleeding, ulceration, and perforation.
- Renal: May cause renal papillary necrosis and other renal injury with long-term use.
- Hepatotoxicity: Elevations of ALT/AST reported. Discontinue if abnormal LFTs persist.

ADVERSE REACTIONS:
Common (>=2%): Abdominal pain, diarrhea, dyspepsia, headache, peripheral edema.
Musculoskeletal: Myalgia (1.5%), rhabdomyolysis (0.3% overall; 2.1% in patients co-prescribed statins).

DRUG INTERACTIONS:
- Statins (atorvastatin, simvastatin): Arthrex-200 inhibits CYP2C9, potentially increasing statin levels. Rhabdomyolysis risk. Reduce statin dose or use alternative statin (rosuvastatin/pravastatin).
- Warfarin: Increased bleeding risk. Monitor INR closely.
- ACE inhibitors/ARBs: Reduced antihypertensive effect. Monitor blood pressure.
- Lithium: Increased lithium levels. Monitor lithium concentrations.""",
    },

    # ── Pharmacovigilance Methodology ────────────────────
    {
        "doc_id": "pv-signal-detection-methods",
        "title": "Statistical Methods for Drug Safety Signal Detection",
        "category": "methodology",
        "drug_name": "",
        "content": """PHARMACOVIGILANCE SIGNAL DETECTION METHODOLOGY

1. PROPORTIONAL REPORTING RATIO (PRR):
The PRR compares the proportion of a specific adverse reaction reported for a drug with the proportion of the same reaction reported for all other drugs in the database.

Formula: PRR = (a / (a+b)) / (c / (c+d))
Where:
  a = reports of the specific reaction with the drug
  b = all other reaction reports with the drug
  c = reports of the specific reaction with all other drugs
  d = all other reaction reports with all other drugs

Signal threshold (Evans' criteria):
  - PRR >= 2.0
  - Chi-squared >= 4.0
  - N >= 3 (at least 3 cases)

Interpretation:
  - PRR 1.0 = no disproportionality
  - PRR 2.0-5.0 = weak signal, warrants monitoring
  - PRR 5.0-10.0 = moderate signal, requires investigation
  - PRR > 10.0 = strong signal, urgent action needed
  - PRR approaching infinity = reaction exclusively reported with this drug

2. REPORTING ODDS RATIO (ROR):
Similar to PRR but uses odds instead of proportions.
Formula: ROR = (a * d) / (b * c)
Signal threshold: Lower bound of 95% CI > 1.0

3. BAYESIAN CONFIDENCE PROPAGATION NEURAL NETWORK (BCPNN):
Uses Information Component (IC) derived from Bayesian analysis.
Signal threshold: IC025 (lower 95% credibility bound) > 0

4. EMPIRICAL BAYES GEOMETRIC MEAN (EBGM):
Used by FDA's Multi-Item Gamma Poisson Shrinker (MGPS).
Signal threshold: EB05 (lower 90% limit) >= 2.0

5. TEMPORAL SPIKE ANALYSIS:
Compares recent reporting rate vs historical baseline.
Spike ratio = (recent daily rate) / (baseline daily rate)
  - Spike > 2.0 = significant increase
  - Spike > 3.0 = concerning acceleration
  - Spike > 5.0 = critical, requires immediate review

6. SIGNAL PRIORITIZATION:
Signals are prioritized based on:
  - Statistical strength (PRR, ROR values)
  - Clinical severity (fatality rate, hospitalization rate)
  - Temporal pattern (accelerating vs stable)
  - Number of cases
  - Patient demographics (vulnerable populations)
  - Biological plausibility""",
    },
    {
        "doc_id": "pv-ich-e2e-guidelines",
        "title": "ICH E2E Pharmacovigilance Planning Guidelines",
        "category": "regulatory",
        "drug_name": "",
        "content": """ICH E2E: PHARMACOVIGILANCE PLANNING — KEY PRINCIPLES

1. PURPOSE:
ICH E2E provides guidance on planning pharmacovigilance activities throughout the lifecycle of a medicinal product, from pre-authorization through the post-authorization period.

2. SAFETY SPECIFICATION:
The safety specification should summarize:
  - Non-clinical safety findings relevant to human use
  - Clinical trial safety profile (identified risks, potential risks)
  - Populations not studied in clinical trials
  - Drug-drug interactions
  - Epidemiology of the indication

3. PHARMACOVIGILANCE PLAN:
Based on the safety specification, the plan should include:
  - Routine pharmacovigilance: Adverse event reporting, signal detection, PSURs
  - Additional pharmacovigilance actions: Targeted questionnaires, registries, post-authorization safety studies (PASS)

4. SIGNAL MANAGEMENT PROCESS:
  a. Signal Detection: Systematic review of ICSRs, literature, clinical trials
  b. Signal Validation: Confirm the signal is new and credible
  c. Signal Analysis: Evaluate strength, consistency, biological plausibility
  d. Signal Prioritization: Rank by public health impact
  e. Signal Assessment: Comprehensive benefit-risk evaluation
  f. Recommendation: Regulatory action (label update, REMS, withdrawal)

5. PERIODIC SAFETY UPDATE REPORTS (PSURs/PBRERs):
  - Summarize global safety data at defined intervals
  - Evaluate benefit-risk balance
  - Identify new safety signals or changes in risk profile
  - Propose risk minimization measures

6. RISK MANAGEMENT:
  - Risk Evaluation and Mitigation Strategies (REMS)
  - Dear Healthcare Professional letters
  - Label updates and black box warnings
  - Restricted distribution programs""",
    },
    {
        "doc_id": "pv-faers-database-guide",
        "title": "FDA FAERS Database — Structure and Usage Guide",
        "category": "methodology",
        "drug_name": "",
        "content": """FDA ADVERSE EVENT REPORTING SYSTEM (FAERS) — DATABASE GUIDE

1. OVERVIEW:
FAERS is the FDA's database for storing adverse event reports submitted through MedWatch from healthcare professionals, consumers, and manufacturers. It is a cornerstone of post-marketing drug safety surveillance and contains over 20 million reports.

2. DATA STRUCTURE:
Each FAERS report contains:
  - Demographics: Patient age, sex, weight, country
  - Drug information: Drug name (brand/generic), dose, route, indication, characterization (primary suspect, secondary suspect, concomitant, interacting)
  - Reactions: MedDRA Preferred Terms (PTs) for adverse events
  - Outcomes: Death, hospitalization, life-threatening, disability, congenital anomaly
  - Reporter: Type (physician, pharmacist, consumer), country of origin

3. LIMITATIONS:
  - Voluntary reporting: Underreporting is common (estimated 1-10% of actual AEs)
  - No denominator data: Cannot calculate incidence rates directly
  - Reporting bias: Serious events and new drugs are over-reported
  - Duplicate reports: Same event may be reported multiple times
  - Missing data: Many fields are incomplete
  - Causality: Reports do not establish causation, only association

4. SIGNAL DETECTION IN FAERS:
The FDA uses the Multi-Item Gamma Poisson Shrinker (MGPS) algorithm for routine signal detection:
  - Calculates EBGM (Empirical Bayes Geometric Mean) for drug-event pairs
  - EB05 >= 2.0 is the signal threshold
  - Reviews are typically quarterly

5. BEST PRACTICES:
  - Always use disproportionality analysis (PRR, ROR, EBGM) rather than raw counts
  - Account for confounders (age, sex, indication)
  - Validate signals using multiple methods
  - Consider biological plausibility and clinical context
  - Cross-reference with published literature and clinical trial data""",
    },
    {
        "doc_id": "pv-regulatory-actions",
        "title": "Regulatory Actions for Drug Safety Signals",
        "category": "regulatory",
        "drug_name": "",
        "content": """REGULATORY ACTIONS FOR DRUG SAFETY SIGNALS

1. LABELING CHANGES:
  - Addition of new warnings, precautions, or adverse reactions
  - Boxed Warning (Black Box): Most serious warning for life-threatening risks
  - Contraindications: Situations where drug should not be used
  - Dosage modifications: Dose reductions for specific populations

2. SAFETY COMMUNICATIONS:
  - Drug Safety Communications (DSCs): Public notifications of new safety information
  - Dear Healthcare Professional (DHCP) letters: Targeted communications to prescribers
  - MedWatch Safety Alerts: Urgent safety information

3. RISK EVALUATION AND MITIGATION STRATEGIES (REMS):
  - Medication Guide: Patient-focused information
  - Communication Plan: Education for healthcare providers
  - Elements to Assure Safe Use (ETASU): Restricted distribution, prescriber certification, patient registries, mandatory lab monitoring

4. POST-MARKETING REQUIREMENTS:
  - Post-Authorization Safety Studies (PASS)
  - Post-Authorization Efficacy Studies (PAES)
  - Additional clinical trials for specific populations
  - Registry studies

5. MARKET ACTIONS:
  - Voluntary recall by manufacturer
  - Product withdrawal from market
  - FDA-mandated recall (rare)
  - Import alerts

6. SIGNAL CLASSIFICATION THRESHOLDS:
  - LOW: PRR 2-5, <10 cases, non-serious outcomes -> Monitor, continue routine surveillance
  - MEDIUM: PRR 5-10, 10-50 cases, some serious -> Initiate safety review, potential label update
  - HIGH: PRR >10, >50 cases, serious outcomes -> Urgent safety review, DHCP letter, label update
  - CRITICAL: Deaths involved, PRR very high, accelerating trend -> Immediate action, possible market withdrawal""",
    },
    {
        "doc_id": "pv-case-assessment",
        "title": "Individual Case Safety Report (ICSR) Assessment Guide",
        "category": "methodology",
        "drug_name": "",
        "content": """INDIVIDUAL CASE SAFETY REPORT (ICSR) ASSESSMENT GUIDE

1. CAUSALITY ASSESSMENT:
WHO-UMC Causality Categories:
  - Certain: Plausible time relationship, cannot be explained by disease/other drugs, rechallenge positive
  - Probable/Likely: Reasonable time relationship, unlikely due to disease/other drugs, clinically reasonable response to withdrawal
  - Possible: Reasonable time relationship, could be explained by disease/other drugs
  - Unlikely: Improbable time relationship, other explanations more likely
  - Conditional/Unclassified: Insufficient data
  - Unassessable: Insufficient information to assess

2. SERIOUSNESS CRITERIA:
An AE is serious if it results in:
  - Death
  - Life-threatening condition
  - Hospitalization (initial or prolonged)
  - Persistent or significant disability/incapacity
  - Congenital anomaly or birth defect
  - Other medically important condition

3. EXPECTEDNESS:
  - Expected (labeled): AE is listed in the current product labeling
  - Unexpected (unlabeled): AE is NOT in the current labeling — triggers expedited reporting

4. REPORTING TIMELINES:
  - Fatal/life-threatening unexpected: 7 calendar days (initial), 15 days (follow-up)
  - All other serious unexpected: 15 calendar days
  - Non-serious: Included in periodic reports (PSURs)

5. QUALITY OF REPORT:
Minimum criteria for a valid ICSR:
  - Identifiable patient
  - Identifiable reporter
  - Suspect drug
  - Adverse event""",
    },
]


# ── Elasticsearch Index Setup with Semantic Search ───────

def setup_inference_endpoint(es: Elasticsearch):
    """Set up ELSER v2 inference endpoint for semantic embeddings."""
    endpoint_id = "elser-v2-pharma"
    
    try:
        # Check if endpoint already exists
        existing = es.inference.get(inference_id=endpoint_id)
        logger.info(f"Inference endpoint '{endpoint_id}' already exists.")
        return endpoint_id
    except Exception:
        pass
    
    try:
        logger.info(f"Creating ELSER v2 inference endpoint: {endpoint_id}")
        es.inference.put(
            inference_id=endpoint_id,
            task_type="sparse_embedding",
            body={
                "service": "elser",
                "service_settings": {
                    "num_allocations": 1,
                    "num_threads": 1,
                }
            },
        )
        logger.info(f"Inference endpoint '{endpoint_id}' created successfully!")
        return endpoint_id
    except Exception as e:
        logger.warning(f"Could not create ELSER endpoint: {e}")
        logger.info("Falling back to standard text search (no embeddings)")
        return None


def create_knowledge_index(es: Elasticsearch, index_name: str, inference_endpoint: str = None):
    """Create index with semantic_text field for automatic embedding generation."""
    
    if inference_endpoint:
        # Use semantic_text for auto-embedding via ELSER
        mapping = {
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "fields": {"keyword": {"type": "keyword"}}
                    },
                    "category": {"type": "keyword"},
                    "drug_name": {"type": "keyword"},
                    "content": {
                        "type": "text",
                        "copy_to": "content_semantic"
                    },
                    "content_semantic": {
                        "type": "semantic_text",
                        "inference_id": inference_endpoint,
                    },
                    "indexed_at": {"type": "date"},
                }
            }
        }
    else:
        # Fallback: standard full-text search with custom analyzer
        mapping = {
            "settings": {
                "analysis": {
                    "analyzer": {
                        "pharma_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "stop", "snowball"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "doc_id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "analyzer": "pharma_analyzer",
                        "fields": {"keyword": {"type": "keyword"}}
                    },
                    "category": {"type": "keyword"},
                    "drug_name": {"type": "keyword"},
                    "content": {"type": "text", "analyzer": "pharma_analyzer"},
                    "indexed_at": {"type": "date"},
                }
            }
        }

    if es.indices.exists(index=index_name):
        logger.info(f"Deleting existing index: {index_name}")
        es.indices.delete(index=index_name)

    logger.info(f"Creating knowledge index: {index_name}")
    es.indices.create(index=index_name, body=mapping)
    logger.info(f"Index '{index_name}' created with {'semantic_text (ELSER v2)' if inference_endpoint else 'BM25 full-text search'}")


def ingest_knowledge(es: Elasticsearch, index_name: str):
    """Index all knowledge documents one by one (semantic_text needs time to embed)."""
    total = len(KNOWLEDGE_DOCS)
    
    for i, doc in enumerate(KNOWLEDGE_DOCS, 1):
        logger.info(f"  Indexing [{i}/{total}]: {doc['title'][:60]}...")
        es.index(
            index=index_name,
            id=doc["doc_id"],
            document={
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "category": doc["category"],
                "drug_name": doc["drug_name"],
                "content": doc["content"].strip(),
                "indexed_at": datetime.utcnow().isoformat(),
            },
            refresh="wait_for",  # Wait for indexing to complete
        )

    es.indices.refresh(index=index_name)
    count = es.count(index=index_name)
    logger.info(f"Total documents in {index_name}: {count['count']}")


def main():
    parser = argparse.ArgumentParser(description="Generate pharma knowledge base with semantic search")
    parser.add_argument("--es-url", required=True, help="Elasticsearch URL")
    parser.add_argument("--api-key", required=True, help="Elasticsearch API key")
    parser.add_argument("--index", default="pharma_knowledge", help="Index name")
    parser.add_argument("--skip-elser", action="store_true", help="Skip ELSER setup, use BM25 only")
    args = parser.parse_args()

    es = Elasticsearch(args.es_url, api_key=args.api_key, request_timeout=120)
    info = es.info()
    logger.info(f"Connected to Elasticsearch: {info['version']['number']}")

    # Step 1: Set up inference endpoint for embeddings
    inference_endpoint = None
    if not args.skip_elser:
        inference_endpoint = setup_inference_endpoint(es)
    
    # Step 2: Create index with appropriate mappings
    create_knowledge_index(es, args.index, inference_endpoint)
    
    # Step 3: Index documents
    logger.info(f"Indexing {len(KNOWLEDGE_DOCS)} knowledge documents...")
    ingest_knowledge(es, args.index)

    logger.info("\n" + "=" * 60)
    logger.info("Knowledge base generation complete!")
    logger.info(f"  Total documents: {len(KNOWLEDGE_DOCS)}")
    logger.info(f"  Index: {args.index}")
    logger.info(f"  Embedding: {'ELSER v2 (semantic)' if inference_endpoint else 'BM25 (full-text)'}")
    logger.info(f"  Categories: drug_label, methodology, regulatory")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
