Rails.application.routes.draw do
  scope '/api/v1' do
    get '/metrics/current', to: proc { [200, { 'Content-Type' => 'application/json' }, [{ temperatureC: 25.0, cpuLoadPercent: 11.0, ramLoadPercent: 33.0, uptimeSeconds: 4, supplyVoltageV: 12.0, timestampUtc: Time.now.utc.iso8601 }.to_json]] }
    get '/gateway/status', to: proc { [200, { 'Content-Type' => 'application/json' }, [{ service: 'ok', opcua: 'simulated', cache: 'ready' }.to_json]] }
  end
end
