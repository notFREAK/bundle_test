const express = require('express');
const crypto = require('crypto');

const app = express();
app.use(express.json());

const users = new Map();
const accessTokens = new Map();
const refreshTokens = new Map();

const issue = () => crypto.randomBytes(24).toString('hex');
const auth = (req, res, next) => {
  const h = req.headers.authorization || '';
  const token = h.startsWith('Bearer ') ? h.slice(7) : null;
  const username = token ? accessTokens.get(token) : null;
  if (!username) return res.status(401).json({ error: { code: 'UNAUTHORIZED', message: 'invalid token' } });
  req.user = users.get(username);
  next();
};

app.post('/api/v1/auth/register', (req, res) => {
  const { username, password, email } = req.body || {};
  if (!username || !password) return res.status(400).json({ error: { code: 'VALIDATION_ERROR' } });
  users.set(username, { username, email: email || `${username}@example.local`, password, role: 'viewer' });
  res.status(201).json({ status: 'registered' });
});

app.post('/api/v1/auth/login', (req, res) => {
  const { username, password } = req.body || {};
  const user = users.get(username);
  if (!user || user.password !== password) return res.status(401).json({ error: { code: 'UNAUTHORIZED' } });
  const accessToken = issue();
  const refreshToken = issue();
  accessTokens.set(accessToken, username);
  refreshTokens.set(refreshToken, username);
  res.json({ accessToken, refreshToken });
});

app.post('/api/v1/auth/refresh', (req, res) => {
  const username = refreshTokens.get((req.body || {}).refreshToken);
  if (!username) return res.status(401).json({ error: { code: 'UNAUTHORIZED' } });
  const accessToken = issue();
  accessTokens.set(accessToken, username);
  res.json({ accessToken, refreshToken: req.body.refreshToken });
});

app.post('/api/v1/auth/logout', auth, (req, res) => {
  refreshTokens.delete((req.body || {}).refreshToken);
  res.status(200).json({ status: 'ok' });
});

app.get('/api/v1/auth/me', auth, (req, res) => res.json({ username: req.user.username, email: req.user.email, role: req.user.role }));
app.get('/api/v1/metrics/current', auth, (_req, res) => res.json({ temperatureC: 25, cpuLoadPercent: 15, ramLoadPercent: 35, uptimeSeconds: 9, supplyVoltageV: 12.0, timestampUtc: new Date().toISOString() }));
app.get('/api/v1/gateway/status', (_req, res) => res.json({ service: 'ok', opcua: 'simulated', cache: 'ready' }));

app.listen(3001, () => console.log('express gateway at 3001'));
