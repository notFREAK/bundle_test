using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;

var builder = WebApplication.CreateBuilder(args);
var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(Environment.GetEnvironmentVariable("JWT_SECRET") ?? "dev-secret-32-characters-minimum!!!"));
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(o => o.TokenValidationParameters = new TokenValidationParameters {
        ValidateIssuer = false, ValidateAudience = false, ValidateIssuerSigningKey = true, IssuerSigningKey = key
    });
builder.Services.AddAuthorization();

var app = builder.Build();
app.UseAuthentication();
app.UseAuthorization();

var users = new Dictionary<string, (string password, string email, string role)>();
var refresh = new Dictionary<string, string>();
var snapshot = new Dictionary<string, object> {
    ["temperatureC"] = 25.0, ["cpuLoadPercent"] = 42.0, ["ramLoadPercent"] = 53.0,
    ["uptimeSeconds"] = 1, ["supplyVoltageV"] = 12.0, ["timestampUtc"] = DateTime.UtcNow.ToString("O")
};

string tokenFor(string username, string role = "viewer") {
    var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);
    var jwt = new JwtSecurityToken(claims: new[] { new Claim("sub", username), new Claim("role", role) }, expires: DateTime.UtcNow.AddMinutes(15), signingCredentials: creds);
    return new JwtSecurityTokenHandler().WriteToken(jwt);
}

app.MapPost("/api/v1/auth/register", (dynamic body) => {
    string username = body.username; string password = body.password; string email = body.email;
    if (users.ContainsKey(username)) return Results.Conflict(new { error = new { code = "CONFLICT" } });
    users[username] = (password, email, "viewer");
    return Results.Created($"/api/v1/users/{username}", new { status = "registered" });
});
app.MapPost("/api/v1/auth/login", (dynamic body) => {
    string username = body.username; string password = body.password;
    return users.TryGetValue(username, out var u) && u.password == password
        ? Results.Ok(new { accessToken = tokenFor(username, u.role), refreshToken = Guid.NewGuid().ToString("N") })
        : Results.Unauthorized();
});
app.MapPost("/api/v1/auth/refresh", (dynamic body) => Results.Ok(new { accessToken = tokenFor("viewer"), refreshToken = (string)body.refreshToken }));
app.MapPost("/api/v1/auth/logout", () => Results.Ok(new { status = "ok" })).RequireAuthorization();
app.MapGet("/api/v1/auth/me", (ClaimsPrincipal u) => Results.Ok(new { username = u.FindFirst("sub")?.Value, role = u.FindFirst("role")?.Value })).RequireAuthorization();
app.MapGet("/api/v1/metrics/current", () => Results.Ok(snapshot)).RequireAuthorization();
app.MapGet("/api/v1/gateway/status", () => Results.Ok(new { service = "ok", opcua = "simulated", cache = "ready" }));

_ = Task.Run(async () => {
    while (true) {
        snapshot["uptimeSeconds"] = (int)snapshot["uptimeSeconds"] + 1;
        snapshot["timestampUtc"] = DateTime.UtcNow.ToString("O");
        await Task.Delay(1000);
    }
});

app.Run();
