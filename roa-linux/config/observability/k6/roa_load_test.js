// =============================================================================
// k6 Load Test for ROA Components
// =============================================================================

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Rate, Trend, Gauge } from 'k6/metrics';

// =============================================================================
// Custom Metrics
// =============================================================================

const roaErrors = new Counter('roa_errors_total');
const roaLatency = new Trend('roa_request_latency_ms');
const roaSuccessRate = new Rate('roa_success_rate');
const roaActiveConnections = new Gauge('roa_active_connections');

// =============================================================================
// Test Configuration
// =============================================================================

export const options = {
    scenarios: {
        // Smoke test - verify basic functionality
        smoke: {
            executor: 'constant-vus',
            vus: 1,
            duration: '1m',
            startTime: '0s',
            tags: { scenario: 'smoke' },
        },
        // Load test - normal load
        load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 10 },   // Ramp up
                { duration: '5m', target: 10 },   // Hold
                { duration: '2m', target: 0 },    // Ramp down
            ],
            startTime: '1m',
            tags: { scenario: 'load' },
        },
        // Stress test - find breaking point
        stress: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '2m', target: 20 },
                { duration: '3m', target: 50 },
                { duration: '2m', target: 100 },
                { duration: '3m', target: 100 },
                { duration: '2m', target: 0 },
            ],
            startTime: '10m',
            tags: { scenario: 'stress' },
        },
    },
    thresholds: {
        // Response time
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        
        // Success rate
        roa_success_rate: ['rate>0.95'],
        
        // Error rate
        roa_errors_total: ['count<100'],
        
        // Custom latency
        roa_request_latency_ms: ['p(95)<400'],
    },
};

// =============================================================================
// Configuration
// =============================================================================

const BASE_URL = __ENV.ROA_URL || 'http://localhost:9800';
const WEBTHREAD_URL = __ENV.WEBTHREAD_URL || `${BASE_URL}`;
const FTI_URL = __ENV.FTI_URL || 'http://localhost:9801';
const DIMC_URL = __ENV.DIMC_URL || 'http://localhost:9802';

// =============================================================================
// Helper Functions
// =============================================================================

function checkResponse(res, name) {
    const success = check(res, {
        [`${name} status is 200`]: (r) => r.status === 200,
        [`${name} response time < 500ms`]: (r) => r.timings.duration < 500,
        [`${name} has body`]: (r) => r.body && r.body.length > 0,
    });
    
    roaLatency.add(res.timings.duration);
    
    if (success) {
        roaSuccessRate.add(1);
    } else {
        roaErrors.add(1);
        roaSuccessRate.add(0);
    }
    
    return success;
}

// =============================================================================
// Test Scenarios
// =============================================================================

export default function () {
    roaActiveConnections.add(1);
    
    group('Webthread API', function () {
        // Health check
        let healthRes = http.get(`${WEBTHREAD_URL}/api/health`, {
            tags: { endpoint: 'health' },
        });
        checkResponse(healthRes, 'health');
        
        // Status endpoint
        let statusRes = http.get(`${WEBTHREAD_URL}/api/status`, {
            tags: { endpoint: 'status' },
        });
        checkResponse(statusRes, 'status');
        
        // Heartbeat status
        let hbRes = http.get(`${WEBTHREAD_URL}/api/heartbeat`, {
            tags: { endpoint: 'heartbeat' },
        });
        checkResponse(hbRes, 'heartbeat');
        
        // Component list
        let componentsRes = http.get(`${WEBTHREAD_URL}/api/components`, {
            tags: { endpoint: 'components' },
        });
        checkResponse(componentsRes, 'components');
    });
    
    group('FTI API', function () {
        // Telemetry data
        let telemetryRes = http.get(`${FTI_URL}/api/telemetry`, {
            tags: { endpoint: 'telemetry' },
        });
        checkResponse(telemetryRes, 'telemetry');
        
        // Metrics
        let metricsRes = http.get(`${FTI_URL}/metrics`, {
            tags: { endpoint: 'fti-metrics' },
        });
        checkResponse(metricsRes, 'fti-metrics');
    });
    
    group('DIMC API', function () {
        // Command queue
        let queueRes = http.get(`${DIMC_URL}/api/queue`, {
            tags: { endpoint: 'queue' },
        });
        checkResponse(queueRes, 'queue');
        
        // Post a test command
        let cmdPayload = JSON.stringify({
            command: 'status',
            params: {},
            priority: 'normal',
        });
        
        let cmdRes = http.post(`${DIMC_URL}/api/command`, cmdPayload, {
            headers: { 'Content-Type': 'application/json' },
            tags: { endpoint: 'command' },
        });
        checkResponse(cmdRes, 'command');
    });
    
    roaActiveConnections.add(-1);
    
    // Think time
    sleep(Math.random() * 2 + 1);
}

// =============================================================================
// Setup and Teardown
// =============================================================================

export function setup() {
    console.log('Starting ROA load test...');
    console.log(`Target URLs:`);
    console.log(`  Webthread: ${WEBTHREAD_URL}`);
    console.log(`  FTI: ${FTI_URL}`);
    console.log(`  DIMC: ${DIMC_URL}`);
    
    // Verify services are reachable
    const healthCheck = http.get(`${WEBTHREAD_URL}/api/health`);
    if (healthCheck.status !== 200) {
        console.warn('Warning: Webthread health check failed');
    }
    
    return { startTime: new Date().toISOString() };
}

export function teardown(data) {
    console.log(`Test started at: ${data.startTime}`);
    console.log(`Test ended at: ${new Date().toISOString()}`);
}

// =============================================================================
// Summary Handler
// =============================================================================

export function handleSummary(data) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    
    return {
        'stdout': textSummary(data, { indent: ' ', enableColors: true }),
        [`k6_summary_${timestamp}.json`]: JSON.stringify(data, null, 2),
    };
}

// Helper for text summary (built-in)
function textSummary(data, options) {
    // k6 provides this automatically, but we can customize if needed
    return JSON.stringify(data.metrics, null, 2);
}
