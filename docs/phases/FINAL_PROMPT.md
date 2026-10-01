Integrate the existing NavosEdge Intelligence Server with the Arduino UNO Q hardware-side data producer.

First inspect the actual hardware code, sensor libraries, and supported interfaces. Do not assume sensor output formats or pin mappings.

Implement a hardware client that:

* Performs sensor initialization and configured warm-up/stabilization.
* Constructs the agreed JSON payload using actual readings.
* Checks server health/readiness.
* Uploads readings periodically using HTTP POST.
* Maintains sensing and local operation if the server disconnects.
* Reconnects and resumes uploads safely.
* Subscribes to the SSE endpoint for server events if the UNO Q runtime supports the required HTTP streaming behavior.

Keep sampling and upload intervals configurable. Include clear logs for sensor readiness, connection status, upload success/failure, and inference availability. Do not block sensor sampling while waiting for a network response.

Test with simulated payloads before claiming physical hardware integration is complete.
