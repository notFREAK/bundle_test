defmodule GatewayWeb.Router do
  use GatewayWeb, :router

  scope "/api/v1", GatewayWeb do
    get "/metrics/current", MetricsController, :current
    get "/gateway/status", GatewayController, :status
  end
end
