require 'json'
require 'webrick'
require 'securerandom'
require 'time'

users = {}
access = {}
refresh = {}
uptime = 0

server = WEBrick::HTTPServer.new(Port: 8003, BindAddress: '0.0.0.0', AccessLog: [], Logger: WEBrick::Log.new('/dev/null'))

server.mount_proc '/' do |req, res|
  path = req.path
  body = req.body.to_s.empty? ? {} : JSON.parse(req.body)
  auth = req['Authorization'].to_s
  current_user = nil
  if auth.start_with?('Bearer ')
    username = access[auth.sub('Bearer ', '')]
    current_user = users[username]
  end

  case [req.request_method, path]
  when ['POST', '/api/v1/auth/register']
    if body['username'].to_s.empty? || body['password'].to_s.empty?
      res.status = 400; res.body = { error: { code: 'VALIDATION_ERROR' } }.to_json
    elsif users.key?(body['username'])
      res.status = 409; res.body = { error: { code: 'CONFLICT' } }.to_json
    else
      users[body['username']] = { 'username'=>body['username'], 'email'=>(body['email'] || "#{body['username']}@example.local"), 'password'=>body['password'], 'role'=>'viewer' }
      res.status = 201; res.body = { status: 'registered' }.to_json
    end
  when ['POST', '/api/v1/auth/login']
    user = users[body['username']]
    if user.nil? || user['password'] != body['password']
      res.status = 401; res.body = { error: { code: 'UNAUTHORIZED' } }.to_json
    else
      at = SecureRandom.hex(24); rt = SecureRandom.hex(24)
      access[at] = user['username']; refresh[rt] = user['username']
      res.status = 200; res.body = { accessToken: at, refreshToken: rt }.to_json
    end
  when ['POST', '/api/v1/auth/refresh']
    username = refresh[body['refreshToken']]
    if username.nil?
      res.status = 401; res.body = { error: { code: 'UNAUTHORIZED' } }.to_json
    else
      at = SecureRandom.hex(24); access[at] = username
      res.status = 200; res.body = { accessToken: at, refreshToken: body['refreshToken'] }.to_json
    end
  when ['POST', '/api/v1/auth/logout']
    if current_user.nil?
      res.status = 401; res.body = { error: { code: 'UNAUTHORIZED' } }.to_json
    else
      refresh.delete(body['refreshToken'])
      res.status = 200; res.body = { status: 'ok' }.to_json
    end
  when ['GET', '/api/v1/auth/me']
    if current_user.nil?
      res.status = 401; res.body = { error: { code: 'UNAUTHORIZED' } }.to_json
    else
      res.status = 200; res.body = { username: current_user['username'], email: current_user['email'], role: current_user['role'] }.to_json
    end
  when ['GET', '/api/v1/metrics/current']
    if current_user.nil?
      res.status = 401; res.body = { error: { code: 'UNAUTHORIZED' } }.to_json
    else
      uptime += 1
      res.status = 200; res.body = { temperatureC: 25.0, cpuLoadPercent: 11.0, ramLoadPercent: 33.0, uptimeSeconds: uptime, supplyVoltageV: 12.0, timestampUtc: Time.now.utc.iso8601 }.to_json
    end
  when ['GET', '/api/v1/gateway/status']
    res.status = 200; res.body = { service: 'ok', opcua: 'simulated', cache: 'ready' }.to_json
  else
    res.status = 404; res.body = { error: { code: 'NOT_FOUND' } }.to_json
  end

  res['Content-Type'] = 'application/json'
end

trap('INT') { server.shutdown }
server.start
