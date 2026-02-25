defmodule GatewayWeb.MetricsController do
  use GatewayWeb, :controller
  def current(conn, _params) do
    json(conn, %{temperatureC: 25.0, cpuLoadPercent: 17.0, ramLoadPercent: 47.0, uptimeSeconds: 6, supplyVoltageV: 12.0, timestampUtc: DateTime.utc_now()})
  end
end
