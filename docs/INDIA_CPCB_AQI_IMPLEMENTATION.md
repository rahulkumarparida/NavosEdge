# Indian CPCB National Air Quality Index (AQI) Implementation

## 1. Regulatory Framework & Standards Basis

NavosEdge implements the official **Indian National Air Quality Index (AQI)** methodology specified by the **Central Pollution Control Board (CPCB)** and the **Ministry of Environment, Forest and Climate Change (MoEFCC)**, Government of India.

Official References:
- *CPCB National Air Quality Index Final Report (2014)*: [CPCB Report](https://app.cpcbccr.com/ccr_docs/FINAL-REPORT_AQI_.pdf)
- *CPCB Air Quality Breakpoints & Technical Guidance*: [CPCB AQI Portal](https://airquality.cpcb.gov.in/AQI_India/)
- *National Centre for Disease Control (NCDC) Public Health Guidance*: [NCDC MoHFW](https://ncdc.mohfw.gov.in/wp-content/uploads/2024/04/3065716611669017053.pdf)

---

## 2. Canonical Indian AQI Categories & Color Codes

In accordance with official Indian regulatory standards, the qualitative categories and standard color bands are:

| AQI Range | Canonical Category | Public Health Impact Description | Official CPCB Color | RGB565 (Display) |
| :---: | :---: | :--- | :---: | :---: |
| **0–50** | **Good** | Minimal health impact; clean and safe air. | Dark Green | `GUI_GOOD_GREEN` (`0x07E0`) |
| **51–100** | **Satisfactory** | Minor breathing discomfort to sensitive people. | Light Green | `GUI_GOOD_GREEN` (`0x07E0`) |
| **101–200** | **Moderate** | Breathing discomfort to people with asthma and heart disease. | Yellow | `GUI_WARN_YELLOW` (`0xFFE0`) |
| **201–300** | **Poor** | Breathing discomfort to most people on prolonged exposure. | Orange | `GUI_WARN_ORANGE` (`0xFD20`) |
| **301–400** | **Very Poor** | Respiratory illness on prolonged exposure; severe effects on vulnerable groups. | Red | `GUI_BAD_RED` (`0xF800`) |
| **401–500** | **Severe** | Affects healthy people; seriously impacts those with existing diseases. | Maroon / Purple | `GUI_PURPLE` (`0x780F`) |

---

## 3. Sub-Index Interpolation Methodology

For any eligible regulatory pollutant with measured concentration $C$, the sub-index $I$ is calculated via linear interpolation across the breakpoint range $[BP_{\text{low}}, BP_{\text{high}}]$ corresponding to index range $[I_{\text{low}}, I_{\text{high}}]$:

$$I = \left[ \frac{I_{\text{high}} - I_{\text{low}}}{BP_{\text{high}} - BP_{\text{low}}} \right] \times (C - BP_{\text{low}}) + I_{\text{low}}$$

Where:
- $C$ is the measured ambient pollutant concentration (rounded to one decimal place).
- $BP_{\text{low}}$ and $BP_{\text{high}}$ are the lower and upper concentration breakpoints for the active category band.
- $I_{\text{low}}$ and $I_{\text{high}}$ are the lower and upper index breakpoints ($0–50, 51–100, 101–200, 201–300, 301–400, 401–500$).

If a concentration exceeds the maximum breakpoint ($500$), it is capped at $500.0$ and categorized as **Severe**.

---

## 4. Official CPCB Concentration Breakpoint Table

| Pollutant | Averaging Period | Units | Good (0–50) | Satisfactory (51–100) | Moderate (101–200) | Poor (201–300) | Very Poor (301–400) | Severe (401–500) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$\text{PM}_{2.5}$** | 24-Hour | $\mu\text{g/m}^3$ | 0–30 | 31–60 | 61–90 | 91–120 | 121–250 | 250+ |
| **$\text{PM}_{10}$** | 24-Hour | $\mu\text{g/m}^3$ | 0–50 | 51–100 | 101–250 | 251–350 | 351–430 | 430+ |
| **$\text{NO}_2$** | 24-Hour | $\mu\text{g/m}^3$ | 0–40 | 41–80 | 81–180 | 181–280 | 281–400 | 400+ |
| **$\text{SO}_2$** | 24-Hour | $\mu\text{g/m}^3$ | 0–40 | 41–80 | 81–380 | 381–800 | 801–1600 | 1600+ |
| **$\text{CO}$** | 8-Hour | $\text{mg/m}^3$ | 0.0–1.0 | 1.1–2.0 | 2.1–10.0 | 10.1–17.0 | 17.1–34.0 | 34.0+ |
| **$\text{O}_3$** | 8-Hour | $\mu\text{g/m}^3$ | 0–50 | 51–100 | 101–168 | 169–208 | 209–748 | 748+ |
| **$\text{NH}_3$** | 24-Hour | $\mu\text{g/m}^3$ | 0–200 | 201–400 | 401–800 | 801–1200 | 1201–1800 | 1800+ |
| **$\text{Pb}$** | 24-Hour | $\mu\text{g/m}^3$ | 0.0–0.5 | 0.6–1.0 | 1.1–2.0 | 2.1–3.0 | 3.1–3.5 | 3.5+ |

---

## 5. Regulatory Compliance & Data Sufficiency Rules

### 5.1 The 3-Pollutant Regulatory Rule
The CPCB standard mandates:
> **An official National AQI can ONLY be computed if data is available for at least THREE criteria pollutants, of which at least ONE must be a particulate parameter ($\text{PM}_{2.5}$ or $\text{PM}_{10}$).**

### 5.2 Regulatory Exclusion of PM1.0
$\text{PM}_{1.0}$ is **NOT** recognized as a criteria pollutant in the Indian CPCB standard. While NavosEdge collects $\text{PM}_{1.0}$ from the MPM10-CS sensor for Edge AI feature extraction and research logging, $\text{PM}_{1.0}$ is strictly **excluded** from the CPCB sub-index and overall AQI computation.

### 5.3 Uncalibrated Gas Sensors Limitation
The onboard MQ-2, MQ-9, and MQ-135 sensors output uncalibrated analog voltages. They **cannot** be treated as calibrated reference measurements of regulatory gases ($\text{NO}_2, \text{SO}_2, \text{CO}, \text{O}_3, \text{NH}_3$). 
- NavosEdge **NEVER** substitutes uncalibrated MQ readings for regulatory gas concentrations.
- Raw MQ voltages are logged and fed exclusively to the source classifier.

### 5.4 PM-Based Estimate Reporting Contract
Because an edge node equipped solely with MPM10-CS and MQ modules provides only two eligible pollutants ($\text{PM}_{2.5}$ and $\text{PM}_{10}$), NavosEdge explicitly and transparently reports the result as a **PM-Based Indicative AQI**:

```json
{
  "status": "available",
  "aqi": 134.5,
  "category": "Moderate",
  "dominant_pollutant": "PM2_5",
  "calculation_basis": "PM_BASED_ESTIMATE",
  "cpcb_compliant": false,
  "data_sufficiency": "INSUFFICIENT_POLLUTANTS",
  "official_cpcb_aqi": null,
  "pm_based_aqi": 134.5,
  "sub_indices": {
    "PM2_5": 134.5,
    "PM10": 98.2
  }
}
```

- `cpcb_compliant`: `false` (explicitly prevents misrepresentation).
- `calculation_basis`: `"PM_BASED_ESTIMATE"`.
- `official_cpcb_aqi`: `null`.
- `pm_based_aqi`: `134.5`.
- `status`: `"available"` (preserves backward compatibility with dashboard callers, display RPC, and SSE streams).
