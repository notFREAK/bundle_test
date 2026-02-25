<?php
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$method = $_SERVER['REQUEST_METHOD'];
$body = json_decode(file_get_contents('php://input') ?: '{}', true);
$storePath = __DIR__ . '/.state.json';
$state = file_exists($storePath) ? json_decode(file_get_contents($storePath), true) : ['users'=>[], 'access'=>[], 'refresh'=>[], 'uptime'=>0];

function save_state($path, $state) { file_put_contents($path, json_encode($state)); }
function out($code, $data) { http_response_code($code); header('Content-Type: application/json'); echo json_encode($data); exit; }
function current_user($state) {
  $h = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
  if (!str_starts_with($h, 'Bearer ')) return null;
  $t = substr($h, 7);
  $u = $state['access'][$t] ?? null;
  return $u ? ($state['users'][$u] ?? null) : null;
}
if ($path === '/api/v1/auth/register' && $method === 'POST') {
  if (empty($body['username']) || empty($body['password'])) out(400, ['error'=>['code'=>'VALIDATION_ERROR']]);
  if (isset($state['users'][$body['username']])) out(409, ['error'=>['code'=>'CONFLICT']]);
  $state['users'][$body['username']] = ['username'=>$body['username'],'email'=>($body['email'] ?? ($body['username'].'@example.local')),'password'=>$body['password'],'role'=>'viewer'];
  save_state($storePath, $state); out(201, ['status'=>'registered']);
}
if ($path === '/api/v1/auth/login' && $method === 'POST') {
  $u = $state['users'][$body['username'] ?? ''] ?? null;
  if (!$u || $u['password'] !== ($body['password'] ?? null)) out(401, ['error'=>['code'=>'UNAUTHORIZED']]);
  $at = bin2hex(random_bytes(24)); $rt = bin2hex(random_bytes(24));
  $state['access'][$at] = $u['username']; $state['refresh'][$rt] = $u['username'];
  save_state($storePath, $state); out(200, ['accessToken'=>$at,'refreshToken'=>$rt]);
}
if ($path === '/api/v1/auth/refresh' && $method === 'POST') {
  $username = $state['refresh'][$body['refreshToken'] ?? ''] ?? null;
  if (!$username) out(401, ['error'=>['code'=>'UNAUTHORIZED']]);
  $at = bin2hex(random_bytes(24)); $state['access'][$at] = $username;
  save_state($storePath, $state); out(200, ['accessToken'=>$at,'refreshToken'=>$body['refreshToken']]);
}
if ($path === '/api/v1/auth/logout' && $method === 'POST') {
  if (!current_user($state)) out(401, ['error'=>['code'=>'UNAUTHORIZED']]);
  unset($state['refresh'][$body['refreshToken'] ?? '']); save_state($storePath, $state); out(200, ['status'=>'ok']);
}
if ($path === '/api/v1/auth/me' && $method === 'GET') {
  $u = current_user($state); if (!$u) out(401, ['error'=>['code'=>'UNAUTHORIZED']]); out(200, ['username'=>$u['username'],'email'=>$u['email'],'role'=>$u['role']]);
}
if ($path === '/api/v1/metrics/current' && $method === 'GET') {
  if (!current_user($state)) out(401, ['error'=>['code'=>'UNAUTHORIZED']]);
  $state['uptime'] += 1; save_state($storePath, $state);
  out(200, ['temperatureC'=>25.0,'cpuLoadPercent'=>18.0,'ramLoadPercent'=>43.0,'uptimeSeconds'=>$state['uptime'],'supplyVoltageV'=>12.0,'timestampUtc'=>gmdate('c')]);
}
if ($path === '/api/v1/gateway/status' && $method === 'GET') out(200, ['service'=>'ok','opcua'=>'simulated','cache'=>'ready']);
out(404, ['error'=>['code'=>'NOT_FOUND']]);
