package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"sync"
	"time"
)

type User struct {
	Username string `json:"username"`
	Email    string `json:"email"`
	Password string
	Role     string `json:"role"`
}

type Metrics struct {
	TemperatureC   float64 `json:"temperatureC"`
	CpuLoadPercent float64 `json:"cpuLoadPercent"`
	RamLoadPercent float64 `json:"ramLoadPercent"`
	UptimeSeconds  int64   `json:"uptimeSeconds"`
	SupplyVoltageV float64 `json:"supplyVoltageV"`
	TimestampUtc   string  `json:"timestampUtc"`
}

var (
	usersMu sync.RWMutex
	users   = map[string]User{}
	tokens  = map[string]string{}
)

func newToken() string {
	buf := make([]byte, 24)
	_, _ = rand.Read(buf)
	return hex.EncodeToString(buf)
}

func authUser(r *http.Request) (User, bool) {
	h := r.Header.Get("Authorization")
	if len(h) < 8 || h[:7] != "Bearer " {
		return User{}, false
	}
	t := h[7:]
	usersMu.RLock()
	defer usersMu.RUnlock()
	u, ok := users[tokens[t]]
	return u, ok
}

func main() {
	snapshot := Metrics{25.1, 12.3, 44.2, 7, 12.1, time.Now().UTC().Format(time.RFC3339)}

	http.HandleFunc("/api/v1/auth/register", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost { w.WriteHeader(http.StatusMethodNotAllowed); return }
		var p map[string]string
		_ = json.NewDecoder(r.Body).Decode(&p)
		u := User{Username: p["username"], Email: p["email"], Password: p["password"], Role: "viewer"}
		if u.Username == "" || u.Password == "" { w.WriteHeader(http.StatusBadRequest); return }
		usersMu.Lock(); users[u.Username] = u; usersMu.Unlock()
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "registered"})
	})

	http.HandleFunc("/api/v1/auth/login", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost { w.WriteHeader(http.StatusMethodNotAllowed); return }
		var p map[string]string
		_ = json.NewDecoder(r.Body).Decode(&p)
		usersMu.RLock(); u, ok := users[p["username"]]; usersMu.RUnlock()
		if !ok || u.Password != p["password"] { w.WriteHeader(http.StatusUnauthorized); return }
		at, rt := newToken(), newToken()
		usersMu.Lock(); tokens[at] = u.Username; tokens[rt] = u.Username; usersMu.Unlock()
		_ = json.NewEncoder(w).Encode(map[string]string{"accessToken": at, "refreshToken": rt})
	})

	http.HandleFunc("/api/v1/auth/refresh", func(w http.ResponseWriter, r *http.Request) {
		var p map[string]string
		_ = json.NewDecoder(r.Body).Decode(&p)
		usersMu.RLock(); uname, ok := tokens[p["refreshToken"]]; usersMu.RUnlock()
		if !ok { w.WriteHeader(http.StatusUnauthorized); return }
		at := newToken(); usersMu.Lock(); tokens[at] = uname; usersMu.Unlock()
		_ = json.NewEncoder(w).Encode(map[string]string{"accessToken": at, "refreshToken": p["refreshToken"]})
	})

	http.HandleFunc("/api/v1/auth/logout", func(w http.ResponseWriter, r *http.Request) {
		var p map[string]string
		_ = json.NewDecoder(r.Body).Decode(&p)
		usersMu.Lock(); delete(tokens, p["refreshToken"]); usersMu.Unlock()
		w.WriteHeader(http.StatusOK)
	})

	http.HandleFunc("/api/v1/auth/me", func(w http.ResponseWriter, r *http.Request) {
		u, ok := authUser(r); if !ok { w.WriteHeader(http.StatusUnauthorized); return }
		_ = json.NewEncoder(w).Encode(map[string]string{"username": u.Username, "email": u.Email, "role": u.Role})
	})

	http.HandleFunc("/api/v1/metrics/current", func(w http.ResponseWriter, r *http.Request) {
		if _, ok := authUser(r); !ok { w.WriteHeader(http.StatusUnauthorized); return }
		_ = json.NewEncoder(w).Encode(snapshot)
	})
	http.HandleFunc("/api/v1/gateway/status", func(w http.ResponseWriter, r *http.Request) { _ = json.NewEncoder(w).Encode(map[string]any{"service": "ok", "opcua": "simulated", "cache": "ready"}) })
	_ = http.ListenAndServe(":8080", nil)
}
