import asyncio
import math
import os
import random
import time
from datetime import datetime, timezone

import psutil
from asyncua import Server, ua


class MetricsGenerator:
    def __init__(self):
        self.start_time = time.time()
        self._phase = 0.0

    def read(self) -> dict:
        cpu_load = psutil.cpu_percent(interval=None)
        ram_load = psutil.virtual_memory().percent
        uptime_s = max(0, int(time.time() - self.start_time))

        self._phase += 0.15
        temperature = 42.0 + 8.0 * math.sin(self._phase) + random.uniform(-0.5, 0.5)
        voltage = 12.2 + 0.3 * math.sin(self._phase / 2.0) + random.uniform(-0.03, 0.03)

        return {
            "temperature_c": round(temperature, 2),
            "cpu_load_percent": round(float(cpu_load), 2),
            "ram_load_percent": round(float(ram_load), 2),
            "uptime_seconds": uptime_s,
            "supply_voltage_v": round(voltage, 3),
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }


async def main() -> None:
    endpoint = os.getenv("OPCUA_ENDPOINT", "opc.tcp://0.0.0.0:4840/metrics/server/")
    namespace_uri = os.getenv("OPCUA_NAMESPACE_URI", "urn:argum:demo:metrics")
    update_period_ms = int(os.getenv("METRICS_UPDATE_PERIOD_MS", "1000"))
    sleep_seconds = max(0.1, update_period_ms / 1000.0)

    server = Server()
    await server.init()
    server.set_endpoint(endpoint)
    server.set_server_name("Mini OPC UA Metrics Server")

    idx = await server.register_namespace(namespace_uri)
    objects = server.nodes.objects
    device = await objects.add_object(idx, "DeviceMetrics")

    temp_var = await device.add_variable(idx, "TemperatureC", 0.0, ua.VariantType.Double)
    cpu_var = await device.add_variable(idx, "CpuLoadPercent", 0.0, ua.VariantType.Double)
    ram_var = await device.add_variable(idx, "RamLoadPercent", 0.0, ua.VariantType.Double)
    uptime_var = await device.add_variable(idx, "UptimeSeconds", 0, ua.VariantType.UInt32)
    volt_var = await device.add_variable(idx, "SupplyVoltageV", 0.0, ua.VariantType.Double)
    ts_var = await device.add_variable(idx, "TimestampUtc", "", ua.VariantType.String)

    # Сохраняем поведение "как в текущей реализации" — переменные writable.
    for node in (temp_var, cpu_var, ram_var, uptime_var, volt_var, ts_var):
        await node.set_writable()

    gen = MetricsGenerator()

    print("OPC UA сервер запущен:")
    print(f"  Endpoint: {endpoint.replace('0.0.0.0', 'localhost')}")
    print(f"  Namespace URI: {namespace_uri}")
    print("  Нажмите Ctrl+C для остановки")

    async with server:
        while True:
            try:
                m = gen.read()
                await temp_var.write_value(ua.Variant(float(m["temperature_c"]), ua.VariantType.Double))
                await cpu_var.write_value(ua.Variant(float(m["cpu_load_percent"]), ua.VariantType.Double))
                await ram_var.write_value(ua.Variant(float(m["ram_load_percent"]), ua.VariantType.Double))
                await uptime_var.write_value(ua.Variant(int(m["uptime_seconds"]), ua.VariantType.UInt32))
                await volt_var.write_value(ua.Variant(float(m["supply_voltage_v"]), ua.VariantType.Double))
                # Timestamp пишем последним как маркер "готового" снапшота
                await ts_var.write_value(ua.Variant(str(m["timestamp_utc"]), ua.VariantType.String))

                print(
                    f"T={m['temperature_c']}°C | CPU={m['cpu_load_percent']}% | "
                    f"RAM={m['ram_load_percent']}% | Uptime={m['uptime_seconds']}s | "
                    f"V={m['supply_voltage_v']}V | TS={m['timestamp_utc']}"
                )
            except Exception as e:
                print(f"Update error: {e}")

            await asyncio.sleep(sleep_seconds)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nСервер остановлен.")
