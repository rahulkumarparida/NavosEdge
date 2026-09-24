
"""Friendly, human-readable advisory variants."""

AQI_VARIANTS = {
    "NORMAL": {
        "LOW": [
            "Air looks good. Enjoy some fresh air outside.",
            "The air is in a good range. A nice time to step outside.",
            "Air quality looks comfortable. Feel free to enjoy the outdoors.",
            "The air feels clean enough for your usual outdoor plans.",
            "Looks like a good day to spend some time outside.",
            "Air quality is looking good. Enjoy your day outdoors."
        ],
        "MODERATE": [
            "Air quality is still good. Outdoor activities should be fine.",
            "The air looks comfortable. You can enjoy your usual outdoor plans.",
            "Air quality is in a healthy range. Feel free to head outside.",
            "The air looks good today. Enjoy some time outdoors.",
            "Nothing concerning in the air right now. Your usual plans are fine.",
            "Air quality is looking nice. Have a good time outside."
        ],
        "HIGH": [
            "Air quality is very good. A great time to enjoy the outdoors.",
            "The air is clean and comfortable. Enjoy your outdoor plans.",
            "Air quality looks excellent. Feel free to spend time outside.",
            "The air is in a very comfortable range today.",
            "Looks like a good day for some fresh air.",
            "Air quality is looking great. Enjoy the outdoors."
        ],
    },

    "MODERATE": {
        "LOW": [
            "Air quality is starting to change. Fresh air is still fine, but take it easy.",
            "The air is a little polluted. Prefer open, well-ventilated spaces.",
            "Air quality is slightly affected. Keep your surroundings well ventilated.",
            "A little pollution is present. Fresh, open spaces are a better choice.",
            "The air is slightly hazy. Keep indoor spaces ventilated.",
            "Pollution is noticeable but mild. Normal activities should be okay."
        ],
        "MODERATE": [
            "Air quality is a little polluted. Take breaks if you're outside for long.",
            "The air is moderately polluted. Well-ventilated places are preferable.",
            "Some pollution is present. Try to avoid staying outside for too long.",
            "The air isn't at its best today. Take it easy outdoors.",
            "Moderate pollution is around. Keep your surroundings fresh and ventilated.",
            "The air is somewhat polluted. Shorter outdoor stays may be more comfortable."
        ],
        "HIGH": [
            "Air pollution is noticeable. Try to limit long outdoor activities.",
            "The air is fairly polluted today. Take regular breaks when outside.",
            "Pollution is on the higher side. Consider spending more time indoors.",
            "The air isn't very comfortable. Keep outdoor activity light.",
            "Higher pollution is present. Avoid unnecessary time near busy roads.",
            "The air is getting heavy. Take it easy and stay somewhere well ventilated."
        ],
    },

    "HIGH": {
        "LOW": [
            "Air pollution is elevated. Keep outdoor activities light.",
            "The air is a little heavy today. Avoid long outdoor sessions.",
            "Pollution is higher than usual. Take breaks when you're outside.",
            "The air isn't at its best. Keep outdoor activity moderate.",
            "Air quality is elevated. Try not to stay outside for too long.",
            "The air is somewhat polluted. A little extra caution would help."
        ],
        "MODERATE": [
            "Air pollution is fairly high. Limit long outdoor activities.",
            "The air is noticeably polluted. Take it easy when you're outside.",
            "Pollution is getting high. Consider spending more time indoors.",
            "The air feels heavy today. Avoid prolonged outdoor activity.",
            "Air quality is poor enough to take some extra care outdoors.",
            "Higher pollution is present. Keep outdoor time short when possible."
        ],
        "HIGH": [
            "Air pollution is high. It's better to keep outdoor time short.",
            "The air is quite polluted today. Stay indoors when you can.",
            "Air quality is poor. Avoid strenuous outdoor activities for now.",
            "The air feels heavy. Consider moving activities indoors.",
            "Pollution is high today. Give your lungs a break and stay indoors more.",
            "The air isn't very healthy right now. Limit unnecessary outdoor exposure."
        ],
    },

    "SEVERE": {
        "LOW": [
            "Air quality is very poor. Try to limit time outside.",
            "The air is quite polluted. Staying indoors may be more comfortable.",
            "Pollution is severe today. Keep outdoor activities to a minimum.",
            "The air is heavy. Avoid spending too much time outside.",
            "Air quality is poor enough to limit outdoor plans.",
            "Consider staying indoors more until the air improves."
        ],
        "MODERATE": [
            "Air quality is very poor. Please keep outdoor time limited.",
            "The air is heavily polluted. Indoor activities are a better choice.",
            "Pollution is quite high. Avoid unnecessary outdoor exposure.",
            "The air is unhealthy right now. Try to stay indoors when possible.",
            "Outdoor air is quite polluted. Keep your time outside short.",
            "It's a heavy-air day. Take it easy and stay indoors when you can."
        ],
        "HIGH": [
            "Air quality is very poor. Avoid outdoor activities if possible.",
            "The air is heavily polluted. It's best to stay indoors.",
            "Pollution is severe today. Keep outdoor exposure to a minimum.",
            "The air is quite unhealthy. Move activities indoors where possible.",
            "Air quality is poor enough to avoid unnecessary outdoor trips.",
            "Give your lungs a break today and stay indoors as much as possible."
        ],
    },

    "CRITICAL": {
        "LOW": [
            "Air quality has reached a critical level. Please stay indoors.",
            "The air is dangerously polluted. Avoid going outside for now.",
            "Pollution is at a critical level. Keep outdoor exposure to a minimum.",
            "The air is not safe for normal outdoor activity right now.",
            "Please avoid unnecessary outdoor trips until conditions improve.",
            "Air quality is extremely poor. Staying indoors is strongly recommended."
        ],
        "MODERATE": [
            "Air quality is critically poor. Please stay indoors if possible.",
            "The air is heavily polluted right now. Avoid outdoor exposure.",
            "Pollution has reached a critical level. Keep doors and windows closed if appropriate.",
            "The air is extremely unhealthy. Avoid unnecessary trips outside.",
            "Please limit outdoor exposure until the air improves.",
            "Air quality is at a critical level. Stay indoors and take care."
        ],
        "HIGH": [
            "Air quality is critically poor. Avoid going outside.",
            "The air is extremely polluted. Please stay indoors.",
            "Pollution is at a critical level. Avoid outdoor exposure completely if possible.",
            "The air is unsafe for normal outdoor activity right now.",
            "Please stay indoors until air quality improves.",
            "Air conditions are extremely poor. Avoid unnecessary outdoor travel."
        ],
    },
}


SOURCE_VARIANTS = {
    "TRAFFIC": {
        "LOW": [
            "Some traffic pollution may be present. Avoid busy roads when you can.",
            "Traffic emissions may be affecting the air nearby.",
            "There may be some vehicle pollution around. Choose quieter roads if possible.",
            "A little traffic pollution is showing up. Keep some distance from busy roads.",
            "Vehicle emissions may be contributing to the air quality.",
            "Busy roads may be affecting the air. A quieter route could help."
        ],
        "MODERATE": [
            "Traffic pollution is likely present. Avoid busy roads when possible.",
            "Vehicle emissions seem to be affecting the air nearby.",
            "There may be noticeable pollution from traffic around you.",
            "Busy roads are likely adding to the pollution. Consider a quieter route.",
            "Traffic appears to be contributing to the current air quality.",
            "If possible, spend less time near heavy traffic today."
        ],
        "HIGH": [
            "Traffic emissions appear strong. Stay away from busy roads if you can.",
            "Vehicle pollution is likely a major factor right now.",
            "Heavy traffic may be affecting the air significantly.",
            "The air near busy roads may be quite polluted. Choose quieter areas.",
            "Strong traffic pollution is showing up. Avoid crowded roads when possible.",
            "Try to keep some distance from heavy traffic today."
        ],
    },

    "HEAVY_DUST": {
        "LOW": [
            "Some dust may be in the air. Avoid visibly dusty spots.",
            "A little dust is showing up. Keep away from dusty areas if possible.",
            "Dust levels may be slightly elevated nearby.",
            "You may notice some extra dust around. Choose cleaner areas.",
            "Some airborne dust is present. Avoid dusty roads when you can.",
            "The air may be a little dusty today. Take it easy around dusty areas."
        ],
        "MODERATE": [
            "Dust levels look noticeable. Avoid dusty areas when possible.",
            "There is quite a bit of dust around. Cleaner areas may feel better.",
            "Dust appears to be affecting the air. Avoid dusty roads and open sites.",
            "The air is somewhat dusty. Try to stay away from visible dust.",
            "Noticeable dust is present. Keep some distance from dusty areas.",
            "Dust may be contributing to the pollution. Choose cleaner surroundings."
        ],
        "HIGH": [
            "Heavy dust is likely affecting the air. Avoid dusty areas.",
            "Dust levels look high. Stay away from construction and dusty roads.",
            "There is a lot of dust in the air. Cleaner surroundings are better right now.",
            "Heavy airborne dust is showing up. Avoid dusty outdoor areas.",
            "The air looks quite dusty. Keep away from roads or sites with loose dust.",
            "Dust pollution is high. Try to stay somewhere cleaner."
        ],
    },

    "CONSTRUCTION": {
        "LOW": [
            "Some construction dust may be nearby. Keep away from active work areas.",
            "Construction activity may be adding a little dust to the air.",
            "There may be some dust from nearby construction.",
            "A nearby construction site could be affecting the air.",
            "Construction dust may be present. Choose a cleaner route if possible.",
            "Some construction-related dust is showing up nearby."
        ],
        "MODERATE": [
            "Construction dust is likely affecting the air. Avoid active sites.",
            "Nearby construction may be adding noticeable dust.",
            "The air may be affected by dust from construction work.",
            "Try to avoid active construction areas for now.",
            "Construction activity appears to be contributing to the pollution.",
            "If possible, take a route away from construction zones."
        ],
        "HIGH": [
            "Heavy construction dust may be affecting the air. Stay away from active sites.",
            "Construction activity appears to be a strong pollution source.",
            "The air near construction areas may be quite dusty.",
            "Avoid active construction zones while dust levels are high.",
            "A lot of construction dust may be in the air right now.",
            "Choose a route away from construction areas if you can."
        ],
    },

    "COMBUSTION": {
        "LOW": [
            "Some combustion fumes may be present. Keep away from poorly ventilated areas.",
            "A little smoke or exhaust may be affecting the air nearby.",
            "Some combustion-related pollution is showing up.",
            "There may be fumes from burning or engines nearby.",
            "Keep some distance from areas with visible smoke or exhaust.",
            "A small amount of combustion pollution may be present."
        ],
        "MODERATE": [
            "Combustion fumes are likely affecting the air. Avoid enclosed smoky areas.",
            "Smoke or exhaust may be contributing to the pollution.",
            "There may be noticeable fumes from burning or engines nearby.",
            "Try to stay away from smoky or poorly ventilated areas.",
            "Combustion-related pollution appears to be present.",
            "Cleaner, well-ventilated spaces may feel better right now."
        ],
        "HIGH": [
            "Strong combustion fumes may be present. Move away from smoky areas.",
            "Smoke or exhaust appears to be a major pollution source.",
            "The air may be heavily affected by combustion fumes.",
            "Avoid areas with smoke, exhaust, or poor ventilation.",
            "Strong fumes are showing up. Find a cleaner, well-ventilated space.",
            "Combustion pollution looks high. Keep your distance from the source."
        ],
    },

    "BIOMASS_OR_WASTE_BURNING": {
        "LOW": [
            "Some smoke or burning may be nearby. Keep indoor air fresh.",
            "A little smoke may be affecting the air. Stay away from burning areas.",
            "There may be some smoke from nearby burning.",
            "Smoke or burning activity may be contributing to the pollution.",
            "Keep windows closed if smoke is entering your home.",
            "Some burning-related pollution is showing up nearby."
        ],
        "MODERATE": [
            "Smoke from burning may be affecting the air. Stay away from the source.",
            "There may be noticeable smoke from waste or biomass burning.",
            "Burning activity is likely adding to the pollution.",
            "Try to stay indoors and keep smoky air outside.",
            "Smoke levels are noticeable. Keep your indoor air as clean as possible.",
            "Avoid areas where waste or biomass is being burned."
        ],
        "HIGH": [
            "Heavy smoke may be affecting the air. Stay indoors if possible.",
            "Burning appears to be a strong source of pollution right now.",
            "The air may be heavily affected by smoke. Stay away from burning areas.",
            "Avoid smoke-filled areas and keep indoor air protected.",
            "There is a lot of smoke around. It's better to stay indoors.",
            "Strong burning-related pollution is present. Keep away from the source."
        ],
    },

    "INDUSTRIAL": {
        "LOW": [
            "Some industrial emissions may be nearby. Keep your distance from industrial areas.",
            "A little industrial pollution may be affecting the air.",
            "Nearby industrial activity may be contributing to the readings.",
            "Some emissions from industrial areas may be present.",
            "If possible, avoid staying close to industrial zones.",
            "Industrial activity may be adding a little pollution nearby."
        ],
        "MODERATE": [
            "Industrial emissions are likely affecting the air. Avoid industrial areas.",
            "Nearby industrial activity may be adding noticeable pollution.",
            "The air may be affected by emissions from nearby industries.",
            "Try to stay away from industrial zones for now.",
            "Industrial pollution appears to be contributing to the readings.",
            "A cleaner area away from industry may be more comfortable."
        ],
        "HIGH": [
            "Industrial emissions may be strong. Stay away from industrial areas.",
            "Nearby industry appears to be a major pollution source.",
            "The air may be heavily affected by industrial emissions.",
            "Avoid industrial zones while pollution levels are high.",
            "Strong industrial pollution is showing up nearby.",
            "If possible, move to an area farther from industrial activity."
        ],
    },

    "INDOOR_ACTIVITY": {
        "LOW": [
            "Indoor air may be getting a little stale. Open a window if practical.",
            "Some indoor pollution may be present. A little fresh air could help.",
            "Indoor air looks slightly affected. Keep the room ventilated.",
            "A bit of indoor pollution is showing up. Let some fresh air in.",
            "Your indoor air may need a little ventilation.",
            "Try opening a window or improving airflow if possible."
        ],
        "MODERATE": [
            "Indoor pollution is noticeable. Improve ventilation if you can.",
            "The room may need some fresh air. Open a window if practical.",
            "Indoor air looks somewhat polluted. Better airflow could help.",
            "The air inside feels a little heavy. Give the room some ventilation.",
            "Some indoor pollution is building up. Fresh airflow may help.",
            "Try ventilating the room for a while."
        ],
        "HIGH": [
            "Indoor pollution is high. Improve ventilation and move to cleaner air if possible.",
            "The indoor air is quite polluted. Get some fresh air into the room.",
            "Air inside may be unhealthy right now. Improve airflow if you can.",
            "The room air looks heavy. Ventilate the space as soon as practical.",
            "Indoor pollution is high. A cleaner, well-ventilated space would be better.",
            "The air inside needs attention. Improve ventilation if possible."
        ],
    },

    "MIXED": {
        "LOW": [
            "A few pollution sources may be contributing. Take normal precautions.",
            "The readings suggest more than one possible pollution source.",
            "There may be a mix of pollution sources nearby.",
            "Pollution seems to be coming from several possible sources.",
            "The source isn't clear, so general air-quality precautions are best.",
            "A few factors may be affecting the air. Keep things simple and stay aware."
        ],
        "MODERATE": [
            "Several pollution sources may be affecting the air. Take extra care outside.",
            "The air appears to be affected by more than one source.",
            "A mix of pollution sources may be contributing right now.",
            "The source looks mixed. Avoid heavily polluted areas when possible.",
            "Several factors may be adding to the pollution. Keep outdoor time moderate.",
            "Pollution seems to have multiple sources. General precautions are a good idea."
        ],
        "HIGH": [
            "Several pollution sources may be active. Limit outdoor exposure.",
            "The air appears to be affected by multiple strong sources.",
            "Pollution is coming from a mix of possible sources. Stay in cleaner areas.",
            "Several factors may be driving the poor air quality.",
            "The source is mixed and pollution is high. Keep outdoor time short.",
            "Multiple pollution sources may be active. Take extra care today."
        ],
    },

    "UNKNOWN": {
        "LOW": [
            "The pollution source isn't clear yet. Take normal precautions.",
            "We're not sure what's causing the change. Keep an eye on the air.",
            "The source is unclear, but pollution levels are only slightly affected.",
            "Something may be affecting the air, but the source isn't clear.",
            "The readings don't point to one clear source. Stay aware of changes.",
            "The source is uncertain for now. General precautions are enough."
        ],
        "MODERATE": [
            "The pollution source isn't clear. Take a little extra care outside.",
            "We're seeing pollution, but the exact source is uncertain.",
            "The source isn't obvious yet. Avoid heavily polluted areas when possible.",
            "The readings suggest pollution without a clear source.",
            "We're not sure what's driving the pollution. Keep outdoor time moderate.",
            "The source is still unclear. General air-quality precautions are recommended."
        ],
        "HIGH": [
            "The source isn't clear, but pollution is high. Limit outdoor exposure.",
            "We're seeing high pollution without one clear source. Stay in cleaner air.",
            "The exact source is uncertain. It's best to reduce outdoor time.",
            "Pollution is high, even though the source isn't clear yet.",
            "The readings show poor air quality. Take extra care while the source is uncertain.",
            "We can't identify one clear source. Stay indoors more while pollution is high."
        ],
    },
}


FORECAST_VARIANTS = {
    "RISING": {
        "LOW": [
            "Pollution may rise a little soon. A little caution now could help.",
            "Air quality may get slightly worse. Plan ahead if you're going outside.",
            "Pollution looks like it may increase. Keep an eye on the readings.",
            "The air may become a little more polluted soon.",
            "Conditions may worsen slightly. It's worth planning ahead.",
            "Pollution could pick up soon. Take precautions early."
        ],
        "MODERATE": [
            "Pollution may increase soon. Consider limiting longer outdoor plans.",
            "Air quality could get noticeably worse. Plan ahead.",
            "The air may become more polluted over the next few hours.",
            "Pollution is trending upward. Keep outdoor plans flexible.",
            "Conditions may worsen moderately. Take precautions early.",
            "The air may get heavier soon. Keep an eye on the trend."
        ],
        "HIGH": [
            "Pollution may rise significantly. It's better to plan indoor options.",
            "Air quality could get much worse soon. Consider staying indoors.",
            "Pollution is trending upward quickly. Limit unnecessary outdoor plans.",
            "The air may become heavily polluted soon.",
            "Conditions could worsen significantly. Take precautions now.",
            "Pollution may climb soon. Keep outdoor exposure as low as practical."
        ],
    },

    "STABLE": {
        "LOW": [
            "Air quality looks steady. Your usual plans should be fine.",
            "Pollution levels are staying about the same.",
            "The air looks stable for now. Nothing much is changing.",
            "Conditions appear steady. Keep doing what works for you.",
            "Air quality is holding steady.",
            "No major change is expected in the near term."
        ],
        "MODERATE": [
            "Air quality looks steady for now. Plan your day normally.",
            "Pollution levels aren't changing much at the moment.",
            "The air is expected to stay around its current level.",
            "Conditions look fairly stable for now.",
            "No major change in pollution is expected soon.",
            "The air should remain around the current level for a while."
        ],
        "HIGH": [
            "Pollution is likely to stay high for now. Keep outdoor time limited.",
            "The air may remain poor for a while. Plan indoor options.",
            "Conditions look steady, but pollution is still high.",
            "No quick improvement is expected. Take it easy outdoors.",
            "Air quality is staying poor for now. Keep exposure low.",
            "The current pollution level may continue for a while."
        ],
    },

    "FALLING": {
        "LOW": [
            "Air quality may improve a little soon. Better conditions could be on the way.",
            "Pollution is starting to ease. The air may feel better soon.",
            "The air looks like it's improving slightly.",
            "Conditions are moving in a better direction.",
            "Pollution may continue to drop a little.",
            "The air is starting to clear. That's a good sign."
        ],
        "MODERATE": [
            "Pollution is starting to come down. Air quality may improve soon.",
            "The air is gradually getting better.",
            "Conditions are improving. Outdoor air may feel more comfortable soon.",
            "Pollution is trending downward.",
            "The air may become noticeably cleaner soon.",
            "Things are moving in a better direction. Keep an eye on the trend."
        ],
        "HIGH": [
            "Pollution is falling, but the air is still poor for now.",
            "Conditions are improving, though it may take some time.",
            "The air is starting to clear. Keep outdoor exposure limited for now.",
            "Pollution is coming down, but levels are still high.",
            "Things are getting better, but it's still worth taking care outside.",
            "The trend is improving. Better air may arrive soon."
        ],
    },
}


WEATHER_VARIANTS = {
    "HOT_HUMID": {
        "LOW": [
            "It's a little hot and humid. Light clothes and some water should help.",
            "Warm and humid today. Keep water nearby and take breaks.",
            "It's slightly sticky outside. Wear something light and breathable.",
            "A bit of heat and humidity is around. Stay hydrated.",
            "Warm, humid weather today. Light clothing should feel comfortable.",
            "It's getting warm and humid. Keep yourself cool and hydrated."
        ],
        "MODERATE": [
            "It's hot and humid. Light clothes, water, and regular breaks will help.",
            "Warm and sticky outside. Stay hydrated and take it easy in the heat.",
            "The humidity is noticeable today. Keep cool and drink plenty of water.",
            "It's a warm, humid day. Breathable clothes will feel better.",
            "Heat and humidity are fairly high. Take cooling breaks when needed.",
            "It's feeling quite humid. Keep water nearby and avoid staying in the heat too long."
        ],
        "HIGH": [
            "It's very hot and humid. Stay cool, drink water, and take frequent breaks.",
            "The heat and humidity are high. Keep outdoor time comfortable and short.",
            "It's quite hot outside. Light clothes, water, and shade will help.",
            "Hot and sticky conditions today. Try to stay somewhere cool.",
            "The heat is strong. Take regular cooling breaks and stay hydrated.",
            "It's a very humid day. Keep cool and avoid unnecessary time in the heat."
        ],
    },

    "HOT_DRY": {
        "LOW": [
            "It's warm and dry. Keep some water with you.",
            "A little heat and dryness today. Stay hydrated.",
            "It's warm outside. Drink water and take breaks from the sun.",
            "Warm, dry weather today. A little shade will feel good.",
            "The air is warm and dry. Keep yourself hydrated.",
            "It's a sunny, dry kind of day. Water and shade should help."
        ],
        "MODERATE": [
            "It's hot and dry. Keep water nearby and take breaks from the sun.",
            "The heat is noticeable today. Stay hydrated and use some shade.",
            "Warm, dry conditions outside. Drink plenty of water.",
            "It's getting hot. Try to avoid long periods in direct sun.",
            "The air is hot and dry. Keep cool and hydrated.",
            "A hot, dry day today. Take breaks and stay out of the strongest sun."
        ],
        "HIGH": [
            "It's very hot and dry. Stay hydrated and avoid strong midday sun.",
            "The heat is intense. Keep water nearby and stay somewhere cool.",
            "Hot, dry conditions today. Limit long periods in direct sunlight.",
            "It's quite hot outside. Take frequent breaks and keep yourself hydrated.",
            "The heat is strong today. Shade and plenty of water will help.",
            "Very warm and dry conditions. Try to stay cool during the hottest hours."
        ],
    },

    "HOT": {
        "LOW": [
            "It's pleasantly warm. Light clothes should feel comfortable.",
            "Warm weather today. A light outfit should be enough.",
            "It's a little warm outside. Keep things light and comfortable.",
            "The weather is warm and easygoing. Light clothing should work well.",
            "A warm day ahead. Dress comfortably and keep some water nearby.",
            "It's warming up outside. Light clothes should do nicely."
        ],
        "MODERATE": [
            "It's fairly warm today. Light, breathable clothes should help.",
            "The weather is warm. Keep your outfit light and comfortable.",
            "It's a warm day outside. A light outfit should feel good.",
            "Warm conditions today. Stay comfortable and drink some water.",
            "It's getting quite warm. Light clothing is a good choice.",
            "The heat is noticeable, but manageable. Keep things light."
        ],
        "HIGH": [
            "It's very warm today. Wear light clothes and take breaks from the heat.",
            "The heat is strong. Keep your clothes light and stay hydrated.",
            "It's quite hot outside. Try to stay cool and avoid the strongest sun.",
            "A hot day today. Light clothing and plenty of water will help.",
            "The temperature is high. Keep cool and take breaks when needed.",
            "It's hot out there. Stay hydrated and find some shade when you can."
        ],
    },

    "COLD_HUMID": {
        "LOW": [
            "It's a little cool and damp. A warm layer should feel nice.",
            "Cool and slightly damp today. Keep a light jacket nearby.",
            "The weather feels cool and moist. A warm layer may help.",
            "A chilly, damp day. Something warm and water-resistant would be handy.",
            "It's cool outside with some humidity. Dress in comfortable layers.",
            "Cool and damp weather today. A light warm layer should do."
        ],
        "MODERATE": [
            "It's cool and damp. A warm, water-resistant layer should help.",
            "The weather is chilly and humid. Keep yourself warm and dry.",
            "Cool, damp conditions today. A jacket or light rain layer may help.",
            "It's feeling chilly outside. Warm layers will make things more comfortable.",
            "Cool and damp weather calls for a warm, comfortable layer.",
            "The air is cool and moist. Dress warmly and keep dry."
        ],
        "HIGH": [
            "It's quite cold and damp. Dress warmly and keep yourself dry.",
            "Cold, wet-feeling weather today. Warm layers and a water-resistant jacket will help.",
            "The weather is chilly and damp. Stay warm and avoid getting soaked.",
            "It's cold and humid outside. Bundle up and keep dry.",
            "A cold, damp day ahead. Warm layers are a good idea.",
            "It's pretty chilly out. Keep warm and protected from the damp air."
        ],
    },

    "COLD_DRY": {
        "LOW": [
            "It's cool and dry. An extra layer should feel comfortable.",
            "Cool, dry weather today. Keep a light jacket nearby.",
            "It's a little chilly outside. A warm layer should be enough.",
            "Cool and dry conditions. Dress in a comfortable extra layer.",
            "The air is cool and dry. Keep yourself warm and comfortable.",
            "A slightly chilly day. A light jacket should do nicely."
        ],
        "MODERATE": [
            "It's cool and dry. A warm extra layer will help.",
            "The air is chilly and dry. Dress warmly and keep comfortable.",
            "Cool weather today. A jacket or sweater should feel good.",
            "It's getting chilly. Keep an extra layer handy.",
            "The weather is cool and dry. Dress warmly when heading out.",
            "A crisp, chilly day. A comfortable warm layer should help."
        ],
        "HIGH": [
            "It's quite cold and dry. Bundle up and protect yourself from the dry air.",
            "The cold is noticeable. Wear warm layers and stay comfortable.",
            "It's chilly outside. A good warm layer will make a big difference.",
            "Cold, dry weather today. Keep yourself warm and comfortable.",
            "The air is cold and dry. Dress warmly and stay hydrated.",
            "It's a cold day. Bundle up before heading outside."
        ],
    },

    "COLD": {
        "LOW": [
            "It's a little cool. A light extra layer should be enough.",
            "Cool weather today. Keep a jacket nearby.",
            "It's slightly chilly outside. A light layer should feel nice.",
            "The weather is cool and comfortable with a warm layer.",
            "A little chilly today. Dress in something comfortable and warm.",
            "It's cool outside. A light jacket should do."
        ],
        "MODERATE": [
            "It's fairly cool today. A warm layer will help.",
            "The weather is chilly. Keep a jacket or sweater handy.",
            "It's cool outside. Dress warmly and stay comfortable.",
            "A chilly day today. An extra layer is a good idea.",
            "The temperature is on the cooler side. Keep yourself warm.",
            "Cool weather ahead. A comfortable jacket should help."
        ],
        "HIGH": [
            "It's quite cold today. Bundle up before heading outside.",
            "The cold is strong today. Wear a good warm layer.",
            "It's chilly outside. Keep yourself warm and comfortable.",
            "Cold weather today. A jacket or sweater is definitely useful.",
            "The temperature is low. Dress warmly before heading out.",
            "It's a cold day. Bundle up and keep warm."
        ],
    },

    "HUMID": {
        "LOW": [
            "It's a little humid. Light, breathable clothes should feel good.",
            "A bit of humidity today. Keep cool and comfortable.",
            "The air feels slightly sticky. Breathable clothes may help.",
            "It's mildly humid outside. Keep water nearby.",
            "A little humidity is around. Light clothing should feel better.",
            "The air is slightly damp. Stay comfortable and keep cool."
        ],
        "MODERATE": [
            "It's fairly humid today. Wear breathable clothes and take breaks.",
            "The air feels sticky. Light clothing and some water will help.",
            "Humidity is noticeable. Keep cool and stay hydrated.",
            "It's a humid day. Breathable clothes will feel more comfortable.",
            "The air is quite damp. Take cooling breaks when needed.",
            "It's feeling sticky outside. Stay cool and keep water nearby."
        ],
        "HIGH": [
            "It's very humid today. Stay cool, hydrated, and take regular breaks.",
            "The air is quite sticky. Light clothes and plenty of water will help.",
            "Humidity is high. Try to stay somewhere cool and comfortable.",
            "It's a very humid day. Take breaks from the heat and stay hydrated.",
            "The air feels heavy and damp. Keep cool and drink plenty of water.",
            "High humidity today. Breathable clothes and regular cooling breaks will help."
        ],
    },

    "DRY": {
        "LOW": [
            "The air is a little dry. Keep some water nearby.",
            "It's slightly dry outside. Stay comfortable and hydrated.",
            "Dry air today. A little extra water may help.",
            "The air feels dry. Keep yourself hydrated.",
            "It's a mildly dry day. Remember to drink enough water.",
            "Dry conditions today. Keep water handy."
        ],
        "MODERATE": [
            "The air is fairly dry. Keep yourself well hydrated.",
            "It's a dry day. Drink water regularly.",
            "Dry air is noticeable today. Keep water nearby.",
            "The weather is quite dry. Stay hydrated and comfortable.",
            "It's feeling dry outside. A little extra hydration may help.",
            "Dry conditions today. Remember to keep drinking water."
        ],
        "HIGH": [
            "The air is very dry. Drink plenty of water and stay comfortable.",
            "It's quite dry today. Keep yourself well hydrated.",
            "Dry conditions are strong. Keep water nearby throughout the day.",
            "The air is very dry. Stay hydrated and avoid getting overheated.",
            "It's a particularly dry day. Drink water regularly.",
            "Very dry conditions today. Keep yourself hydrated."
        ],
    },

    "COMFORTABLE": {
        "LOW": [
            "The weather feels nice and easy today. Enjoy it.",
            "Comfortable weather outside. A good time to step out.",
            "The weather looks pleasant. Enjoy your day.",
            "It feels nice outside. Make the most of it.",
            "Pleasant conditions today. Enjoy some time outdoors.",
            "The weather is feeling comfortable. Have a good day outside."
        ],
        "MODERATE": [
            "The weather is comfortably pleasant today. Enjoy your plans.",
            "Conditions look nice and balanced. A good day to be outside.",
            "The weather feels comfortable. Enjoy some time outdoors.",
            "It's a pleasant day outside. Nothing much to worry about weather-wise.",
            "The conditions look quite comfortable today.",
            "Nice weather today. Enjoy your usual plans."
        ],
        "HIGH": [
            "The weather looks especially comfortable today. Enjoy the outdoors.",
            "Conditions are very pleasant. A great time to spend some time outside.",
            "The weather is feeling really nice today. Enjoy it.",
            "Everything looks comfortable outside. Make the most of the day.",
            "A very pleasant day ahead. Enjoy your outdoor plans.",
            "The weather is at a comfortable level. Have a good day outside."
        ],
    },
}

