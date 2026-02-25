package com.example.gateway

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.http.HttpStatus
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.*
import java.time.Instant
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

@SpringBootApplication
class Application
fun main(args: Array<String>) = runApplication<Application>(*args)

data class User(val username: String, val email: String, val password: String, val role: String = "viewer")

@RestController
@RequestMapping("/api/v1")
class ApiController {
    private val users = ConcurrentHashMap<String, User>()
    private val access = ConcurrentHashMap<String, String>()
    private val refresh = ConcurrentHashMap<String, String>()
    private var uptime: Long = 0

    @PostMapping("/auth/register")
    fun register(@RequestBody body: Map<String, String>): ResponseEntity<Any> {
        val username = body["username"] ?: return ResponseEntity.badRequest().build()
        val password = body["password"] ?: return ResponseEntity.badRequest().build()
        if (users.containsKey(username)) return ResponseEntity.status(HttpStatus.CONFLICT).body(mapOf("error" to mapOf("code" to "CONFLICT")))
        users[username] = User(username, body["email"] ?: "$username@example.local", password)
        return ResponseEntity.status(HttpStatus.CREATED).body(mapOf("status" to "registered"))
    }

    @PostMapping("/auth/login")
    fun login(@RequestBody body: Map<String, String>): ResponseEntity<Any> {
        val user = users[body["username"]] ?: return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build()
        if (user.password != body["password"]) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build()
        val at = UUID.randomUUID().toString().replace("-", "")
        val rt = UUID.randomUUID().toString().replace("-", "")
        access[at] = user.username
        refresh[rt] = user.username
        return ResponseEntity.ok(mapOf("accessToken" to at, "refreshToken" to rt))
    }

    @PostMapping("/auth/refresh")
    fun refreshToken(@RequestBody body: Map<String, String>): ResponseEntity<Any> {
        val username = refresh[body["refreshToken"]] ?: return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build()
        val at = UUID.randomUUID().toString().replace("-", "")
        access[at] = username
        return ResponseEntity.ok(mapOf("accessToken" to at, "refreshToken" to body["refreshToken"]))
    }

    @PostMapping("/auth/logout")
    fun logout(@RequestBody body: Map<String, String>, @RequestHeader("Authorization") auth: String?): ResponseEntity<Any> {
        if (currentUser(auth) == null) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build()
        refresh.remove(body["refreshToken"])
        return ResponseEntity.ok(mapOf("status" to "ok"))
    }

    @GetMapping("/auth/me")
    fun me(@RequestHeader("Authorization") auth: String?): ResponseEntity<Any> {
        val user = currentUser(auth) ?: return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build()
        return ResponseEntity.ok(mapOf("username" to user.username, "email" to user.email, "role" to user.role))
    }

    @GetMapping("/metrics/current")
    fun metrics(@RequestHeader("Authorization") auth: String?): ResponseEntity<Any> {
        if (currentUser(auth) == null) return ResponseEntity.status(HttpStatus.UNAUTHORIZED).build()
        uptime += 1
        return ResponseEntity.ok(mapOf("temperatureC" to 25.0, "cpuLoadPercent" to 22.0, "ramLoadPercent" to 51.0, "uptimeSeconds" to uptime, "supplyVoltageV" to 12.1, "timestampUtc" to Instant.now().toString()))
    }

    @GetMapping("/gateway/status")
    fun status() = mapOf("service" to "ok", "opcua" to "simulated", "cache" to "ready")

    private fun currentUser(auth: String?): User? {
        if (auth == null || !auth.startsWith("Bearer ")) return null
        return users[access[auth.removePrefix("Bearer ")] ?: return null]
    }
}
