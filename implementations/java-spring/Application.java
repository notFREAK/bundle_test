package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@SpringBootApplication
public class Application {
  public static void main(String[] args) {
    SpringApplication.run(Application.class, args);
  }

  @RestController
  @RequestMapping("/api/v1")
  static class ApiController {
    private final Map<String, User> users = new ConcurrentHashMap<>();
    private final Map<String, String> access = new ConcurrentHashMap<>();
    private final Map<String, String> refresh = new ConcurrentHashMap<>();
    private volatile long uptime = 0;

    @PostMapping("/auth/register")
    public ResponseEntity<?> register(@RequestBody Map<String, String> body) {
      String username = body.get("username");
      String password = body.get("password");
      String email = body.getOrDefault("email", username + "@example.local");
      if (username == null || password == null) return ResponseEntity.badRequest().build();
      if (users.containsKey(username)) return ResponseEntity.status(HttpStatus.CONFLICT).body(Map.of("error", Map.of("code", "CONFLICT")));
      users.put(username, new User(username, email, password, "viewer"));
      return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("status", "registered"));
    }

    @PostMapping("/auth/login")
    public ResponseEntity<?> login(@RequestBody Map<String, String> body) {
      User user = users.get(body.get("username"));
      if (user == null || !user.password().equals(body.get("password"))) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
      String at = UUID.randomUUID().toString().replace("-", "");
      String rt = UUID.randomUUID().toString().replace("-", "");
      access.put(at, user.username());
      refresh.put(rt, user.username());
      return ResponseEntity.ok(Map.of("accessToken", at, "refreshToken", rt));
    }

    @PostMapping("/auth/refresh")
    public ResponseEntity<?> refresh(@RequestBody Map<String, String> body) {
      String username = refresh.get(body.get("refreshToken"));
      if (username == null) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
      String at = UUID.randomUUID().toString().replace("-", "");
      access.put(at, username);
      return ResponseEntity.ok(Map.of("accessToken", at, "refreshToken", body.get("refreshToken")));
    }

    @PostMapping("/auth/logout")
    public ResponseEntity<?> logout(@RequestBody Map<String, String> body, @RequestHeader("Authorization") String auth) {
      if (currentUser(auth) == null) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
      refresh.remove(body.get("refreshToken"));
      return ResponseEntity.ok(Map.of("status", "ok"));
    }

    @GetMapping("/auth/me")
    public ResponseEntity<?> me(@RequestHeader("Authorization") String auth) {
      User user = currentUser(auth);
      if (user == null) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
      return ResponseEntity.ok(Map.of("username", user.username(), "email", user.email(), "role", user.role()));
    }

    @GetMapping("/metrics/current")
    public ResponseEntity<?> metrics(@RequestHeader("Authorization") String auth){
      if (currentUser(auth) == null) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build();
      uptime++;
      return ResponseEntity.ok(Map.of("temperatureC",25.0,"cpuLoadPercent",20.0,"ramLoadPercent",40.0,"uptimeSeconds",uptime,"supplyVoltageV",12.2,"timestampUtc", Instant.now().toString()));
    }

    @GetMapping("/gateway/status")
    public Map<String,Object> status(){ return Map.of("service","ok","opcua","simulated","cache","ready"); }

    private User currentUser(String authorization) {
      if (authorization == null || !authorization.startsWith("Bearer ")) return null;
      String token = authorization.substring("Bearer ".length());
      String username = access.get(token);
      return username == null ? null : users.get(username);
    }
  }

  record User(String username, String email, String password, String role) {}
}
