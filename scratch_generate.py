def get_variants(base, action, n=6):
    synonyms = [
        "Data indicates", "We observe", "It appears",
        "Sensors show", "Current readings suggest", "Our analysis indicates"
    ]
    words = [
        "Please", "Consider to", "We advise you to",
        "It is recommended to", "Make sure to", "Be sure to"
    ]
    res = []
    for i in range(n):
        s = synonyms[i % len(synonyms)]
        w = words[i % len(words)]
        res.append(f"{s} {base}. {w} {action}.")
    return res

out = '"""Auto-generated advisory variants."""\n\n'

out += 'AQI_VARIANTS = {\n'
for sev, base_str in [
    ("NORMAL", "air quality is in the normal range"),
    ("MODERATE", "air pollution is moderate"),
    ("HIGH", "air pollution is elevated"),
    ("SEVERE", "air pollution is severe"),
    ("CRITICAL", "air pollution has reached critical levels")
]:
    out += f'    "{sev}": {{\n'
    for sub, mod in [("LOW", "just slightly"), ("MODERATE", "noticeably"), ("HIGH", "highly")]:
        b = base_str.replace("is", f"is {mod}") if "is " in base_str else base_str.replace("has", f"has {mod}")
        act = "enjoy outdoor activities" if sev == "NORMAL" else "take general precautions"
        if sev == "MODERATE": act = "prefer well-ventilated areas"
        if sev == "HIGH": act = "reduce prolonged outdoor exertion"
        if sev == "SEVERE": act = "limit outdoor activity"
        if sev == "CRITICAL": act = "avoid outdoor exposure"
        variants = get_variants(b, act)
        out += f'        "{sub}": {variants},\n'
    out += '    },\n'
out += '}\n\n'

out += 'SOURCE_VARIANTS = {\n'
for src, base_str, act in [
    ("TRAFFIC", "traffic emissions", "reduce exposure near busy roads"),
    ("HEAVY_DUST", "heavy dust levels", "avoid visibly dusty areas"),
    ("CONSTRUCTION", "construction dust", "avoid active construction zones"),
    ("COMBUSTION", "combustion fumes", "avoid poorly ventilated combustion areas"),
    ("BIOMASS_OR_WASTE_BURNING", "smoke or burning", "keep indoor air protected"),
    ("INDUSTRIAL", "industrial emissions", "steer clear of industrial zones"),
    ("INDOOR_ACTIVITY", "indoor pollution", "ventilate your indoor space"),
    ("MIXED", "mixed pollution sources", "use general pollution precautions"),
    ("UNKNOWN", "an uncertain pollution source", "use general pollution precautions")
]:
    out += f'    "{src}": {{\n'
    for sub, mod in [("LOW", "possible"), ("MODERATE", "likely"), ("HIGH", "strong")]:
        b = f"there are {mod} signs of {base_str}"
        variants = get_variants(b, act)
        out += f'        "{sub}": {variants},\n'
    out += '    },\n'
out += '}\n\n'

out += 'FORECAST_VARIANTS = {\n'
for trend, base_str, act in [
    ("RISING", "pollution may increase", "take precautions early"),
    ("STABLE", "particulate levels are expected to remain stable", "plan accordingly"),
    ("FALLING", "particulate pollution may improve", "enjoy the better conditions soon")
]:
    out += f'    "{trend}": {{\n'
    for sub, mod in [("LOW", "slightly"), ("MODERATE", "moderately"), ("HIGH", "significantly")]:
        b = f"{base_str} {mod}" if "increase" in base_str or "improve" in base_str else base_str
        variants = get_variants(b, act)
        out += f'        "{sub}": {variants},\n'
    out += '    },\n'
out += '}\n\n'

out += 'WEATHER_VARIANTS = {\n'
for weather, base_str, act in [
    ("HOT_HUMID", "hot and humid conditions", "wear light clothing, hydrate, and take cooling breaks"),
    ("HOT_DRY", "hot and dry conditions", "stay hydrated and avoid sun"),
    ("HOT", "warm conditions", "wear light clothing"),
    ("COLD_HUMID", "cool and damp conditions", "wear warm, water-resistant layers"),
    ("COLD_DRY", "cool and dry conditions", "wear an extra layer and protect against dryness"),
    ("COLD", "cool conditions", "wear a suitable extra layer"),
    ("HUMID", "humid conditions", "wear breathable clothing and take cooling breaks"),
    ("DRY", "dry conditions", "stay hydrated"),
    ("COMFORTABLE", "comfortable weather", "enjoy the comfortable conditions")
]:
    out += f'    "{weather}": {{\n'
    for sub, mod in [("LOW", "mildly"), ("MODERATE", "noticeably"), ("HIGH", "very")]:
        b = f"{base_str} are {mod} present"
        variants = get_variants(b, act)
        out += f'        "{sub}": {variants},\n'
    out += '    },\n'
out += '}\n\n'

with open('Intelligence/Server/app/advisory/content.py', 'w') as f:
    f.write(out)

