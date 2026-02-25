<?php
use Illuminate\Support\Facades\Route;

Route::prefix('api/v1')->group(function () {
    Route::get('/metrics/current', fn () => response()->json([
        'temperatureC' => 25.0,
        'cpuLoadPercent' => 18.0,
        'ramLoadPercent' => 43.0,
        'uptimeSeconds' => 8,
        'supplyVoltageV' => 12.0,
        'timestampUtc' => now()->toIso8601String(),
    ]));
    Route::get('/gateway/status', fn () => response()->json(['service' => 'ok', 'opcua' => 'simulated', 'cache' => 'ready']));
});
