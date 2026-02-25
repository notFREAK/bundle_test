use axum::{extract::State, http::HeaderMap, routing::{get, post}, Json, Router};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::{collections::HashMap, sync::{Arc, Mutex}};

#[derive(Clone, Default)]
struct AppState {
    users: Arc<Mutex<HashMap<String, User>>>,
    access: Arc<Mutex<HashMap<String, String>>>,
    refresh: Arc<Mutex<HashMap<String, String>>>,
    uptime: Arc<Mutex<u64>>,
}

#[derive(Clone, Serialize, Deserialize)]
struct User { username: String, email: String, password: String, role: String }
#[derive(Deserialize)]
struct RegisterIn { username: String, email: Option<String>, password: String }
#[derive(Deserialize)]
struct LoginIn { username: String, password: String }
#[derive(Deserialize)]
struct RefreshIn { #[serde(rename = "refreshToken")] refresh_token: String }

fn token() -> String { uuid::Uuid::new_v4().to_string().replace('-', "") }

fn current_user(headers: &HeaderMap, state: &AppState) -> Option<User> {
    let auth = headers.get("authorization")?.to_str().ok()?;
    let t = auth.strip_prefix("Bearer ")?;
    let uname = state.access.lock().ok()?.get(t)?.clone();
    state.users.lock().ok()?.get(&uname).cloned()
}

async fn register(State(state): State<AppState>, Json(p): Json<RegisterIn>) -> (axum::http::StatusCode, Json<serde_json::Value>) {
    let mut users = state.users.lock().unwrap();
    if users.contains_key(&p.username) { return (axum::http::StatusCode::CONFLICT, Json(json!({"error":{"code":"CONFLICT"}}))); }
    users.insert(p.username.clone(), User { username: p.username.clone(), email: p.email.unwrap_or(format!("{}@example.local", p.username)), password: p.password, role: "viewer".into()});
    (axum::http::StatusCode::CREATED, Json(json!({"status":"registered"})))
}

async fn login(State(state): State<AppState>, Json(p): Json<LoginIn>) -> (axum::http::StatusCode, Json<serde_json::Value>) {
    let users = state.users.lock().unwrap();
    let Some(u) = users.get(&p.username) else { return (axum::http::StatusCode::UNAUTHORIZED, Json(json!({"error":{"code":"UNAUTHORIZED"}}))); };
    if u.password != p.password { return (axum::http::StatusCode::UNAUTHORIZED, Json(json!({"error":{"code":"UNAUTHORIZED"}}))); }
    drop(users);
    let at = token(); let rt = token();
    state.access.lock().unwrap().insert(at.clone(), p.username.clone());
    state.refresh.lock().unwrap().insert(rt.clone(), p.username);
    (axum::http::StatusCode::OK, Json(json!({"accessToken":at,"refreshToken":rt})))
}

async fn refresh(State(state): State<AppState>, Json(p): Json<RefreshIn>) -> (axum::http::StatusCode, Json<serde_json::Value>) {
    let Some(username) = state.refresh.lock().unwrap().get(&p.refresh_token).cloned() else {
        return (axum::http::StatusCode::UNAUTHORIZED, Json(json!({"error":{"code":"UNAUTHORIZED"}})));
    };
    let at = token();
    state.access.lock().unwrap().insert(at.clone(), username);
    (axum::http::StatusCode::OK, Json(json!({"accessToken":at,"refreshToken":p.refresh_token})))
}

async fn logout(State(state): State<AppState>, headers: HeaderMap, Json(p): Json<RefreshIn>) -> (axum::http::StatusCode, Json<serde_json::Value>) {
    if current_user(&headers, &state).is_none() { return (axum::http::StatusCode::UNAUTHORIZED, Json(json!({"error":{"code":"UNAUTHORIZED"}}))); }
    state.refresh.lock().unwrap().remove(&p.refresh_token);
    (axum::http::StatusCode::OK, Json(json!({"status":"ok"})))
}

async fn me(State(state): State<AppState>, headers: HeaderMap) -> (axum::http::StatusCode, Json<serde_json::Value>) {
    let Some(user) = current_user(&headers, &state) else { return (axum::http::StatusCode::UNAUTHORIZED, Json(json!({"error":{"code":"UNAUTHORIZED"}}))); };
    (axum::http::StatusCode::OK, Json(json!({"username":user.username,"email":user.email,"role":user.role})))
}

async fn metrics(State(state): State<AppState>, headers: HeaderMap) -> (axum::http::StatusCode, Json<serde_json::Value>) {
    if current_user(&headers, &state).is_none() { return (axum::http::StatusCode::UNAUTHORIZED, Json(json!({"error":{"code":"UNAUTHORIZED"}}))); }
    let mut uptime = state.uptime.lock().unwrap(); *uptime += 1;
    (axum::http::StatusCode::OK, Json(json!({"temperatureC":25.0,"cpuLoadPercent":14.0,"ramLoadPercent":54.0,"uptimeSeconds":*uptime,"supplyVoltageV":12.2,"timestampUtc":chrono::Utc::now().to_rfc3339()})))
}

async fn status() -> Json<serde_json::Value> { Json(json!({"service":"ok","opcua":"simulated","cache":"ready"})) }

#[tokio::main]
async fn main() {
    let state = AppState::default();
    let app = Router::new()
        .route("/api/v1/auth/register", post(register))
        .route("/api/v1/auth/login", post(login))
        .route("/api/v1/auth/refresh", post(refresh))
        .route("/api/v1/auth/logout", post(logout))
        .route("/api/v1/auth/me", get(me))
        .route("/api/v1/metrics/current", get(metrics))
        .route("/api/v1/gateway/status", get(status))
        .with_state(state);
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3002").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
