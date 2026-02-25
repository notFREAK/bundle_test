Mix.install([{:plug_cowboy, "~> 2.7"}, {:jason, "~> 1.4"}])

defmodule GatewayRouter do
  use Plug.Router
  plug Plug.Logger
  plug Plug.Parsers, parsers: [:json], pass: ["application/json"], json_decoder: Jason
  plug :match
  plug :dispatch

  @users :users_table
  @access :access_table
  @refresh :refresh_table

  defp json(conn, code, payload) do
    conn |> Plug.Conn.put_resp_content_type("application/json") |> Plug.Conn.send_resp(code, Jason.encode!(payload))
  end

  defp current_user(conn) do
    auth = Plug.Conn.get_req_header(conn, "authorization") |> List.first() || ""
    case String.split(auth, "Bearer ", parts: 2) do
      [_, token] ->
        case :ets.lookup(@access, token) do
          [{_, username}] -> case :ets.lookup(@users, username) do [{_, user}] -> user; _ -> nil end
          _ -> nil
        end
      _ -> nil
    end
  end

  post "/api/v1/auth/register" do
    b = conn.body_params
    u = b["username"]; p = b["password"]
    cond do
      is_nil(u) or is_nil(p) -> json(conn, 400, %{error: %{code: "VALIDATION_ERROR"}})
      :ets.lookup(@users, u) != [] -> json(conn, 409, %{error: %{code: "CONFLICT"}})
      true ->
        user = %{username: u, email: b["email"] || "#{u}@example.local", password: p, role: "viewer"}
        :ets.insert(@users, {u, user}); json(conn, 201, %{status: "registered"})
    end
  end

  post "/api/v1/auth/login" do
    b = conn.body_params
    case :ets.lookup(@users, b["username"] || "") do
      [{_, user}] when user.password == b["password"] ->
        at = Base.encode16(:crypto.strong_rand_bytes(24), case: :lower)
        rt = Base.encode16(:crypto.strong_rand_bytes(24), case: :lower)
        :ets.insert(@access, {at, user.username}); :ets.insert(@refresh, {rt, user.username})
        json(conn, 200, %{accessToken: at, refreshToken: rt})
      _ -> json(conn, 401, %{error: %{code: "UNAUTHORIZED"}})
    end
  end

  post "/api/v1/auth/refresh" do
    rt = conn.body_params["refreshToken"] || ""
    case :ets.lookup(@refresh, rt) do
      [{_, username}] -> at = Base.encode16(:crypto.strong_rand_bytes(24), case: :lower); :ets.insert(@access, {at, username}); json(conn, 200, %{accessToken: at, refreshToken: rt})
      _ -> json(conn, 401, %{error: %{code: "UNAUTHORIZED"}})
    end
  end

  post "/api/v1/auth/logout" do
    if current_user(conn) == nil, do: json(conn, 401, %{error: %{code: "UNAUTHORIZED"}}), else: (:ets.delete(@refresh, conn.body_params["refreshToken"] || ""); json(conn, 200, %{status: "ok"}))
  end

  get "/api/v1/auth/me" do
    case current_user(conn) do
      nil -> json(conn, 401, %{error: %{code: "UNAUTHORIZED"}})
      u -> json(conn, 200, %{username: u.username, email: u.email, role: u.role})
    end
  end

  get "/api/v1/metrics/current" do
    if current_user(conn) == nil do
      json(conn, 401, %{error: %{code: "UNAUTHORIZED"}})
    else
      :ets.update_counter(:state_table, :uptime, {2, 1}, {:uptime, 0})
      [{:uptime, uptime}] = :ets.lookup(:state_table, :uptime)
      json(conn, 200, %{temperatureC: 25.0, cpuLoadPercent: 17.0, ramLoadPercent: 47.0, uptimeSeconds: uptime, supplyVoltageV: 12.0, timestampUtc: DateTime.utc_now()})
    end
  end

  get "/api/v1/gateway/status", do: json(conn, 200, %{service: "ok", opcua: "simulated", cache: "ready"})
  match _, do: json(conn, 404, %{error: %{code: "NOT_FOUND"}})
end

:ets.new(:users_table, [:set, :public, :named_table])
:ets.new(:access_table, [:set, :public, :named_table])
:ets.new(:refresh_table, [:set, :public, :named_table])
:ets.new(:state_table, [:set, :public, :named_table])

Plug.Cowboy.http(GatewayRouter, [], port: 8004)
Process.sleep(:infinity)
