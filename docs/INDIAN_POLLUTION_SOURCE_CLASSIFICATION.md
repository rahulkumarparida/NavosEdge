# Indian Pollution Source Classification & Hypotheses

## 1. Environmental Context & Reality Mapping

Air pollution profiles in the Indian subcontinent present distinct emission signatures compared to Western urban environments:
- **Biomass & Crop Residue Burning**: Agricultural stubble burning (*parali*) across Northern India during post-monsoon and winter seasons; rural/semi-urban domestic biomass cooking using wood, cow-dung cakes, and crop waste (*chulha*).
- **Road & Mechanical Dust**: Extensive resuspension of coarse soil dust from unpaved roads, construction sites, and arid ground conditions, typically characterized by elevated $\text{PM}_{10}$ relative to $\text{PM}_{2.5}$.
- **Mixed Vehicular Emissions**: Dense mixtures of two-wheelers, auto-rickshaws, commercial diesel trucks, and buses operating in stop-and-go traffic conditions.
- **Localized Combustion**: Diesel generator sets (DG sets) operating during power disruptions, open solid-waste burning in municipal zones, and street-side food stalls.
- **Industrial & Cluster Emissions**: Small-to-medium enterprise manufacturing, brick kilns, foundries, and chemical processing zones.

---

## 2. Taxonomy Mapping & Category Aliases

To preserve compatibility with pre-trained Edge AI weights (`TinyGasNet` and `SourceClassifier`) while presenting terminology relevant to Indian clean-air action plans (e.g., NCAP), the system maintains canonical taxonomy aliases:

| Pre-Trained Model Class | Indian Context Category | Primary Atmospheric Characteristics | Key Indicator Ratios |
| :--- | :--- | :--- | :--- |
| `TRAFFIC` | **Vehicular / Transport Emissions** | Fine $\text{PM}_{2.5}$, exhaust soot, elevated MQ-2/MQ-9 signatures near transit corridors | High $\text{PM}_{2.5}/\text{PM}_{10}$ ratio ($\approx 0.6–0.8$), elevated MQ-9 |
| `HEAVY_DUST` | **Road & Soil Dust Resuspension** | Coarse particulate dominance, arid conditions, construction track dust | High $\text{PM}_{10}$, low $\text{PM}_{2.5}/\text{PM}_{10}$ ratio ($\le 0.4$), normal MQ-9 |
| `CONSTRUCTION` | **Construction & Demolition Activity** | Localized high coarse dust combined with mechanical exhaust | Elevated $\text{PM}_{10}$ with moderate localized VOC/exhaust markers |
| `BIOMASS_OR_WASTE_BURNING` | **Crop Stubble / Biomass / Waste Burning** | High fine particulate concentration accompanied by smoke VOCs and CO | Sharp spikes in $\text{PM}_{2.5}$ and $\text{PM}_{1.0}$, elevated MQ-2 and MQ-135 |
| `COMBUSTION` | **General Combustion & Generator Exhaust** | Diesel generator emissions, open burning, domestic fuel combustion | Elevated CO/smoke markers (MQ-9 and MQ-2) |
| `INDUSTRIAL` | **Industrial & Kiln Cluster Emissions** | Chemical plumes, sulfurous and solvent VOC signatures | Distinct elevated MQ-135 voltage relative to ambient baseline |
| `INDOOR_ACTIVITY` | **Indoor / Confined Space Activity** | Domestic cooking smoke, incense burning, poor room ventilation | High temperature/humidity correlation, rapid decay upon ventilation |
| `MIXED` | **Mixed / Complex Multi-Source Plume** | Background urban smog with multiple contributing non-point sources | Balanced feature vectors without single dominant classifier pole |
| `UNKNOWN` | **Unclassified / Baseline Ambience** | Readings within normal ambient background or low model confidence | Low sensor deviations across all channels |

---

## 3. Scientific Caveats & Cautious Hypothesis Phrasing

### 3.1 Non-Chromatographic Nature of Metal-Oxide Sensors
Low-cost metal-oxide semiconductor (MOS) sensors (MQ series):
1. **Lack Chemical Specificity**: MQ sensors respond to broad classes of reducing and oxidizing gases through surface chemisorption on heated $\text{SnO}_2$. They cannot discriminate between individual chemical species (e.g., CO vs. $\text{H}_2$ vs. butane).
2. **Environmental Cross-Sensitivity**: Ambient temperature and relative humidity directly alter the baseline resistance ($R_0$) and sensor response ($R_s/R_0$).
3. **No ppm Equivalency**: Analog output voltages cannot be equated to parts-per-million (ppm) regulatory measurements without chamber gas titration.

### 3.2 Cautious Hypothesis Phrasing
Accordingly, the system never claims definitive legal proof of a pollution source. Instead, it reports hypotheses using cautious, probabilistically conditioned language:

- **Confirmed Classification ($\text{Confidence} \ge 60\%$)**:
  - *Traffic*: *"Sensor patterns suggest possible vehicular or traffic emissions nearby."*
  - *Biomass Burning*: *"Elevated fine particles and smoke markers indicate potential biomass or crop residue smoke."*
  - *Dust*: *"High coarse particle ratios suggest road or soil dust resuspension."*
- **Unconfirmed Classification ($\text{Confidence} < 60\%$)**:
  - *"Readings suggest multiple or indeterminate emission sources. Source cannot be conclusively identified."*
  - Actions default to general precautionary public-health advisories.

---

## 4. Model Confidence vs. Regulatory Certainty

| Dimension | Edge AI Classifier (NavosEdge) | Regulatory Continuous Ambient Station (CAAQMS) |
| :--- | :--- | :--- |
| **Technology** | Laser light scattering + MOS sensor array | Beta-Attenuation Monitor (BAM) + Chemiluminescence analyzers |
| **Output** | Indicative classification hypothesis + confidence score | Certified concentrations of regulatory pollutants ($\mu\text{g/m}^3$) |
| **Use Case** | Localized real-time situational awareness & immediate user action | Regulatory compliance, legal enforcement, city-wide official reporting |
| **Calibration** | Factory curve + temperature/humidity normalization | Periodic multi-point span/zero gas calibration |
