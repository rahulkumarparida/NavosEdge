
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


# =====================================================================
# Gas Hazard Advisory Variants (English, Hindi, Odia)
# =====================================================================

GAS_VARIANTS_EN = {
    "CO": {
        "CRITICAL": {
            "LOW": [
                "Urgent: Dangerous Carbon Monoxide (CO) levels detected. Toxic gas hazard. Evacuate immediately.",
                "Hazard alert: Critical Carbon Monoxide spike. Move to fresh air without delay.",
                "Emergency warning: Lethal Carbon Monoxide concentration detected. Evacuate enclosed area."
            ],
            "MODERATE": [
                "Urgent: High Carbon Monoxide (CO) danger. Evacuate immediately into fresh outdoor air.",
                "Hazard alert: Severe Carbon Monoxide buildup. Cease indoor activities and leave premises."
            ],
            "HIGH": [
                "Critical Alert: Extreme Carbon Monoxide hazard. Immediate evacuation required."
            ]
        },
        "SEVERE": {
            "LOW": [
                "Carbon Monoxide (CO) levels are elevated and hazardous. Ventilate the area thoroughly.",
                "Hazard warning: Significant Carbon Monoxide detected. Inspect heaters and combustion appliances."
            ],
            "MODERATE": [
                "Warning: High Carbon Monoxide levels present. Open doors and windows and avoid prolonged exposure."
            ],
            "HIGH": [
                "Severe Carbon Monoxide presence detected. Ventilate immediately and inspect gas appliances."
            ]
        },
        "HIGH": {
            "LOW": [
                "Carbon Monoxide is noticeably elevated. Ensure sufficient ventilation.",
                "Advisory: Elevated CO detected. Check combustion heaters or vehicle exhaust infiltration."
            ],
            "MODERATE": [
                "Elevated Carbon Monoxide levels. Keep indoor areas well-ventilated."
            ],
            "HIGH": [
                "Caution: Higher than normal Carbon Monoxide detected. Check ventilation."
            ]
        },
        "MODERATE": {
            "LOW": [
                "Mild Carbon Monoxide elevation detected. Keep spaces ventilated.",
                "Slight CO rise observed. Standard monitoring advised."
            ],
            "MODERATE": [
                "Low-level Carbon Monoxide detected. Maintain open airflow."
            ],
            "HIGH": [
                "Minor CO elevation. Ensure ongoing ventilation."
            ]
        }
    },
    "FLAMMABLE": {
        "CRITICAL": {
            "LOW": [
                "Urgent: Combustible gas leak detected. Flammable explosion hazard. Evacuate immediately.",
                "Danger: High combustible gas concentration. Do not operate electrical switches or open flames.",
                "Critical Alert: Severe flammable gas spike. Evacuate premises and call emergency services."
            ],
            "MODERATE": [
                "Emergency warning: High flammable gas leak. Evacuate immediately and avoid any ignition sources."
            ],
            "HIGH": [
                "Explosion hazard: Severe combustible gas concentration. Immediate evacuation required."
            ]
        },
        "SEVERE": {
            "LOW": [
                "Combustible gas levels are high. Ventilate the area and eliminate open flames.",
                "Hazard warning: Significant flammable gas detected. Check gas cylinders and pipeline valves."
            ],
            "MODERATE": [
                "Warning: High combustible gas presence. Shut off gas supply if accessible safely."
            ],
            "HIGH": [
                "Severe flammable gas concentration. Ensure rapid ventilation and avoid sparks."
            ]
        },
        "HIGH": {
            "LOW": [
                "Combustible gas is elevated above normal. Inspect gas connections.",
                "Advisory: Flammable gas levels rising. Ensure adequate air exchange."
            ],
            "MODERATE": [
                "Elevated flammable gas reading. Check burners and gas cylinders."
            ],
            "HIGH": [
                "Caution: Higher combustible gas readings detected. Check gas fittings."
            ]
        },
        "MODERATE": {
            "LOW": [
                "Mild combustible gas reading observed. Maintain airflow.",
                "Slight flammable gas fluctuation detected. Keep area ventilated."
            ],
            "MODERATE": [
                "Low-level flammable gas presence. Ensure natural ventilation."
            ],
            "HIGH": [
                "Minor gas elevation. Check gas appliances."
            ]
        }
    },
    "TOXIC_VOC": {
        "CRITICAL": {
            "LOW": [
                "Urgent: Dangerous chemical vapor or toxic VOC spike detected. Evacuate affected area.",
                "Hazard alert: Critical toxic gas / VOC concentration. Move away from vapor source immediately.",
                "Emergency warning: Extreme volatile organic compound spike. Seek fresh air."
            ],
            "MODERATE": [
                "Severe chemical fume hazard. Leave the enclosed area and ensure powerful ventilation."
            ],
            "HIGH": [
                "Critical chemical vapor alert. Immediate evacuation of affected room recommended."
            ]
        },
        "SEVERE": {
            "LOW": [
                "Toxic VOC levels are severely elevated. Ventilate the area aggressively.",
                "Warning: High concentration of hazardous fumes or vapors detected. Avoid breathing vapors."
            ],
            "MODERATE": [
                "Hazardous chemical vapor detected. Open all windows and ventilate."
            ],
            "HIGH": [
                "Severe VOC buildup. Remove open solvent containers and ventilate."
            ]
        },
        "HIGH": {
            "LOW": [
                "Toxic VOCs or chemical vapors are elevated. Improve ventilation.",
                "Advisory: Chemical fumes detected. Avoid staying in poorly ventilated areas."
            ],
            "MODERATE": [
                "Elevated VOC readings. Ensure good cross-ventilation."
            ],
            "HIGH": [
                "Higher than normal chemical vapor levels. Keep room ventilated."
            ]
        },
        "MODERATE": {
            "LOW": [
                "Mild VOC elevation detected. Keep spaces ventilated.",
                "Slight chemical odor or vapor detected. Open windows for fresh air."
            ],
            "MODERATE": [
                "Moderate chemical vapor presence. Ensure steady airflow."
            ],
            "HIGH": [
                "Minor VOC reading. Keep surrounding air circulating."
            ]
        }
    },
    "SMOKE": {
        "CRITICAL": {
            "LOW": [
                "Urgent: Dense smoke or combustion fumes detected nearby. Immediate fire hazard caution.",
                "Danger: Extreme smoke concentration. Evacuate affected area and check for active fire.",
                "Critical Alert: Heavy combustion smoke detected. Move to safety."
            ],
            "MODERATE": [
                "Hazard alert: Critical smoke levels. Evacuate smoke-filled area immediately."
            ],
            "HIGH": [
                "Dense smoke hazard detected. Protect respiratory tract and evacuate."
            ]
        },
        "SEVERE": {
            "LOW": [
                "Heavy smoke or combustion fumes present. Keep airways protected and move away from source.",
                "Warning: Significant combustion smoke detected. Inspect surrounding area for fire sources."
            ],
            "MODERATE": [
                "Dense smoke observed. Limit exposure and find fresh air."
            ],
            "HIGH": [
                "Severe combustion smoke levels. Use respiratory protection and ventilate."
            ]
        },
        "HIGH": {
            "LOW": [
                "Combustion smoke is elevated. Avoid proximity to burning sources.",
                "Advisory: Smoke fumes detected. Keep doors and windows protected from external smoke."
            ],
            "MODERATE": [
                "Noticeable smoke in the air. Avoid active combustion areas."
            ],
            "HIGH": [
                "Elevated smoke levels. Protect sensitive individuals from inhalation."
            ]
        },
        "MODERATE": {
            "LOW": [
                "Mild smoke detected. Keep distance from active burning.",
                "Slight smoke haze observed. Standard precautions recommended."
            ],
            "MODERATE": [
                "Low-level smoke presence. Avoid direct exposure."
            ],
            "HIGH": [
                "Minor smoke elevation. Keep surroundings ventilated."
            ]
        }
    },
    "GAS_SPIKE": {
        "CRITICAL": {
            "LOW": [
                "Urgent: Rapid acute toxic gas spike detected. Evacuate area immediately.",
                "Hazard alert: Sudden intense gas surge detected. Check for acute leaks and move to safety."
            ],
            "MODERATE": [
                "Emergency warning: Fast-rising gas spike. Evacuate and avoid ignition."
            ],
            "HIGH": [
                "Critical gas surge detected. Immediate evacuation recommended."
            ]
        },
        "SEVERE": {
            "LOW": [
                "Rapid gas surge detected across telemetry. Inspect gas lines and ventilate.",
                "Warning: Fast-rising chemical vapor surge. Ensure immediate ventilation."
            ],
            "MODERATE": [
                "Acute gas elevation observed. Increase fresh airflow."
            ],
            "HIGH": [
                "Sudden gas surge. Check appliances and ventilate."
            ]
        },
        "HIGH": {
            "LOW": [
                "Noticeable gas elevation rate observed. Keep area ventilated.",
                "Advisory: Gas concentration rising faster than baseline. Monitor closely."
            ],
            "MODERATE": [
                "Rising gas readings detected. Ensure active ventilation."
            ],
            "HIGH": [
                "Gas rate-of-change elevated. Maintain open airflow."
            ]
        },
        "MODERATE": {
            "LOW": [
                "Mild gas fluctuation observed. Maintain steady airflow."
            ],
            "MODERATE": [
                "Minor gas variation detected. Standard monitoring advised."
            ],
            "HIGH": [
                "Slight gas rate change. Keep area ventilated."
            ]
        }
    }
}


GAS_VARIANTS_HI = {
    "CO": {
        "CRITICAL": {
            "LOW": [
                "चेतावनी: खतरनाक कार्बन मोनोऑक्साइड (CO) का स्तर पाया गया। तुरंत बाहर निकलें और ताज़ी हवा में जाएं।",
                "गंभीर खतरा: कार्बन मोनोऑक्साइड का घातक स्तर। बिना देरी किए खुले स्थान पर जाएं।",
                "आपातकालीन चेतावनी: जानलेवा कार्बन मोनोऑक्साइड गैस रिसाव। तुरंत बंद क्षेत्र खाली करें।"
            ],
            "MODERATE": [
                "अति गंभीर: कार्बन मोनोऑक्साइड का जानलेवा स्तर। तुरंत ताज़ी हवा में जाएं।"
            ],
            "HIGH": [
                "खतरनाक कार्बन मोनोऑक्साइड रिसाव। तुरंत सुरक्षित स्थान पर जाएं।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "कार्बन मोनोऑक्साइड (CO) का स्तर खतरनाक रूप से बढ़ा हुआ है। वेंटिलेशन तुरंत बढ़ाएं।",
                "चेतावनी: काफी मात्रा में कार्बन मोनोऑक्साइड पाई गई है। हीटर और गैस उपकरणों की जाँच करें।"
            ],
            "MODERATE": [
                "उच्च कार्बन मोनोऑक्साइड स्तर। खिड़कियाँ और दरवाजे खोलें और बाहर निकलें।"
            ],
            "HIGH": [
                "गंभीर कार्बन मोनोऑक्साइड की उपस्थिति। गैस उपकरणों की तत्काल जाँच करें।"
            ]
        },
        "HIGH": {
            "LOW": [
                "कार्बन मोनोऑक्साइड का स्तर सामान्य से अधिक है। अच्छा वेंटिलेशन सुनिश्चित करें।",
                "सावधानी: हीटर या वाहन उत्सर्जन की जाँच करें। CO का स्तर बढ़ा हुआ है।"
            ],
            "MODERATE": [
                "बढ़ा हुआ कार्बन मोनोऑक्साइड स्तर। हवादार जगह में रहें।"
            ],
            "HIGH": [
                "कार्बन मोनोऑक्साइड में वृद्धि। इनडोर वेंटिलेशन की जाँच करें।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "कार्बन मोनोऑक्साइड में हल्की वृद्धि देखी गई है। हवा का बहाव बनाए रखें।",
                "हल्का CO स्तर। सामान्य निगरानी की सलाह दी जाती है।"
            ],
            "MODERATE": [
                "कार्बन मोनोऑक्साइड में सामान्य से थोड़ी वृद्धि। वेंटिलेशन बनाए रखें।"
            ],
            "HIGH": [
                "हल्की CO उपस्थिति। ताज़ी हवा आने दें।"
            ]
        }
    },
    "FLAMMABLE": {
        "CRITICAL": {
            "LOW": [
                "ज्वलनशील या एलपीजी गैस रिसाव का पता चला है। आग और विस्फोट का भारी खतरा। तुरंत स्थान खाली करें।",
                "खतरा: ज्वलनशील गैस की अत्यधिक सांद्रता। बिजली के स्विच या खुली आग का उपयोग बिल्कुल न करें।",
                "आपातकालीन चेतावनी: गैस रिसाव से आग का भारी खतरा। सुरक्षित दूरी से आपातकालीन सेवाओं को सूचित करें।"
            ],
            "MODERATE": [
                "आपातकालीन अलर्ट: गंभीर गैस रिसाव। तुरंत बाहर निकलें और स्पार्क से बचें।"
            ],
            "HIGH": [
                "विस्फोट का खतरा: अत्यधिक ज्वलनशील गैस। तुरंत परिसर खाली करें।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "ज्वलनशील गैस का बढ़ा हुआ स्तर पाया गया है। सतर्क रहें और वेंटिलेशन सुनिश्चित करें।",
                "चेतावनी: ज्वलनशील गैस की उपस्थिति। गैस सिलेंडर और पाइपलाइन की जाँच करें।"
            ],
            "MODERATE": [
                "उच्च ज्वलनशील गैस स्तर। यदि संभव हो तो मुख्य गैस आपूर्ति बंद करें।"
            ],
            "HIGH": [
                "गंभीर गैस सांद्रता। किसी भी चिंगारी से बचें और वेंटिलेशन करें।"
            ]
        },
        "HIGH": {
            "LOW": [
                "हल्की ज्वलनशील गैस की उपस्थिति दर्ज की गई है। गैस लाइनों की जाँच करें।",
                "सावधानी: ज्वलनशील गैस सामान्य से अधिक है। बर्नर और वाल्व की जाँच करें।"
            ],
            "MODERATE": [
                "बढ़ी हुई गैस रीडिंग। गैस कनेक्शन सुरक्षित करें।"
            ],
            "HIGH": [
                "गैस स्तर बढ़ा हुआ है। सावधानीपूर्वक निरीक्षण करें।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "हल्की ज्वलनशील गैस देखी गई है। हवा का प्रवाह बनाए रखें।",
                "मामूली गैस उतार-चढ़ाव। स्थान को हवादार रखें।"
            ],
            "MODERATE": [
                "कम स्तर की ज्वलनशील गैस। प्राकृतिक वेंटिलेशन सुनिश्चित करें।"
            ],
            "HIGH": [
                "मामूली गैस उपस्थिति। उपकरणों की जाँच करें।"
            ]
        }
    },
    "TOXIC_VOC": {
        "CRITICAL": {
            "LOW": [
                "अत्यधिक विषाक्त रासायनिक वाष्प या वीओसी (VOC) का स्तर पाया गया। तुरंत क्षेत्र से दूर जाएं।",
                "गंभीर चेतावनी: खतरनाक रासायनिक वाष्प। बिना मास्क के वाष्प स्रोत के पास न जाएं।",
                "आपातकालीन अलर्ट: विषाक्त गैस का तीव्र प्रसार। ताज़ी हवा में जाएं।"
            ],
            "MODERATE": [
                "विषाक्त रासायनिक खतरा। तुरंत बंद कमरा छोड़ें और वेंटिलेशन चालू करें।"
            ],
            "HIGH": [
                "गंभीर रासायनिक वाष्प चेतावनी। प्रभावित क्षेत्र को तुरंत खाली करें।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "रासायनिक वाष्प या वीओसी प्रदूषण उच्च स्तर पर है। अच्छा वेंटिलेशन रखें।",
                "चेतावनी: हानिकारक गैसों और वाष्प का उच्च स्तर। सीधे सांस लेने से बचें।"
            ],
            "MODERATE": [
                "खतरनाक रासायनिक वाष्प। सभी खिड़कियाँ खोलें और ताज़ी हवा आने दें।"
            ],
            "HIGH": [
                "उच्च वीओसी संचय। खुले सॉल्वैंट्स और रसायनों को तुरंत हटाएं।"
            ]
        },
        "HIGH": {
            "LOW": [
                "रासायनिक गंध या वाष्प का स्तर बढ़ा हुआ है। वेंटिलेशन में सुधार करें।",
                "सावधानी: रासायनिक वाष्प दर्ज की गई है। बंद स्थानों में अधिक समय न बिताएं।"
            ],
            "MODERATE": [
                "बढ़ी हुई वीओसी रीडिंग। अच्छा क्रॉस-वेंटिलेशन रखें।"
            ],
            "HIGH": [
                "सामान्य से अधिक रासायनिक वाष्प। खिड़कियाँ खुली रखें।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "हल्की वीओसी सांद्रता दर्ज की गई है। वेंटिलेशन बनाए रखें।",
                "मामूली रासायनिक गंध। ताज़ी हवा के लिए खिड़कियाँ खोलें।"
            ],
            "MODERATE": [
                "मध्यम रासायनिक वाष्प। हवा का प्रवाह जारी रखें।"
            ],
            "HIGH": [
                "मामूली वीओसी वृद्धि। वेंटिलेशन सुनिश्चित करें।"
            ]
        }
    },
    "SMOKE": {
        "CRITICAL": {
            "LOW": [
                "घना धुआँ और दहन गैसें दर्ज की गई हैं। आग के खतरे से तुरंत सतर्क रहें और बाहर निकलें।",
                "खतरा: अत्यधिक धुआँ। प्रभावित क्षेत्र खाली करें और श्वसन मार्ग की रक्षा करें।"
            ],
            "MODERATE": [
                "गंभीर धुआँ खतरा। तुरंत धुएँ वाले क्षेत्र से बाहर निकलें।"
            ],
            "HIGH": [
                "घना धुआँ उपस्थित है। तुरंत सुरक्षित स्थान पर जाएं।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "भारी धुआँ मौजूद है। श्वसन सुरक्षा का उपयोग करें और स्रोत से दूर रहें।",
                "चेतावनी: दहन का भारी धुआँ। आसपास आग के स्रोतों की जाँच करें।"
            ],
            "MODERATE": [
                "घना धुआँ देखा गया है। ताज़ी हवा वाले स्थान पर जाएं।"
            ],
            "HIGH": [
                "गंभीर धुआँ स्तर। मास्क का उपयोग करें और वेंटिलेशन करें।"
            ]
        },
        "HIGH": {
            "LOW": [
                "हल्का धुआँ देखा गया है। जलने वाले स्रोतों से दूर रहें।",
                "सावधानी: धुएँ की गंध मौजूद है। बाहरी धुएँ से इनडोर हवा को बचाएं।"
            ],
            "MODERATE": [
                "हवा में धुआँ दिखाई दे रहा है। धुएँ वाले क्षेत्रों से बचें।"
            ],
            "HIGH": [
                "बढ़ा हुआ धुआँ स्तर। संवेदनशील लोग सावधानी बरतें।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "मामूली धुआँ दर्ज किया गया है। जलने के स्रोतों से दूरी बनाए रखें।"
            ],
            "MODERATE": [
                "हल्का धुआँ मौजूद है। सीधे संपर्क से बचें।"
            ],
            "HIGH": [
                "मामूली धुआँ वृद्धि। वेंटिलेशन बनाए रखें।"
            ]
        }
    },
    "GAS_SPIKE": {
        "CRITICAL": {
            "LOW": [
                "अचानक तीव्र गैस रिसाव का पता चला है। तुरंत क्षेत्र खाली करें।",
                "आपातकालीन अलर्ट: गैस सांद्रता में अचानक भारी उछाल। तुरंत ताज़ी हवा में जाएं।"
            ],
            "MODERATE": [
                "तीव्र गैस उछाल। तुरंत बाहर निकलें और चिंगारी से बचें।"
            ],
            "HIGH": [
                "गंभीर गैस उछाल। तुरंत परिसर खाली करें।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "गैस के स्तर में तेज वृद्धि देखी गई है। गैस लाइनों की जाँच करें और वेंटिलेशन करें।",
                "चेतावनी: रासायनिक वाष्प में अचानक उछाल। तुरंत खिड़कियाँ खोलें।"
            ],
            "MODERATE": [
                "तीव्र गैस वृद्धि। हवा का प्रवाह बढ़ाएं।"
            ],
            "HIGH": [
                "गैस स्तर में अचानक उछाल। उपकरणों की जाँच करें।"
            ]
        },
        "HIGH": {
            "LOW": [
                "गैस सांद्रता तेजी से बढ़ रही है। वेंटिलेशन बनाए रखें।"
            ],
            "MODERATE": [
                "बढ़ती हुई गैस रीडिंग। वेंटिलेशन सुनिश्चित करें।"
            ],
            "HIGH": [
                "गैस में तेज बदलाव। सतर्क रहें।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "हल्का गैस उतार-चढ़ाव। सामान्य निगरानी जारी रखें।"
            ],
            "MODERATE": [
                "मामूली गैस भिन्नता। वेंटिलेशन बनाए रखें।"
            ],
            "HIGH": [
                "हल्की गैस वृद्धि। सतर्क रहें।"
            ]
        }
    }
}


GAS_VARIANTS_OR = {
    "CO": {
        "CRITICAL": {
            "LOW": [
                "ଜରୁରୀ ସତର୍କତା: ବିପଜ୍ଜନକ କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ (CO) ସ୍ତର ଚିହ୍ନଟ ହୋଇଛି। ତୁରନ୍ତ ସ୍ଥାନ ଖାଲି କରନ୍ତୁ ଏବଂ ସତେଜ ବାୟୁକୁ ଯାଆନ୍ତୁ।",
                "ବିପଦ ସଙ୍କେତ: କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍‌ର ମାରାତ୍ମକ ସ୍ତର। ବିଳମ୍ବ ନକରି ତୁରନ୍ତ ବାହାରକୁ ଚାଲିଯାଆନ୍ତୁ।",
                "ଆପାତକାଳୀନ ଚେତାବନୀ: ବିଷାକ୍ତ କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ଗ୍ୟାସ୍ ବୃଦ୍ଧି। ବନ୍ଦ କୋଠରୀ ତୁରନ୍ତ ଛାଡ଼ନ୍ତୁ।"
            ],
            "MODERATE": [
                "ଅତି ଗମ୍ଭୀର: କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ବିଷାକ୍ତ ବିପଦ। ତୁରନ୍ତ ଖୋଲା ବାୟୁକୁ ଯାଆନ୍ତୁ।"
            ],
            "HIGH": [
                "ବିପଜ୍ଜନକ କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ଲିକ୍। ତୁରନ୍ତ ନିରାପଦ ସ୍ଥାନକୁ ସ୍ଥାନାନ୍ତର ହୁଅନ୍ତୁ।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ (CO) ସ୍ତର ବିପଦଜନକ ଭାବେ ବୃଦ୍ଧି ପାଇଛି। ବାୟୁ ଚଳାଚଳ ତୁରନ୍ତ ବୃଦ୍ଧି କରନ୍ତୁ।",
                "ଚେତାବନୀ: ଯଥେଷ୍ଟ ପରିମାଣରେ କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ଚିହ୍ନଟ। ହିଟର୍ ଏବଂ ଗ୍ୟାସ୍ ଉପକରଣ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ],
            "MODERATE": [
                "ଉଚ୍ଚ କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ସ୍ତର। ଝରକା କବାଟ ଖୋଲନ୍ତୁ ଏବଂ ବାହାରକୁ ଆସନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗମ୍ଭୀର କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ଉପସ୍ଥିତି। ଗ୍ୟାସ୍ ଉପକରଣ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ]
        },
        "HIGH": {
            "LOW": [
                "କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ସାଧାରଣ ସ୍ତରଠାରୁ ଅଧିକ ରହିଛି। ଭଲ ବାୟୁ ଚଳାଚଳ ସୁନିଶ୍ଚିତ କରନ୍ତୁ।",
                "ସତର୍କତା: ଗ୍ୟାସ୍ ଉପକରଣ କିମ୍ବା ଗାଡ଼ିର ଧୂଆଁ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ],
            "MODERATE": [
                "ବୃଦ୍ଧି ପାଇଥିବା କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍। ଖୋଲା ସ୍ଥାନରେ ରୁହନ୍ତୁ।"
            ],
            "HIGH": [
                "କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ବୃଦ୍ଧି। ଘର ଭିତର ବାୟୁ ଚଳାଚଳ ବଢାନ୍ତୁ।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍‌ରେ ସାମାନ୍ୟ ବୃଦ୍ଧି ଦେଖାଦେଇଛି। ବାୟୁ ଚଳାଚଳ ବଜାୟ ରଖନ୍ତୁ।",
                "ସ୍ୱଳ୍ପ CO ସ୍ତର। ସାଧାରଣ ନଜର ରଖିବାକୁ ପରାମର୍ଶ।"
            ],
            "MODERATE": [
                "କାର୍ବନ ମୋନୋକ୍ସାଇଡ୍ ସାମାନ୍ୟ ବୃଦ୍ଧି। ପବନ ଚଳାଚଳ ରଖନ୍ତୁ।"
            ],
            "HIGH": [
                "ସାମାନ୍ୟ CO ଉପସ୍ଥିତି। ତାଜା ବାୟୁ ଆସିବାକୁ ଦିଅନ୍ତୁ।"
            ]
        }
    },
    "FLAMMABLE": {
        "CRITICAL": {
            "LOW": [
                "ଜରୁରୀ ସତର୍କତା: ଜ୍ୱଳନଶୀଳ କିମ୍ବା ଏଲ୍‌ପିଜି ଗ୍ୟାସ୍ ଲିକ୍ ଚିହ୍ନଟ ହୋଇଛି। ନିଆଁ ଏବଂ ବିସ୍ଫୋରଣର ପ୍ରବଳ ଆଶଙ୍କା। ତୁରନ୍ତ ସ୍ଥାନ ଖାଲି କରନ୍ତୁ।",
                "ବିପଦ: ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍‌ର ଅତ୍ୟଧିକ ସାନ୍ଦ୍ରତା। ବିଦ୍ୟୁତ୍ ସୁଇଚ୍ କିମ୍ବା ଖୋଲା ନିଆଁ ଆଦୌ ବ୍ୟବହାର କରନ୍ତୁ ନାହିଁ।",
                "ଆପାତକାଳୀନ ଚେତାବନୀ: ଗ୍ୟାସ୍ ଲିକ୍‌ରୁ ଅଗ୍ନିକାଣ୍ଡର ବିପଦ। ସୁରକ୍ଷିତ ଦୂରତାରୁ ଜରୁରୀକାଳୀନ ସେବାକୁ ଜଣାନ୍ତୁ।"
            ],
            "MODERATE": [
                "ଆପାତକାଳୀନ ଆଲର୍ଟ: ଗମ୍ଭୀର ଗ୍ୟାସ୍ ଲିକ୍। ତୁରନ୍ତ ବାହାରକୁ ଯାଆନ୍ତୁ ଏବଂ ନିଆଁଠାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"
            ],
            "HIGH": [
                "ବିସ୍ଫୋରଣ ବିପଦ: ଅତ୍ୟଧିକ ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍। ତୁରନ୍ତ ସ୍ଥାନ ଛାଡ଼ନ୍ତୁ।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍ ବୃଦ୍ଧି ପାଇଛି। ସତର୍କ ରୁହନ୍ତୁ ଏବଂ ବାୟୁ ଚଳାଚଳ କରାନ୍ତୁ।",
                "ଚେତାବନୀ: ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍ ଚିହ୍ନଟ। ଗ୍ୟାସ୍ ସିଲିଣ୍ଡର ଏବଂ ପାଇପ୍‌ଲାଇନ୍ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ],
            "MODERATE": [
                "ଉଚ୍ଚ ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍ ସ୍ତର। ସମ୍ଭବ ହେଲେ ମୁଖ୍ୟ ଗ୍ୟାସ୍ ଯୋଗାଣ ବନ୍ଦ କରନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗମ୍ଭୀର ଗ୍ୟାସ୍ ସାନ୍ଦ୍ରତା। କୌଣସି ନିଆଁର ସ୍ପାର୍କରୁ ଦୂରେଇ ରୁହନ୍ତୁ ଏବଂ ବାୟୁ ଚଳାଚଳ କରନ୍ତୁ।"
            ]
        },
        "HIGH": {
            "LOW": [
                "ସାମାନ୍ୟ ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍ ଉପସ୍ଥିତି ଦେଖାଯାଇଛି। ଗ୍ୟାସ୍ ପାଇପ୍ ଯାଞ୍ଚ କରନ୍ତୁ।",
                "ସତର୍କତା: ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍ ସାଧାରଣଠାରୁ ଅଧିକ। ବର୍ଣ୍ଣର୍ ଏବଂ ଭଲ୍ଭ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ],
            "MODERATE": [
                "ବୃଦ୍ଧି ପାଇଥିବା ଗ୍ୟାସ୍ ରିଡିଂ। ଗ୍ୟାସ୍ ସଂଯୋଗ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗ୍ୟାସ୍ ସ୍ତର ବୃଦ୍ଧି ପାଇଛି। ସତର୍କତାର ସହ ନିରୀକ୍ଷଣ କରନ୍ତୁ।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "ସାମାନ୍ୟ ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍ ଦେଖାଯାଇଛି। ବାୟୁ ଚଳାଚଳ ବଜାୟ ରଖନ୍ତୁ।",
                "ସ୍ୱଳ୍ପ ଗ୍ୟାସ୍ ପରିବର୍ତ୍ତନ। ସ୍ଥାନକୁ ଖୋଲା ରଖନ୍ତୁ।"
            ],
            "MODERATE": [
                "କମ୍ ସ୍ତରର ଜ୍ୱଳନଶୀଳ ଗ୍ୟାସ୍। ପ୍ରାକୃତିକ ବାୟୁ ଚଳାଚଳ ସୁନିଶ୍ଚିତ କରନ୍ତୁ।"
            ],
            "HIGH": [
                "ସାମାନ୍ୟ ଗ୍ୟାସ୍ ଉପସ୍ଥିତି। ଉପକରଣ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ]
        }
    },
    "TOXIC_VOC": {
        "CRITICAL": {
            "LOW": [
                "ଜରୁରୀ ସତର୍କତା: ଅତି ବିଷାକ୍ତ ରାସାୟନିକ ବାଷ୍ପ କିମ୍ବା VOC ସ୍ପାଇକ୍ ଚିହ୍ନଟ ହୋଇଛି। ତୁରନ୍ତ ସେହି ସ୍ଥାନରୁ ଦୂରେଇ ଯାଆନ୍ତୁ।",
                "ବିପଦ ସଙ୍କେତ: ବିଷାକ୍ତ ରାସାୟନିକ ବାଷ୍ପ। ମାସ୍କ ବିନା ସେହି ସ୍ଥାନକୁ ଯାଆନ୍ତୁ ନାହିଁ।",
                "ଆପାତକାଳୀନ ଚେତାବନୀ: ବିଷାକ୍ତ ବାଷ୍ପର ତୀବ୍ର ବିସ୍ତାର। ତୁରନ୍ତ ସତେଜ ବାୟୁକୁ ଯାଆନ୍ତୁ।"
            ],
            "MODERATE": [
                "ବିଷାକ୍ତ ରାସାୟନିକ ବିପଦ। ତୁରନ୍ତ ବନ୍ଦ କୋଠରୀ ଛାଡ଼ନ୍ତୁ ଏବଂ ବାୟୁ ଚଳାଚଳ କରାନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗମ୍ଭୀର ରାସାୟନିକ ବାଷ୍ପ ଚେତାବନୀ। ପ୍ରଭାବିତ ଅଞ୍ଚଳ ତୁରନ୍ତ ଖାଲି କରନ୍ତୁ।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "ରାସାୟନିକ ବାଷ୍ପ କିମ୍ବା VOC ପ୍ରଦୂଷଣ ଉଚ୍ଚ ସ୍ତରରେ ଅଛି। ଭଲ ବାୟୁ ଚଳାଚଳ ରଖନ୍ତୁ।",
                "ଚେତାବନୀ: କ୍ଷତିକାରକ ଗ୍ୟାସ୍ ଏବଂ ବାଷ୍ପର ଉଚ୍ଚ ସ୍ତର। ସିଧାସଳଖ ନିଶ୍ୱାସ ନେବାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"
            ],
            "MODERATE": [
                "ବିପଦଜନକ ରାସାୟନିକ ବାଷ୍ପ। ସମସ୍ତ ଝରକା ଖୋଲନ୍ତୁ ଏବଂ ତାଜା ବାୟୁ ଆସିବାକୁ ଦିଅନ୍ତୁ।"
            ],
            "HIGH": [
                "ଉଚ୍ଚ VOC ଜମା ହୋଇଛି। ଖୋଲା ରାସାୟନିକ ଦ୍ରବ୍ୟ ତୁରନ୍ତ ହଟାନ୍ତୁ।"
            ]
        },
        "HIGH": {
            "LOW": [
                "ରାସାୟନିକ ଗନ୍ଧ କିମ୍ବା ବାଷ୍ପ ସ୍ତର ବୃଦ୍ଧି ପାଇଛି। ବାୟୁ ଚଳାଚଳ ବୃଦ୍ଧି କରନ୍ତୁ।",
                "ସତର୍କତା: ରାସାୟନିକ ବାଷ୍ପ ଚିହ୍ନଟ। ବନ୍ଦ ସ୍ଥାନରେ ଅଧିକ ସମୟ ବିତାନ୍ତୁ ନାହିଁ।"
            ],
            "MODERATE": [
                "ବୃଦ୍ଧି ପାଇଥିବା VOC ରିଡିଂ। ଝରକା କବାଟ ଖୋଲା ରଖନ୍ତୁ।"
            ],
            "HIGH": [
                "ସାଧାରଣଠାରୁ ଅଧିକ ରାସାୟନିକ ବାଷ୍ପ। ବାୟୁ ଚଳାଚଳ ଜାରି ରଖନ୍ତୁ।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "ସାମାନ୍ୟ VOC ସାନ୍ଦ୍ରତା ଚିହ୍ନଟ। ବାୟୁ ଚଳାଚଳ ବଜାୟ ରଖନ୍ତୁ।",
                "ସ୍ୱଳ୍ପ ରାସାୟନିକ ଗନ୍ଧ। ତାଜା ବାୟୁ ପାଇଁ ଝରକା ଖୋଲନ୍ତୁ।"
            ],
            "MODERATE": [
                "ମଧ୍ୟମ ରାସାୟନିକ ବାଷ୍ପ। ପବନ ଚଳାଚଳ ଜାରି ରଖନ୍ତୁ।"
            ],
            "HIGH": [
                "ସାମାନ୍ୟ VOC ବୃଦ୍ଧି। ବାୟୁ ଚଳାଚଳ ସୁନିଶ୍ଚିତ କରନ୍ତୁ।"
            ]
        }
    },
    "SMOKE": {
        "CRITICAL": {
            "LOW": [
                "ଜରୁରୀ ସତର୍କତା: ପ୍ରବଳ ଧୂଆଁ ଏବଂ ଜ୍ୱଳନ ବାଷ୍ପ ଚିହ୍ନଟ ହୋଇଛି। ଅଗ୍ନି ବିପଦରୁ ତୁରନ୍ତ ସତର୍କ ରୁହନ୍ତୁ ଏବଂ ବାହାରକୁ ଯାଆନ୍ତୁ।",
                "ବିପଦ: ଅତ୍ୟଧିକ ଧୂଆଁ। ପ୍ରଭାବିତ ଅଞ୍ଚଳ ଖାଲି କରନ୍ତୁ ଏବଂ ଶ୍ୱାସକ୍ରିୟା ସୁରକ୍ଷିତ ରଖନ୍ତୁ।"
            ],
            "MODERATE": [
                "ଗମ୍ଭୀର ଧୂଆଁ ବିପଦ। ତୁରନ୍ତ ଧୂଆଁ ଥିବା ସ୍ଥାନରୁ ବାହାରକୁ ଚାଲିଆସନ୍ତୁ।"
            ],
            "HIGH": [
                "ପ୍ରବଳ ଧୂଆଁ ଉପସ୍ଥିତ। ତୁରନ୍ତ ସୁରକ୍ଷିତ ସ୍ଥାନକୁ ଯାଆନ୍ତୁ।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "ଅଧିକ ଧୂଆଁ ଉପସ୍ଥିତ ଅଛି। ମାସ୍କ କିମ୍ବା ଶ୍ୱାସ ସୁରକ୍ଷା ବ୍ୟବହାର କରନ୍ତୁ ଏବଂ ଉତ୍ସରୁ ଦୂରେଇ ରୁହନ୍ତୁ।",
                "ଚେତାବନୀ: ଜଳିବାର ପ୍ରବଳ ଧୂଆଁ। ଆଖପାଖରେ ନିଆଁର ଉତ୍ସ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ],
            "MODERATE": [
                "ପ୍ରବଳ ଧୂଆଁ ଦେଖାଯାଇଛି। ସତେଜ ବାୟୁ ଥିବା ସ୍ଥାନକୁ ଯାଆନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗମ୍ଭୀର ଧୂଆଁ ସ୍ତର। ମାସ୍କ ବ୍ୟବହାର କରନ୍ତୁ ଏବଂ ବାୟୁ ଚଳାଚଳ କରନ୍ତୁ।"
            ]
        },
        "HIGH": {
            "LOW": [
                "ସ୍ୱଳ୍ପ ଧୂଆଁ ଦେଖାଦେଇଛି। ଜଳୁଥିବା ଉତ୍ସଠାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।",
                "ସତର୍କତା: ଧୂଆଁ ଗନ୍ଧ ଅନୁଭୂତ। ବାହାର ଧୂଆଁରୁ ଘର ଭିତର ବାୟୁକୁ ରକ୍ଷା କରନ୍ତୁ।"
            ],
            "MODERATE": [
                "ବାୟୁରେ ଧୂଆଁ ଦେଖାଯାଉଛି। ଧୂଆଁ ଥିବା ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"
            ],
            "HIGH": [
                "ବୃଦ୍ଧି ପାଇଥିବା ଧୂଆଁ ସ୍ତର। ସମ୍ବେଦନଶୀଳ ବ୍ୟକ୍ତି ସତର୍କ ରୁହନ୍ତୁ।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "ସାମାନ୍ୟ ଧୂଆଁ ଚିହ୍ନଟ ହୋଇଛି। ଜଳୁଥିବା ଉତ୍ସଠାରୁ ଦୂରତା ବଜାୟ ରଖନ୍ତୁ।"
            ],
            "MODERATE": [
                "ସ୍ୱଳ୍ପ ଧୂଆଁ ଉପସ୍ଥିତ। ସିଧାସଳଖ ସଂସ୍ପର୍ଶରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"
            ],
            "HIGH": [
                "ସାମାନ୍ୟ ଧୂଆଁ ବୃଦ୍ଧି। ବାୟୁ ଚଳାଚଳ ରଖନ୍ତୁ।"
            ]
        }
    },
    "GAS_SPIKE": {
        "CRITICAL": {
            "LOW": [
                "ଜରୁରୀ ସତର୍କତା: ହଠାତ୍ ତୀବ୍ର ଗ୍ୟାସ୍ ବୃଦ୍ଧି ଚିହ୍ନଟ ହୋଇଛି। ତୁରନ୍ତ ସ୍ଥାନ ଖାଲି କରନ୍ତୁ।",
                "ଆପାତକାଳୀନ ଆଲର୍ଟ: ଗ୍ୟାସ୍ ସାନ୍ଦ୍ରତାରେ ହଠାତ୍ ଅତ୍ୟଧିକ ବୃଦ୍ଧି। ତୁରନ୍ତ ସତେଜ ବାୟୁକୁ ଯାଆନ୍ତୁ।"
            ],
            "MODERATE": [
                "ତୀବ୍ର ଗ୍ୟାସ୍ ବୃଦ୍ଧି। ତୁରନ୍ତ ବାହାରକୁ ଯାଆନ୍ତୁ ଏବଂ ନିଆଁରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗମ୍ଭୀର ଗ୍ୟାସ୍ ସ୍ପାଇକ୍। ତୁରନ୍ତ ସ୍ଥାନ ଛାଡ଼ନ୍ତୁ।"
            ]
        },
        "SEVERE": {
            "LOW": [
                "ଗ୍ୟାସ୍ ସ୍ତରରେ ଦ୍ରୁତ ବୃଦ୍ଧି ଦେଖାଯାଇଛି। ଗ୍ୟାସ୍ ଲାଇନ୍ ଯାଞ୍ଚ କରନ୍ତୁ ଏବଂ ବାୟୁ ଚଳାଚଳ କରାନ୍ତୁ।",
                "ଚେତାବନୀ: ରାସାୟନିକ ବାଷ୍ପରେ ହଠାତ୍ ବୃଦ୍ଧି। ତୁରନ୍ତ ଝରକା ଖୋଲନ୍ତୁ।"
            ],
            "MODERATE": [
                "ଦ୍ରୁତ ଗ୍ୟାସ୍ ବୃଦ୍ଧି। ପବନ ଚଳାଚଳ ବଢାନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗ୍ୟାସ୍ ସ୍ତରରେ ହଠାତ୍ ବୃଦ୍ଧି। ଉପକରଣ ଯାଞ୍ଚ କରନ୍ତୁ।"
            ]
        },
        "HIGH": {
            "LOW": [
                "ଗ୍ୟାସ୍ ସାନ୍ଦ୍ରତା ଦ୍ରୁତ ଗତିରେ ବୃଦ୍ଧି ପାଉଛି। ବାୟୁ ଚଳାଚଳ ବଜାୟ ରଖନ୍ତୁ।"
            ],
            "MODERATE": [
                "ବୃଦ୍ଧି ପାଉଥିବା ଗ୍ୟାସ୍ ରିଡିଂ। ବାୟୁ ଚଳାଚଳ ସୁନିଶ୍ଚିତ କରନ୍ତୁ।"
            ],
            "HIGH": [
                "ଗ୍ୟାସ୍‌ରେ ଦ୍ରୁତ ପରିବର୍ତ୍ତନ। ସତର୍କ ରୁହନ୍ତୁ।"
            ]
        },
        "MODERATE": {
            "LOW": [
                "ସାମାନ୍ୟ ଗ୍ୟାସ୍ ପରିବର୍ତ୍ତନ। ସାଧାରଣ ନଜର ରଖନ୍ତୁ।"
            ],
            "MODERATE": [
                "ସ୍ୱଳ୍ପ ଗ୍ୟାସ୍ ପରିବର୍ତ୍ତନ। ବାୟୁ ଚଳାଚଳ ବଜାୟ ରଖନ୍ତୁ।"
            ],
            "HIGH": [
                "ସାମାନ୍ୟ ଗ୍ୟାସ୍ ବୃଦ୍ଧି। ସତର୍କ ରୁହନ୍ତୁ।"
            ]
        }
    }
}


# =====================================================================
# Localized AQI Variants (Hindi & Odia)
# =====================================================================

AQI_VARIANTS_HI = {
    "NORMAL": {
        "LOW": [
            "हवा की गुणवत्ता बहुत अच्छी है। बाहर ताज़ी हवा का आनंद लें।",
            "वायु स्वच्छ और सामान्य है। बाहर समय बिताने के लिए अच्छा समय है।",
            "हवा साफ और आरामदायक लग रही है। बाहर जाने में कोई समस्या नहीं है।",
            "हवा की स्थिति सामान्य है। अपने दैनिक कार्य जारी रखें।"
        ],
        "MODERATE": [
            "वायु गुणवत्ता अच्छी श्रेणी में है। बाहरी गतिविधियाँ सुरक्षित हैं।",
            "हवा साफ और आरामदायक है। बाहर जाने का आनंद ले सकते हैं।",
            "हवा में कोई चिंताजनक बात नहीं है। सामान्य दिनचर्या जारी रखें।"
        ],
        "HIGH": [
            "वायु गुणवत्ता उत्कृष्ट है। बाहर घूमने का बेहतरीन समय है।",
            "हवा बहुत साफ और ताज़ा है। बाहर की गतिविधियों का आनंद लें।"
        ],
    },
    "MODERATE": {
        "LOW": [
            "वायु गुणवत्ता थोड़ी बदलने लगी है। ताज़ी हवा ठीक है, पर अधिक समय बाहर न रहें।",
            "हवा थोड़ी प्रदूषित है। खुले और हवादार स्थानों को प्राथमिकता दें।",
            "हल्का प्रदूषण मौजूद है। अपने आस-पास अच्छा वेंटिलेशन रखें।"
        ],
        "MODERATE": [
            "वायु गुणवत्ता थोड़ी प्रदूषित है। बाहर लंबे समय तक रहने पर ब्रेक लें।",
            "हवा मध्यम रूप से प्रदूषित है। हवादार जगहें बेहतर रहेंगी।",
            "कुछ प्रदूषण मौजूद है। लंबे समय तक बाहर रहने से बचें।"
        ],
        "HIGH": [
            "वायु प्रदूषण ध्यान देने योग्य है। लंबी बाहरी गतिविधियों को सीमित करें।",
            "हवा काफी प्रदूषित है। बाहर रहने पर नियमित अंतराल लें।",
            "प्रदूषण बढ़ रहा है। व्यस्त सड़कों के पास अनावश्यक समय न बिताएं।"
        ],
    },
    "HIGH": {
        "LOW": [
            "वायु प्रदूषण बढ़ा हुआ है। बाहरी गतिविधियों को हल्का रखें।",
            "हवा भारी लग रही है। लंबे समय तक बाहर रहने से बचें।",
            "प्रदूषण सामान्य से अधिक है। बाहर होने पर ब्रेक लें।"
        ],
        "MODERATE": [
            "वायु प्रदूषण काफी अधिक है। लंबी बाहरी गतिविधियों को सीमित करें।",
            "हवा स्पष्ट रूप से प्रदूषित है। संवेदनशील लोगों को अतिरिक्त सावधानी बरतनी चाहिए।",
            "प्रदूषण अधिक हो रहा है। अधिक समय घर के अंदर बिताने पर विचार करें।"
        ],
        "HIGH": [
            "वायु प्रदूषण उच्च स्तर पर है। बाहर कम समय बिताना ही बेहतर है।",
            "हवा काफी प्रदूषित है। जब संभव हो घर के अंदर ही रहें।",
            "वायु गुणवत्ता खराब है। अभी कठिन बाहरी व्यायाम से बचें।"
        ],
    },
    "SEVERE": {
        "LOW": [
            "वायु गुणवत्ता बहुत खराब है। बाहर का समय सीमित करें।",
            "हवा काफी प्रदूषित है। घर के अंदर रहना अधिक सुरक्षित है।",
            "प्रदूषण गंभीर है। बाहरी गतिविधियाँ न्यूनतम रखें।"
        ],
        "MODERATE": [
            "वायु गुणवत्ता बहुत खराब है। कृपया बाहर का समय कम रखें।",
            "हवा भारी प्रदूषित है। इनडोर गतिविधियाँ ही बेहतर विकल्प हैं।",
            "प्रदूषण काफी बढ़ चुका है। अनावश्यक बाहरी संपर्क से बचें।"
        ],
        "HIGH": [
            "वायु गुणवत्ता बहुत खराब है। यदि संभव हो तो बाहरी गतिविधियों से पूरी तरह बचें।",
            "हवा अत्यधिक प्रदूषित है। घर के अंदर रहना ही सबसे अच्छा है।",
            "गंभीर प्रदूषण स्तर। घर के अंदर रहें और खिड़कियाँ बंद रखें।"
        ],
    },
    "CRITICAL": {
        "LOW": [
            "वायु गुणवत्ता गंभीर स्तर पर पहुँच गई है। कृपया घर के अंदर रहें।",
            "हवा खतरनाक रूप से प्रदूषित है। अभी बाहर जाने से बचें।",
            "प्रदूषण गंभीर स्तर पर है। बाहरी संपर्क न्यूनतम रखें।"
        ],
        "MODERATE": [
            "वायु गुणवत्ता अत्यधिक खराब है। कृपया घर के अंदर रहें।",
            "हवा अत्यधिक प्रदूषित है। बाहर जाने से बिल्कुल बचें।",
            "प्रदूषण गंभीर स्तर पर पहुँच चुका है। दरवाजे और खिड़कियाँ बंद रखें।"
        ],
        "HIGH": [
            "वायु गुणवत्ता अत्यंत गंभीर स्तर पर है। बाहर जाने से बिल्कुल बचें।",
            "हवा खतरनाक रूप से प्रदूषित है। कृपया घर के अंदर ही रहें।",
            "प्रदूषण आपातकालीन स्तर पर है। जब तक स्थिति में सुधार न हो, बाहर न निकलें।"
        ],
    },
}

AQI_VARIANTS_OR = {
    "NORMAL": {
        "LOW": [
            "ବାୟୁ ମାନ ଉତ୍ତମ ଅଛି। ବାହାରକୁ ଯାଇ ଭ୍ରମଣ କରିବା ପାଇଁ ଅନୁକୂଳ ସମୟ।",
            "ବାୟୁ ସ୍ୱଚ୍ଛ ଏବଂ ସୁରକ୍ଷିତ ରହିଛି। ଆପଣଙ୍କର ସାଧାରଣ କାର୍ଯ୍ୟ ଜାରି ରଖନ୍ତୁ।",
            "ବାୟୁ ମାନ ଆରାମଦାୟକ ଅଛି। ବାହାର ପରିବେଶକୁ ଉପଭୋଗ କରନ୍ତୁ।"
        ],
        "MODERATE": [
            "ବାୟୁ ମାନ ସୁସ୍ଥ ସ୍ତରରେ ରହିଛି। ବାହାର କାର୍ଯ୍ୟକଳାପ ସୁରକ୍ଷିତ ଅଟେ।",
            "ବାୟୁ ସଫା ରହିଛି। ସାଧାରଣ ଦୈନନ୍ଦିନ କାର୍ଯ୍ୟ କରିପାରିବେ।"
        ],
        "HIGH": [
            "ବାୟୁ ମାନ ଅତି ଉତ୍କୃଷ୍ଟ ଅଛି। ବାହାରେ ସମୟ ବିତାଇବା ପାଇଁ ଉତ୍ତମ ଦିନ।"
        ],
    },
    "MODERATE": {
        "LOW": [
            "ବାୟୁର ମାନ ସାମାନ୍ୟ ପ୍ରଭାବିତ ହୋଇଛି। ବାହାରେ ଅଧିକ ସମୟ ବିତାଇବା ବେଳେ ସତର୍କ ରୁହନ୍ତୁ।",
            "ସ୍ୱଳ୍ପ ପ୍ରଦୂଷଣ ଅନୁଭୂତ ହେଉଛି। ଖୋଲା ଏବଂ ବାୟୁ ଚଳାଚଳ ଥିବା ସ୍ଥାନ ବାଛନ୍ତୁ।"
        ],
        "MODERATE": [
            "ବାୟୁ ସାମାନ୍ୟ ପ୍ରଦୂଷିତ ଅଛି। ବାହାରେ ଅଧିକ ସମୟ ରହିଲେ ବିରତି ନିଅନ୍ତୁ।",
            "ମଧ୍ୟମ ଧରଣର ପ୍ରଦୂଷଣ ରହିଛି। ଭଲ ବାୟୁ ଚଳାଚଳ ଥିବା ସ୍ଥାନକୁ ପ୍ରାଥମିକତା ଦିଅନ୍ତୁ।"
        ],
        "HIGH": [
            "ବାୟୁ ପ୍ରଦୂଷଣ ବୃଦ୍ଧି ପାଉଛି। ବାହାରେ ଅଧିକ ସମୟ ବିତାଇବା ଠାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।",
            "ବ୍ୟସ୍ତବହୁଳ ରାସ୍ତା ନିକଟରେ ଅନାବଶ୍ୟକ ସମୟ ବିତାନ୍ତୁ ନାହିଁ।"
        ],
    },
    "HIGH": {
        "LOW": [
            "ବାୟୁ ପ୍ରଦୂଷଣ ବୃଦ୍ଧି ପାଇଛି। ବାହାର କାର୍ଯ୍ୟକଳାପ ସୀମିତ ରଖନ୍ତୁ।",
            "ହଠାତ୍ ପ୍ରଦୂଷଣ ବଢିଛି। ବାହାରେ ଅଧିକ ସମୟ ରହିବା କମାନ୍ତୁ।"
        ],
        "MODERATE": [
            "ବାୟୁ ପ୍ରଦୂଷଣ ବେଶ୍ ଅଧିକ ରହିଛି। ଲମ୍ବା ସମୟ ବାହାରେ ରହିବା କମାନ୍ତୁ।",
            "ସମ୍ବେଦନଶୀଳ ବ୍ୟକ୍ତିମାନେ ବିଶେଷ ସତର୍କତା ଅବଲମ୍ବନ କରନ୍ତୁ।"
        ],
        "HIGH": [
            "ବାୟୁ ପ୍ରଦୂଷଣ ଉଚ୍ଚ ସ୍ତରରେ ଅଛି। ବାହାରେ ଅଧିକ ସମୟ ବିତାଇବା ଠାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।",
            "ବାୟୁ ଖରାପ ଅଛି। ବର୍ତ୍ତମାନ କଠିନ ବ୍ୟାୟାମରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"
        ],
    },
    "SEVERE": {
        "LOW": [
            "ବାୟୁ ଗୁଣବତ୍ତା ଅତି ଖରାପ ସ୍ତରରେ ଅଛି। ବାହାରେ ସମୟ ବିତାଇବା କମାନ୍ତୁ।",
            "ବାୟୁ ବେଶ୍ ପ୍ରଦୂଷିତ। ଘର ଭିତରେ ରହିବା ଅଧିକ ନିରାପଦ।"
        ],
        "MODERATE": [
            "ବାୟୁ ଗୁଣବତ୍ତା ଅତି ଖରାପ। ଦୟାକରି ବାହାର କାର୍ଯ୍ୟକଳାପ ସୀମିତ ରଖନ୍ତୁ।",
            "ଅନାବଶ୍ୟକ ଭାବେ ବାହାରକୁ ଯାଆନ୍ତୁ ନାହିଁ।"
        ],
        "HIGH": [
            "ବାୟୁ ଗୁଣବତ୍ତା ଅତି ଖରାପ ସ୍ତରରେ ଅଛି। ସମ୍ଭବ ହେଲେ ବାହାର କାର୍ଯ୍ୟକଳାପ ବନ୍ଦ ରଖନ୍ତୁ।",
            "ଗମ୍ଭୀର ପ୍ରଦୂଷଣ ସ୍ଥିତି। ଘର ଭିତରେ ରୁହନ୍ତୁ ଏବଂ କବାଟ ଝରକା ବନ୍ଦ ରଖନ୍ତୁ।"
        ],
    },
    "CRITICAL": {
        "LOW": [
            "ବାୟୁ ଗୁଣବତ୍ତା ଗମ୍ଭୀର ସ୍ତରରେ ପହଞ୍ଚିଛି। ଦୟାକରି ଘର ଭିତରେ ରୁହନ୍ତୁ।",
            "ବାୟୁ ବିପଦଜନକ ଭାବେ ପ୍ରଦୂଷିତ। ବର୍ତ୍ତମାନ ବାହାରକୁ ଯିବା ବନ୍ଦ କରନ୍ତୁ।"
        ],
        "MODERATE": [
            "ବାୟୁ ଗୁଣବତ୍ତା ଅତ୍ୟନ୍ତ ଖରାପ। ବାହାରକୁ ଆଦୌ ଯାଆନ୍ତୁ ନାହିଁ।",
            "ପ୍ରଦୂଷଣ ଗମ୍ଭୀର ସ୍ତରରେ ଅଛି। ଝରକା କବାଟ ବନ୍ଦ ରଖନ୍ତୁ।"
        ],
        "HIGH": [
            "ବାୟୁ ଗୁଣବତ୍ତା ବିପଜ୍ଜନକ ସ୍ତରରେ ପହଞ୍ଚିଛି। ବାହାରକୁ ଆଦୌ ଯାଆନ୍ତୁ ନାହିଁ।",
            "ଅତି ଗମ୍ଭୀର ପ୍ରଦୂଷଣ। ଘର ଭିତରେ ରୁହନ୍ତୁ ଏବଂ ଉପଯୁକ୍ତ ମାସ୍କ ବ୍ୟବହାର କରନ୍ତୁ।"
        ],
    },
}


# =====================================================================
# Localized Source Variants (Hindi & Odia)
# =====================================================================

SOURCE_VARIANTS_HI = {
    "TRAFFIC": {
        "LOW": ["वाहनों का कुछ प्रदूषण मौजूद हो सकता है। व्यस्त सड़कों से बचें।"],
        "MODERATE": ["वाहनों का उत्सर्जन वायु गुणवत्ता को प्रभावित कर रहा है। शांत मार्ग चुनें।"],
        "HIGH": ["सड़क यातायात से भारी प्रदूषण हो रहा है। व्यस्त सड़कों से दूर रहें।"]
    },
    "HEAVY_DUST": {
        "LOW": ["हवा में कुछ धूल मौजूद हो सकती है। संवेदनशील लोग ध्यान दें।"],
        "MODERATE": ["धूल का प्रदूषण ध्यान देने योग्य है। हवादार क्षेत्रों में रहें।"],
        "HIGH": ["भारी धूल भरी हवा। धूल भरे क्षेत्रों से बचें और मास्क पहनें।"]
    },
    "CONSTRUCTION": {
        "LOW": ["निर्माण कार्य से संबंधित कुछ धूल मौजूद हो सकती है।"],
        "MODERATE": ["निर्माण गतिविधि से धूल बढ़ रही है। उस क्षेत्र से दूर रहें।"],
        "HIGH": ["सक्रिय निर्माण स्थलों के पास भारी धूल। सुरक्षात्मक उपाय करें।"]
    },
    "COMBUSTION": {
        "LOW": ["दहन या धुएँ का कुछ प्रभाव दिखाई दे रहा है।"],
        "MODERATE": ["धुएँ का प्रदूषण बढ़ रहा है। खराब वेंटिलेशन वाले क्षेत्रों से बचें।"],
        "HIGH": ["दहन और धुएँ का गंभीर प्रदूषण। धुएँ से दूर रहें।"]
    },
    "BIOMASS_OR_WASTE_BURNING": {
        "LOW": ["बायोमास या कचरा जलने का धुआँ आसपास हो सकता है।"],
        "MODERATE": ["कचरा या बायोमास जलने से धुआँ फैल रहा है। इनडोर हवा को सुरक्षित रखें।"],
        "HIGH": ["बायोमास जलने से भारी धुआँ। धुएँ के सीधे संपर्क से बचें।"]
    },
    "INDUSTRIAL": {
        "LOW": ["औद्योगिक उत्सर्जन का हल्का प्रभाव संभव है।"],
        "MODERATE": ["औद्योगिक क्षेत्र से निकलने वाला धुआँ वायु को प्रभावित कर रहा है।"],
        "HIGH": ["औद्योगिक क्षेत्रों के पास प्रदूषण काफी अधिक है। संपर्क सीमित करें।"]
    },
    "INDOOR_ACTIVITY": {
        "LOW": ["इनडोर गतिविधियों से हवा थोड़ी प्रभावित हो सकती है।"],
        "MODERATE": ["इनडोर वेंटिलेशन में सुधार की आवश्यकता है।"],
        "HIGH": ["इनडोर प्रदूषण बढ़ गया है। खिड़कियाँ खोलें और वेंटिलेशन करें।"]
    },
    "MIXED": {
        "LOW": ["प्रदूषण के कई मिले-जुले स्रोत मौजूद हो सकते हैं।"],
        "MODERATE": ["मिले-जुले स्रोतों से प्रदूषण बढ़ रहा है। सावधानी बरतें।"],
        "HIGH": ["विभिन्न स्रोतों से व्यापक प्रदूषण। सामान्य सावधानी बरतें।"]
    },
    "UNKNOWN": {
        "LOW": ["प्रदूषण के स्रोत का स्पष्ट पता नहीं है। सामान्य सावधानी बरतें।"],
        "MODERATE": ["अज्ञात स्रोत से प्रदूषण बढ़ रहा है। सामान्य सावधानियाँ बरतें।"],
        "HIGH": ["प्रदूषण स्रोत की पुष्टि नहीं हुई है। सतर्क रहें।"]
    }
}

SOURCE_VARIANTS_OR = {
    "TRAFFIC": {
        "LOW": ["ଗାଡ଼ି ମୋଟରରୁ କିଛି ପ୍ରଦୂଷଣ ହୋଇପାରେ। ବ୍ୟସ୍ତବହୁଳ ରାସ୍ତାଠାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"],
        "MODERATE": ["ଯାନବାହାନର ନିର୍ଗମନ ବାୟୁକୁ ପ୍ରଭାବିତ କରୁଛି। ଶାନ୍ତ ରାସ୍ତା ବାଛନ୍ତୁ।"],
        "HIGH": ["ରାସ୍ତା ଟ୍ରାଫିକ୍‌ରୁ ପ୍ରବଳ ପ୍ରଦୂଷଣ। ବ୍ୟସ୍ତବହୁଳ ରାସ୍ତା ନିକଟକୁ ଯାଆନ୍ତୁ ନାହିଁ।"]
    },
    "HEAVY_DUST": {
        "LOW": ["ବାୟୁରେ କିଛି ଧୂଳିକଣା ଉପସ୍ଥିତ ଅଛି।"],
        "MODERATE": ["ଧୂଳି ପ୍ରଦୂଷଣ ସ୍ପଷ୍ଟ ଜଣାପଡୁଛି। ଧୂଳିଆ ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"],
        "HIGH": ["ପ୍ରବଳ ଧୂଳିଝଡ଼ ସ୍ଥିତି। ଧୂଳି ଉଡୁଥିବା ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ ଏବଂ ମାସ୍କ ବ୍ୟବହାର କରନ୍ତୁ।"]
    },
    "CONSTRUCTION": {
        "LOW": ["ନିର୍ମାଣ କାର୍ଯ୍ୟରୁ କିଛି ଧୂଳି ହୋଇପାରେ।"],
        "MODERATE": ["ନିର୍ମାଣ କାର୍ଯ୍ୟ ଯୋଗୁଁ ଧୂଳି ବଢୁଛି। ସତର୍କ ରୁହନ୍ତୁ।"],
        "HIGH": ["ନିର୍ମାଣ କାର୍ଯ୍ୟ ଚାଲିଥିବା ସ୍ଥାନରୁ ପ୍ରବଳ ଧୂଳି। ସେହି ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"]
    },
    "COMBUSTION": {
        "LOW": ["କିଛି ଜଳିବା କିମ୍ବା ଧୂଆଁର ପ୍ରଭାବ ଦେଖାଯାଉଛି।"],
        "MODERATE": ["ଧୂଆଁ ପ୍ରଦୂଷଣ ବଢୁଛି। କମ୍ ବାୟୁ ଚଳାଚଳ ଥିବା ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"],
        "HIGH": ["ପ୍ରବଳ ଧୂଆଁ ପ୍ରଦୂଷଣ। ଧୂଆଁରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"]
    },
    "BIOMASS_OR_WASTE_BURNING": {
        "LOW": ["ଅଳିଆ ଆବର୍ଜନା ଜଳିବାର ଧୂଆଁ ଆଖପାଖରେ ହୋଇପାରେ।"],
        "MODERATE": ["ଆବର୍ଜନା କିମ୍ବା କାଠ ଜଳିବାରୁ ଧୂଆଁ ବ୍ୟାପୁଛି। ଘର ଭିତର ବାୟୁକୁ ସୁରକ୍ଷିତ ରଖନ୍ତୁ।"],
        "HIGH": ["ଆବର୍ଜନା ଜଳିବାରୁ ପ୍ରବଳ ଧୂଆଁ। ଧୂଆଁ ସଂସ୍ପର୍ଶରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"]
    },
    "INDUSTRIAL": {
        "LOW": ["ଶିଳ୍ପାଞ୍ଚଳ ନିର୍ଗମନର ସାମାନ୍ୟ ପ୍ରଭାବ ସମ୍ଭବ।"],
        "MODERATE": ["କାରଖାନାରୁ ନିର୍ଗତ ଧୂଆଁ ବାୟୁକୁ ପ୍ରଭାବିତ କରୁଛି।"],
        "HIGH": ["ଶିଳ୍ପାଞ୍ଚଳ ନିକଟରେ ଅଧିକ ପ୍ରଦୂଷଣ। ସେଠାରେ ରହିବା ସମୟ କମାନ୍ତୁ।"]
    },
    "INDOOR_ACTIVITY": {
        "LOW": ["ଘର ଭିତର କାର୍ଯ୍ୟକଳାପ ଯୋଗୁଁ ବାୟୁ ସାମାନ୍ୟ ପ୍ରଭାବିତ ହୋଇପାରେ।"],
        "MODERATE": ["ଘର ଭିତରେ ବାୟୁ ଚଳାଚଳ ବୃଦ୍ଧି କରିବା ଆବଶ୍ୟକ।"],
        "HIGH": ["ଘର ଭିତର ପ୍ରଦୂଷଣ ବୃଦ୍ଧି ପାଇଛି। ଝରକା ଖୋଲନ୍ତୁ ଏବଂ ବାୟୁ ଚଳାଚଳ କରାନ୍ତୁ।"]
    },
    "MIXED": {
        "LOW": ["ଏକାଧିକ ମିଶ୍ରିତ ଉତ୍ସରୁ ପ୍ରଦୂଷଣ ହୋଇପାରେ।"],
        "MODERATE": ["ମିଶ୍ରିତ ଉତ୍ସରୁ ପ୍ରଦୂଷଣ ବଢୁଛି। ସତର୍କତା ଅବଲମ୍ବନ କରନ୍ତୁ।"],
        "HIGH": ["ବିଭିନ୍ନ ଉତ୍ସରୁ ବ୍ୟାପକ ପ୍ରଦୂଷଣ। ସାଧାରଣ ସତର୍କତା ଅବଲମ୍ବନ କରନ୍ତୁ।"]
    },
    "UNKNOWN": {
        "LOW": ["ପ୍ରଦୂଷଣର ନିର୍ଦ୍ଦିଷ୍ଟ ଉତ୍ସ ଅସ୍ପଷ୍ଟ। ସାଧାରଣ ସତର୍କତା ବଜାୟ ରଖନ୍ତୁ।"],
        "MODERATE": ["ଅଜ୍ଞାତ ଉତ୍ସରୁ ପ୍ରଦୂଷଣ ବୃଦ୍ଧି ପାଉଛି। ସାଧାରଣ ସତର୍କତା ଅବଲମ୍ବନ କରନ୍ତୁ।"],
        "HIGH": ["ପ୍ରଦୂଷଣ ଉତ୍ସ ନିଶ୍ଚିତ ହୋଇନାହିଁ। ସତର୍କ ରୁହନ୍ତୁ।"]
    }
}


# =====================================================================
# Localized Forecast Variants (Hindi & Odia)
# =====================================================================

FORECAST_VARIANTS_HI = {
    "RISING": {
        "LOW": ["पूर्वानुमान के अनुसार आने वाले घंटों में प्रदूषण बढ़ सकता है।"],
        "MODERATE": ["आने वाले समय में वायु प्रदूषण और बढ़ने की संभावना है।"],
        "HIGH": ["प्रदूषण में भारी वृद्धि का अनुमान है। पहले से आवश्यक सावधानी बरतें।"]
    },
    "FALLING": {
        "LOW": ["पूर्वानुमान के अनुसार वायु गुणवत्ता में सुधार होने की संभावना है।"],
        "MODERATE": ["आने वाले घंटों में प्रदूषण कम होने की उम्मीद है।"],
        "HIGH": ["हवा की गुणवत्ता में उल्लेखनीय सुधार होने की संभावना है।"]
    },
    "STABLE": {
        "LOW": ["वायु गुणवत्ता वर्तमान स्तर पर स्थिर रहने की संभावना है।"],
        "MODERATE": ["प्रदूषण के स्तर में कोई बड़ा बदलाव अपेक्षित नहीं है।"],
        "HIGH": ["आने वाले समय में हवा की स्थिति स्थिर रहने का अनुमान है।"]
    }
}

FORECAST_VARIANTS_OR = {
    "RISING": {
        "LOW": ["ପୂର୍ବାନୁମାନ ଅନୁସାରେ ଆଗାମୀ ଘଣ୍ଟାଗୁଡ଼ିକରେ ପ୍ରଦୂଷଣ ବୃଦ୍ଧି ପାଇପାରେ।"],
        "MODERATE": ["ଆଗାମୀ ସମୟରେ ବାୟୁ ପ୍ରଦୂଷଣ ଆହୁରି ବଢିବାର ସମ୍ଭାବନା ଅଛି।"],
        "HIGH": ["ପ୍ରଦୂଷଣ ବହୁତ ବଢିବାର ଅନୁମାନ କରାଯାଉଛି। ପୂର୍ବରୁ ସତର୍କ ରୁହନ୍ତୁ।"]
    },
    "FALLING": {
        "LOW": ["ପୂର୍ବାନୁମାନ ଅନୁସାରେ ବାୟୁ ଗୁଣବତ୍ତାରେ ସୁଧାର ଆସିବାର ସମ୍ଭାବନା ଅଛି।"],
        "MODERATE": ["ଆଗାମୀ ସମୟରେ ପ୍ରଦୂଷଣ କମିବାର ଆଶା କରାଯାଉଛି।"],
        "HIGH": ["ବାୟୁର ମାନରେ ଉଲ୍ଲେଖନୀୟ ଉନ୍ନତି ହେବାର ସମ୍ଭାବନା ରହିଛି।"]
    },
    "STABLE": {
        "LOW": ["ବାୟୁ ମାନ ବର୍ତ୍ତମାନ ସ୍ତରରେ ସ୍ଥିର ରହିବାର ସମ୍ଭାବନା ଅଛି।"],
        "MODERATE": ["ପ୍ରଦୂଷଣ ସ୍ତରରେ କୌଣସି ବଡ଼ ପରିବର୍ତ୍ତନର ଆଶଙ୍କା ନାହିଁ।"],
        "HIGH": ["ଆଗାମୀ ସମୟରେ ବାୟୁ ସ୍ଥିତି ସ୍ଥିର ରହିବାର ଅନୁମାନ।"]
    }
}


# =====================================================================
# Localized Weather Variants (Hindi & Odia)
# =====================================================================

WEATHER_VARIANTS_HI = {
    "HOT_HUMID": {
        "LOW": ["मौसम गर्म और उमस भरा है। पर्याप्त पानी पिएं और छाया में रहें।"],
        "MODERATE": ["मौसम काफी गर्म और उमस भरा है। हाइड्रेटेड रहें और ठंडा रहें।"],
        "HIGH": ["भीषण गर्मी और उमस। धूप से बचें, प्रचुर पानी पिएं और आराम करें।"]
    },
    "HOT": {
        "LOW": ["मौसम गर्म है। पर्याप्त मात्रा में पानी पिएं।"],
        "MODERATE": ["मौसम काफी गर्म है। सीधी धूप से बचें और हाइड्रेटेड रहें।"],
        "HIGH": ["तेज गर्मी है। बाहर निकलने पर सावधानी बरतें और खूब पानी पिएं।"]
    },
    "COLD_DRY": {
        "LOW": ["मौसम ठंडा और सूखा है। गर्म कपड़े पहनें और पानी पीते रहें।"],
        "MODERATE": ["काफी ठंड और शुष्क मौसम है। गर्म कपड़े पहनें।"],
        "HIGH": ["कड़ाके की ठंड और शुष्क हवा। पर्याप्त गर्म कपड़े पहनें।"]
    },
    "COLD": {
        "LOW": ["मौसम थोड़ा ठंडा है। हल्का गर्म कपड़ा पहनें।"],
        "MODERATE": ["मौसम में ठंडक है। गर्म कपड़े साथ रखें।"],
        "HIGH": ["काफी ठंड है। बाहर जाने से पहले गर्म कपड़े अवश्य पहनें।"]
    },
    "HUMID": {
        "LOW": ["हवा में थोड़ी उमस है। हल्के और आरामदायक कपड़े पहनें।"],
        "MODERATE": ["उमस काफी महसूस हो रही है। पानी पीते रहें और छाया में रहें।"],
        "HIGH": ["हवा में उमस बहुत अधिक है। नियमित रूप से पानी पिएं।"]
    },
    "DRY": {
        "LOW": ["हवा थोड़ी शुष्क है। पर्याप्त पानी पिएं।"],
        "MODERATE": ["मौसम काफी शुष्क है। नियमित अंतराल पर पानी पीते रहें।"],
        "HIGH": ["हवा बहुत शुष्क है। खूब पानी पिएं और हाइड्रेटेड रहें।"]
    },
    "COMFORTABLE": {
        "LOW": ["मौसम सुखद और अनुकूल है। अपने दिन का आनंद लें।"],
        "MODERATE": ["मौसम बहुत आरामदायक और सुहावना है। बाहर घूमने के लिए अच्छा दिन है।"],
        "HIGH": ["मौसम एकदम सही और सुहावना है। बाहर की गतिविधियों का आनंद लें।"]
    }
}

WEATHER_VARIANTS_OR = {
    "HOT_HUMID": {
        "LOW": ["ପାଗ ଗରମ ଏବଂ ଆର୍ଦ୍ର ରହିଛି। ପ୍ରଚୁର ପାଣି ପିଅନ୍ତୁ ଏବଂ ଛାଇରେ ରୁହନ୍ତୁ।"],
        "MODERATE": ["ପାଗ ବହୁତ ଗରମ ଏବଂ ଗୁଳୁଗୁଳି ଅଛି। ପ୍ରଚୁର ପାଣି ପିଇବା ସହ ଥଣ୍ଡା ରୁହନ୍ତୁ।"],
        "HIGH": ["ଭୀଷଣ ଗରମ ଏବଂ ଗୁଳୁଗୁଳି। ଖରାରୁ ଦୂରେଇ ରୁହନ୍ତୁ ଏବଂ ହାଇଡ୍ରେଟେଡ୍ ରୁହନ୍ତୁ।"]
    },
    "HOT": {
        "LOW": ["ପାଗ ଗରମ ଅଛି। ଯଥେଷ୍ଟ ପାଣି ପିଅନ୍ତୁ।"],
        "MODERATE": ["ପାଗ ବେଶ୍ ଗରମ ରହିଛି। ସିଧାସଳଖ ଖରାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।"],
        "HIGH": ["ପ୍ରବଳ ଗରମ। ବାହାରକୁ ଯିବା ସମୟରେ ସତର୍କ ରୁହନ୍ତୁ ଏବଂ ପାଣି ପିଅନ୍ତୁ।"]
    },
    "COLD_DRY": {
        "LOW": ["ପାଗ ଥଣ୍ଡା ଏବଂ ଶୁଷ୍କ ରହିଛି। ଉଷୁମ ପୋଷାକ ପିନ୍ଧନ୍ତୁ ଏବଂ ପାଣି ପିଅନ୍ତୁ।"],
        "MODERATE": ["ବେଶ୍ ଥଣ୍ଡା ଏବଂ ଶୁଖିଲା ପାଗ। ଶୀତ ପୋଷାକ ବ୍ୟବହାର କରନ୍ତୁ।"],
        "HIGH": ["ପ୍ରବଳ ଥଣ୍ଡା ଏବଂ ଶୁଷ୍କ ପବନ। ଭଲ ଭାବରେ ଗରମ ପୋଷାକ ପିନ୍ଧନ୍ତୁ।"]
    },
    "COLD": {
        "LOW": ["ପାଗ ସାମାନ୍ୟ ଥଣ୍ଡା ଅଛି। ହାଲୁକା ଶୀତ ପୋଷାକ ପିନ୍ଧନ୍ତୁ।"],
        "MODERATE": ["ପାଗରେ ଥଣ୍ଡା ରହିଛି। ଶୀତ ପୋଷାକ ପାଖରେ ରଖନ୍ତୁ।"],
        "HIGH": ["ବେଶ୍ ଥଣ୍ଡା ପାଗ। ବାହାରକୁ ଯିବା ପୂର୍ବରୁ ଉଷୁମ ପୋଷାକ ପିନ୍ଧନ୍ତୁ।"]
    },
    "HUMID": {
        "LOW": ["ବାୟୁରେ ସାମାନ୍ୟ ଆର୍ଦ୍ରତା ରହିଛି। ହାଲୁକା ପୋଷାକ ପିନ୍ଧନ୍ତୁ।"],
        "MODERATE": ["ଗୁଳୁଗୁଳି ଅନୁଭୂତ ହେଉଛି। ପାଣି ପିଅନ୍ତୁ ଏବଂ ଛାଇରେ ରୁହନ୍ତୁ।"],
        "HIGH": ["ବାୟୁରେ ଆର୍ଦ୍ରତା ବହୁତ ଅଧିକ। ନିୟମିତ ପାଣି ପିଅନ୍ତୁ।"]
    },
    "DRY": {
        "LOW": ["ବାୟୁ ସାମାନ୍ୟ ଶୁଷ୍କ ଅଛି। ଯଥେଷ୍ଟ ପାଣି ପିଅନ୍ତୁ।"],
        "MODERATE": ["ପାଗ ବେଶ୍ ଶୁଷ୍କ ରହିଛି। ନିୟମିତ ପାଣି ପିଉଥାନ୍ତୁ।"],
        "HIGH": ["ବାୟୁ ବହୁତ ଶୁଷ୍କ। ପ୍ରଚୁର ପାଣି ପିଅନ୍ତୁ ଏବଂ ଶରୀରକୁ ସତେଜ ରଖନ୍ତୁ।"]
    },
    "COMFORTABLE": {
        "LOW": ["ପାଗ ସୁଖଦ ଏବଂ ଅନୁକୂଳ ରହିଛି। ନିଜର ଦିନଟିକୁ ଉପଭୋଗ କରନ୍ତୁ।"],
        "MODERATE": ["ପାଗ ବହୁତ ଆରାମଦାୟକ ଏବଂ ଭଲ ଅଛି। ବାହାରକୁ ଯିବା ପାଇଁ ଭଲ ଦିନ।"],
        "HIGH": ["ପାଗ ଅତି ଚମତ୍କାର ରହିଛି। ବାହାର ପରିବେଶର ଆନନ୍ଦ ନିଅନ୍ତୁ।"]
    }
}


# =====================================================================
# Localized Action Text Mappings
# =====================================================================

ACTION_TEXT_MAP = {
    "en": {
        "AVOID_OUTDOOR_EXPOSURE": "Avoid outdoor exposure.",
        "USE_RESPIRATORY_PROTECTION": "Use suitable respiratory protection.",
        "LIMIT_OUTDOOR_ACTIVITY": "Limit outdoor activity.",
        "KEEP_WINDOWS_CLOSED": "Keep windows closed where practical.",
        "REDUCE_PROLONGED_OUTDOOR": "Reduce prolonged outdoor activity.",
        "SENSITIVE_TAKE_CARE": "Sensitive people should take extra care.",
        "PREFER_WELL_VENTILATED": "Prefer well-ventilated, lower-pollution areas.",
        "VERIFY_SENSOR_TELEMETRY": "Verify sensor telemetry.",
        "USE_GENERAL_PRECAUTIONS": "Use general pollution precautions.",
        # Source-specific actions
        "ACTION_TRAFFIC": "Reduce exposure near busy roads when practical.",
        "ACTION_HEAVY_DUST": "Avoid visibly dusty areas and use respiratory protection if needed.",
        "ACTION_CONSTRUCTION": "Avoid active dust-generating areas when practical.",
        "ACTION_COMBUSTION": "Avoid smoke and poorly ventilated combustion areas.",
        "ACTION_BIOMASS": "Avoid smoke and keep indoor air protected.",
        "ACTION_INDUSTRIAL": "Limit exposure near industrial zones.",
        "ACTION_INDOOR": "Improve indoor ventilation.",
        # Forecast actions
        "ACTION_FORECAST_PRECAUTION": "Take precautions before the forecast period.",
        # Gas hazard actions
        "ACTION_EVACUATE_ENCLOSED": "Evacuate enclosed space immediately into fresh air.",
        "ACTION_EVACUATE_IMMEDIATELY": "Evacuate the area immediately.",
        "ACTION_NO_IGNITION_OR_SWITCHES": "Do not operate electrical switches, phones, or open flames.",
        "ACTION_VENTILATE_GAS": "Open doors and windows to ventilate if safe to do so.",
        "ACTION_SHUT_GAS_SUPPLY": "Shut off main gas supply if accessible safely.",
        "ACTION_SEEK_MEDICAL": "Seek medical attention if experiencing headache, dizziness, or nausea.",
        "ACTION_CALL_EMERGENCY": "Call emergency services from a safe distance.",
        "ACTION_MOVE_AWAY_CHEMICAL": "Move away from chemical vapor or toxic fume source.",
        "ACTION_STRONG_VENTILATION": "Ensure strong continuous ventilation.",
        "ACTION_AVOID_FUMES": "Avoid breathing fumes directly and use suitable protection.",
        "ACTION_CHECK_FIRE": "Check for nearby fire or combustion sources.",
        "ACTION_MOVE_AWAY_SMOKE": "Move away from dense smoke and protect airways.",
        "ACTION_INSPECT_GAS_APPLIANCES": "Inspect gas appliances and ensure proper ventilation."
    },
    "hi": {
        "AVOID_OUTDOOR_EXPOSURE": "बाहर जाने से बचें।",
        "USE_RESPIRATORY_PROTECTION": "उपयुक्त मास्क (N95) का उपयोग करें।",
        "LIMIT_OUTDOOR_ACTIVITY": "बाहरी गतिविधियाँ सीमित करें।",
        "KEEP_WINDOWS_CLOSED": "यथासंभव खिड़कियाँ बंद रखें।",
        "REDUCE_PROLONGED_OUTDOOR": "लंबे समय तक बाहर रहने से बचें।",
        "SENSITIVE_TAKE_CARE": "संवेदनशील लोग विशेष सावधानी बरतें।",
        "PREFER_WELL_VENTILATED": "हवादार और कम प्रदूषण वाले क्षेत्रों को प्राथमिकता दें।",
        "VERIFY_SENSOR_TELEMETRY": "सेंसर टेलीमेट्री सत्यापित करें।",
        "USE_GENERAL_PRECAUTIONS": "सामान्य प्रदूषण सावधानियों का पालन करें।",
        # Source-specific actions
        "ACTION_TRAFFIC": "व्यस्त सड़कों के पास जाने से बचें।",
        "ACTION_HEAVY_DUST": "धूल भरे क्षेत्रों से बचें और मास्क का उपयोग करें।",
        "ACTION_CONSTRUCTION": "निर्माण और धूल वाले स्थानों से दूर रहें।",
        "ACTION_COMBUSTION": "धुएँ और खराब वेंटिलेशन वाले क्षेत्रों से बचें।",
        "ACTION_BIOMASS": "धुएँ से बचें और इनडोर हवा को सुरक्षित रखें।",
        "ACTION_INDUSTRIAL": "औद्योगिक क्षेत्रों के पास जाने से बचें।",
        "ACTION_INDOOR": "घर के अंदर वेंटिलेशन में सुधार करें।",
        # Forecast actions
        "ACTION_FORECAST_PRECAUTION": "पूर्वानुमान अवधि से पहले आवश्यक सावधानी बरतें।",
        # Gas hazard actions
        "ACTION_EVACUATE_ENCLOSED": "तुरंत बंद कमरा छोड़कर बाहर ताज़ी हवा में जाएं।",
        "ACTION_EVACUATE_IMMEDIATELY": "तुरंत बंद क्षेत्र को खाली करें और सुरक्षित स्थान पर जाएं।",
        "ACTION_NO_IGNITION_OR_SWITCHES": "बिजली के स्विच, फोन या खुली आग का इस्तेमाल बिल्कुल न करें।",
        "ACTION_VENTILATE_GAS": "बाहरी दरवाजे और खिड़कियाँ खोलकर तुरंत वेंटिलेशन करें।",
        "ACTION_SHUT_GAS_SUPPLY": "यदि सुरक्षित हो तो मुख्य गैस आपूर्ति तुरंत बंद करें।",
        "ACTION_SEEK_MEDICAL": "चक्कर, सिरदर्द या मतली होने पर तुरंत चिकित्सा सहायता लें।",
        "ACTION_CALL_EMERGENCY": "सुरक्षित दूरी से आपातकालीन सेवाओं को सूचित करें।",
        "ACTION_MOVE_AWAY_CHEMICAL": "रासायनिक स्रोत या वाष्प से तुरंत दूर हटें।",
        "ACTION_STRONG_VENTILATION": "लगातार तेज वेंटिलेशन सुनिश्चित करें।",
        "ACTION_AVOID_FUMES": "सीधे वाष्प में सांस लेने से बचें और सुरक्षात्मक उपाय करें।",
        "ACTION_CHECK_FIRE": "आसपास आग या दहन स्रोतों की जाँच करें।",
        "ACTION_MOVE_AWAY_SMOKE": "घने धुएँ से दूर हटें और श्वसन मार्ग की रक्षा करें।",
        "ACTION_INSPECT_GAS_APPLIANCES": "गैस उपकरणों की जाँच करें और वेंटिलेशन सुनिश्चित करें।"
    },
    "or": {
        "AVOID_OUTDOOR_EXPOSURE": "ବାହାରକୁ ଯିବା ବନ୍ଦ କରନ୍ତୁ।",
        "USE_RESPIRATORY_PROTECTION": "ଉପଯୁକ୍ତ ମାସ୍କ (N95) ବ୍ୟବହାର କରନ୍ତୁ।",
        "LIMIT_OUTDOOR_ACTIVITY": "ବାହାରେ ଅଧିକ ସମୟ ବିତାନ୍ତୁ ନାହିଁ।",
        "KEEP_WINDOWS_CLOSED": "ଝରକା କବାଟ ବନ୍ଦ ରଖନ୍ତୁ।",
        "REDUCE_PROLONGED_OUTDOOR": "ଅଧିକ ସମୟ ବାହାରେ ରହିବା କମାନ୍ତୁ।",
        "SENSITIVE_TAKE_CARE": "ସମ୍ବେଦନଶୀଳ ବ୍ୟକ୍ତିମାନେ ବିଶେଷ ଯତ୍ନ ନିଅନ୍ତୁ।",
        "PREFER_WELL_VENTILATED": "ଭଲ ଭାବରେ ବାୟୁ ଚଳାଚଳ ହେଉଥିବା ସ୍ଥାନ ବାଛନ୍ତୁ।",
        "VERIFY_SENSOR_TELEMETRY": "ସେନ୍ସର ଟେଲିମେଟ୍ରି ଯାଞ୍ଚ କରନ୍ତୁ।",
        "USE_GENERAL_PRECAUTIONS": "ସାଧାରଣ ପ୍ରଦୂଷଣ ସତର୍କତା ଅବଲମ୍ବନ କରନ୍ତୁ।",
        # Source-specific actions
        "ACTION_TRAFFIC": "ବ୍ୟସ୍ତବହୁଳ ରାସ୍ତା ନିକଟକୁ ଯିବା କମାନ୍ତୁ।",
        "ACTION_HEAVY_DUST": "ଧୂଳି ଉଡୁଥିବା ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ ଏବଂ ମାସ୍କ ବ୍ୟବହାର କରନ୍ତୁ।",
        "ACTION_CONSTRUCTION": "ନିର୍ମାଣ କାର୍ଯ୍ୟ ଚାଲିଥିବା ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ।",
        "ACTION_COMBUSTION": "ଧୂଆଁ ଏବଂ କମ୍ ବାୟୁ ଚଳାଚଳ ଥିବା ସ୍ଥାନରୁ ଦୂରେଇ ରୁହନ୍ତୁ।",
        "ACTION_BIOMASS": "ଧୂଆଁରୁ ବଞ୍ଚନ୍ତୁ ଏବଂ ଘର ଭିତର ବାୟୁ ସୁରକ୍ଷିତ ରଖନ୍ତୁ।",
        "ACTION_INDUSTRIAL": "ଶିଳ୍ପାଞ୍ଚଳ ନିକଟରେ ରହିବା ସମୟ ସୀମିତ କରନ୍ତୁ।",
        "ACTION_INDOOR": "ଘର ଭିତରେ ବାୟୁ ଚଳାଚଳ ବୃଦ୍ଧି କରନ୍ତୁ।",
        # Forecast actions
        "ACTION_FORECAST_PRECAUTION": "ପୂର୍ବାନୁମାନ ଅବଧି ପୂର୍ବରୁ ଆବଶ୍ୟକ ସତର୍କତା ଅବଲମ୍ବନ କରନ୍ତୁ।",
        # Gas hazard actions
        "ACTION_EVACUATE_ENCLOSED": "ତୁରନ୍ତ ବନ୍ଦ କୋଠରୀ ଛାଡ଼ି ବାହାର ସତେଜ ବାୟୁକୁ ଯାଆନ୍ତୁ।",
        "ACTION_EVACUATE_IMMEDIATELY": "ତୁରନ୍ତ ବନ୍ଦ ସ୍ଥାନ ଛାଡ଼ି ନିରାପଦ ସ୍ଥାନକୁ ଯାଆନ୍ତୁ।",
        "ACTION_NO_IGNITION_OR_SWITCHES": "ବିଦ୍ୟୁତ୍ ସୁଇଚ୍, ଫୋନ୍ କିମ୍ବା ଖୋଲା ନିଆଁ ବ୍ୟବହାର କରନ୍ତୁ ନାହିଁ।",
        "ACTION_VENTILATE_GAS": "ବାହାର କବାଟ ଓ ଝରକା ଖୋଲି ଘର ଭିତରେ ବାୟୁ ଚଳାଚଳ କରାନ୍ତୁ।",
        "ACTION_SHUT_GAS_SUPPLY": "ଯଦି ସୁରକ୍ଷିତ ତେବେ ମୁଖ୍ୟ ଗ୍ୟାସ୍ ଯୋଗାଣ ତୁରନ୍ତ ବନ୍ଦ କରନ୍ତୁ।",
        "ACTION_SEEK_MEDICAL": "ମୁଣ୍ଡ ବୁଲାଇବା କିମ୍ବା ବାନ୍ତି ଲାଗିଲେ ତୁରନ୍ତ ଡାକ୍ତରଙ୍କ ପରାମର୍ଶ ନିଅନ୍ତୁ।",
        "ACTION_CALL_EMERGENCY": "ନିରାପଦ ଦୂରତାରୁ ଜରୁରୀକାଳୀନ ସେବାକୁ ଫୋନ୍ କରନ୍ତୁ।",
        "ACTION_MOVE_AWAY_CHEMICAL": "ରାସାୟନିକ ବାଷ୍ପ ଉତ୍ସରୁ ତୁରନ୍ତ ଦୂରେଇ ଯାଆନ୍ତୁ।",
        "ACTION_STRONG_VENTILATION": "ଘର ଭିତରେ ଅଧିକ ବାୟୁ ଚଳାଚଳ ସୁନିଶ୍ଚିତ କରନ୍ତୁ।",
        "ACTION_AVOID_FUMES": "ବାଷ୍ପରେ ସିଧାସଳଖ ନିଶ୍ୱାସ ନେବାରୁ ଦୂରେଇ ରୁହନ୍ତୁ ଏବଂ ସୁରକ୍ଷା ବ୍ୟବସ୍ଥା ଗ୍ରହଣ କରନ୍ତୁ।",
        "ACTION_CHECK_FIRE": "ନିକଟରେ ଅଗ୍ନି କିମ୍ବା ଜଳିବା ଉତ୍ସ ଯାଞ୍ଚ କରନ୍ତୁ।",
        "ACTION_MOVE_AWAY_SMOKE": "ପ୍ରବଳ ଧୂଆଁରୁ ଦୂରେଇ ଯାଆନ୍ତୁ ଏବଂ ଶ୍ୱାସକ୍ରିୟା ସୁରକ୍ଷିତ ରଖନ୍ତୁ।",
        "ACTION_INSPECT_GAS_APPLIANCES": "ଗ୍ୟାସ୍ ଉପକରଣ ଯାଞ୍ଚ କରନ୍ତୁ ଏବଂ ବାୟୁ ଚଳାଚଳ ସୁନିଶ୍ଚିତ କରନ୍ତୁ।"
    }
}


# =====================================================================
# Localized Provisional Messages
# =====================================================================

PROVISIONAL_TEXT_MAP = {
    "en": {
        "PROVISIONAL_CRITICAL": "Provisional PM assessment indicates critical particulate levels based on available readings. Limit exposure.",
        "PROVISIONAL_SEVERE": "Provisional PM assessment indicates high particulate pollution based on available readings.",
        "PROVISIONAL_HIGH": "Provisional PM assessment shows elevated particulates. Sensitive individuals should take care.",
        "PROVISIONAL_MODERATE": "Provisional PM assessment indicates moderate particulate levels.",
        "PROVISIONAL_NORMAL": "Provisional PM assessment indicates acceptable particulate levels across available readings.",
        "PROVISIONAL_UNAVAILABLE": "Air quality data is unavailable or unverified. Maintain standard precautions."
    },
    "hi": {
        "PROVISIONAL_CRITICAL": "उपलब्ध आंकड़ों के आधार पर अनंतिम पीएम आकलन गंभीर प्रदूषण दर्शाता है। बाहर जाने से बचें।",
        "PROVISIONAL_SEVERE": "उपलब्ध आंकड़ों के आधार पर अनंतिम पीएम आकलन उच्च प्रदूषण दर्शाता है।",
        "PROVISIONAL_HIGH": "अनंतिम पीएम आकलन बढ़ा हुआ प्रदूषण दर्शाता है। संवेदनशील लोग ध्यान दें।",
        "PROVISIONAL_MODERATE": "अनंतिम पीएम आकलन मध्यम प्रदूषण स्तर दर्शाता है।",
        "PROVISIONAL_NORMAL": "उपलब्ध आंकड़ों में स्वीकार्य कण स्तर दर्शाया गया है।",
        "PROVISIONAL_UNAVAILABLE": "वायु गुणवत्ता डेटा अनुपलब्ध या असत्यापित है। सामान्य सावधानियाँ बरतें।"
    },
    "or": {
        "PROVISIONAL_CRITICAL": "ଉପଲବ୍ଧ ତଥ୍ୟ ଅନୁସାରେ ଅସ୍ଥାୟୀ ପିଏମ୍ ଆକଳନ ଗମ୍ଭୀର ପ୍ରଦୂଷଣ ଦର୍ଶାଉଛି। ବାହାରକୁ ଯିବା ବନ୍ଦ କରନ୍ତୁ।",
        "PROVISIONAL_SEVERE": "ଉପଲବ୍ଧ ତଥ୍ୟ ଅନୁସାରେ ଅସ୍ଥାୟୀ ପିଏମ୍ ଆକଳନ ଉଚ୍ଚ ପ୍ରଦୂଷଣ ଦର୍ଶାଉଛି।",
        "PROVISIONAL_HIGH": "ଅସ୍ଥାୟୀ ପିଏମ୍ ଆକଳନ ଅଧିକ ଧୂଳିକଣା ଦର୍ଶାଉଛି। ସମ୍ବେଦନଶୀଳ ବ୍ୟକ୍ତି ସତର୍କ ରୁହନ୍ତୁ।",
        "PROVISIONAL_MODERATE": "ଅସ୍ଥାୟୀ ପିଏମ୍ ଆକଳନ ମଧ୍ୟମ ଧରଣର ପ୍ରଦୂଷଣ ଦର୍ଶାଉଛି।",
        "PROVISIONAL_NORMAL": "ଉପଲବ୍ଧ ତଥ୍ୟରେ ଗ୍ରହଣଯୋଗ୍ୟ ଧୂଳିକଣା ସ୍ତର ଦେଖାଯାଇଛି।",
        "PROVISIONAL_UNAVAILABLE": "ବାୟୁ ଗୁଣବତ୍ତା ତଥ୍ୟ ଉପଲବ୍ଧ ନାହିଁ କିମ୍ବା ଯାଞ୍ଚ ହୋଇନାହିଁ। ସାଧାରଣ ସତର୍କତା ବଜାୟ ରଖନ୍ତୁ।"
    }
}


# =====================================================================
# Localization Retrieval Helpers (Automatic Fallback to English)
# =====================================================================

LOCALIZED_AQI = {
    "en": AQI_VARIANTS,
    "hi": AQI_VARIANTS_HI,
    "or": AQI_VARIANTS_OR,
}

LOCALIZED_SOURCE = {
    "en": SOURCE_VARIANTS,
    "hi": SOURCE_VARIANTS_HI,
    "or": SOURCE_VARIANTS_OR,
}

LOCALIZED_FORECAST = {
    "en": FORECAST_VARIANTS,
    "hi": FORECAST_VARIANTS_HI,
    "or": FORECAST_VARIANTS_OR,
}

LOCALIZED_WEATHER = {
    "en": WEATHER_VARIANTS,
    "hi": WEATHER_VARIANTS_HI,
    "or": WEATHER_VARIANTS_OR,
}

LOCALIZED_GAS = {
    "en": GAS_VARIANTS_EN,
    "hi": GAS_VARIANTS_HI,
    "or": GAS_VARIANTS_OR,
}


def normalize_language(lang: str | None) -> str:
    """Normalize language code to one of 'en', 'hi', 'or'; defaults to 'en'."""
    if not lang:
        return "en"
    l = str(lang).strip().lower()
    if l in ("hi", "hindi"):
        return "hi"
    if l in ("or", "odia", "oriya"):
        return "or"
    return "en"


def get_aqi_variants(severity: str, sub: str, lang: str = "en") -> list[str]:
    norm_lang = normalize_language(lang)
    lang_map = LOCALIZED_AQI.get(norm_lang, AQI_VARIANTS)
    sev_map = lang_map.get(severity) or AQI_VARIANTS.get(severity, {})
    variants = sev_map.get(sub)
    if not variants:
        variants = AQI_VARIANTS.get(severity, {}).get(sub, [])
    return variants or []


def get_source_variants(source: str, sub: str, lang: str = "en") -> list[str]:
    norm_lang = normalize_language(lang)
    lang_map = LOCALIZED_SOURCE.get(norm_lang, SOURCE_VARIANTS)
    src_map = lang_map.get(source) or lang_map.get("MIXED") or SOURCE_VARIANTS.get(source, SOURCE_VARIANTS["MIXED"])
    variants = src_map.get(sub)
    if not variants:
        variants = SOURCE_VARIANTS.get(source, SOURCE_VARIANTS["MIXED"]).get(sub, [])
    return variants or []


def get_forecast_variants(trend: str, sub: str, lang: str = "en") -> list[str]:
    norm_lang = normalize_language(lang)
    lang_map = LOCALIZED_FORECAST.get(norm_lang, FORECAST_VARIANTS)
    t_map = lang_map.get(trend) or FORECAST_VARIANTS.get(trend, {})
    variants = t_map.get(sub)
    if not variants:
        variants = FORECAST_VARIANTS.get(trend, {}).get(sub, [])
    return variants or []


def get_weather_variants(cond: str, sub: str, lang: str = "en") -> list[str]:
    norm_lang = normalize_language(lang)
    lang_map = LOCALIZED_WEATHER.get(norm_lang, WEATHER_VARIANTS)
    w_map = lang_map.get(cond) or WEATHER_VARIANTS.get(cond, {})
    variants = w_map.get(sub)
    if not variants:
        variants = WEATHER_VARIANTS.get(cond, {}).get(sub, [])
    return variants or []


def get_gas_variants(gas_type: str, severity: str, sub: str, lang: str = "en") -> list[str]:
    norm_lang = normalize_language(lang)
    lang_map = LOCALIZED_GAS.get(norm_lang, GAS_VARIANTS_EN)
    type_map = lang_map.get(gas_type) or GAS_VARIANTS_EN.get(gas_type, {})
    sev_map = type_map.get(severity) or GAS_VARIANTS_EN.get(gas_type, {}).get(severity, {})
    variants = sev_map.get(sub)
    if not variants:
        variants = sev_map.get("LOW") or GAS_VARIANTS_EN.get(gas_type, {}).get(severity, {}).get(sub, [])
    if not variants:
        variants = GAS_VARIANTS_EN.get(gas_type, {}).get(severity, {}).get("LOW", [])
    return variants or []


def get_action_text(action_key: str, lang: str = "en") -> str:
    norm_lang = normalize_language(lang)
    lang_actions = ACTION_TEXT_MAP.get(norm_lang, ACTION_TEXT_MAP["en"])
    text = lang_actions.get(action_key)
    if not text:
        text = ACTION_TEXT_MAP["en"].get(action_key, action_key)
    return text


def get_provisional_text(msg_key: str, lang: str = "en") -> str:
    norm_lang = normalize_language(lang)
    lang_prov = PROVISIONAL_TEXT_MAP.get(norm_lang, PROVISIONAL_TEXT_MAP["en"])
    text = lang_prov.get(msg_key)
    if not text:
        text = PROVISIONAL_TEXT_MAP["en"].get(msg_key, "")
    return text


