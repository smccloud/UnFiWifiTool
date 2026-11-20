/*
 * CI pipeline for UniFi WiFi Access Manager.
 *
 * Requirements on the Jenkins agent:
 *   - Docker Engine / CLI (the agent user must be able to run docker)
 *   - Network access to Docker Hub, PyPI, and npm
 *
 * The pipeline does not push an image. It builds it, runs the backend and
 * frontend test suites, validates docker-compose, and boots the image twice to
 * verify both authentication modes.
 *
 * DOCKER_NETWORK defaults to "host" because it also works on restricted,
 * nested, or rootless CI agents where bridge/veth creation is unavailable.
 * Switch it to "default" if your policy requires build-network isolation.
 */

pipeline {
    agent any

    parameters {
        choice(
            name: 'DOCKER_NETWORK',
            choices: ['host', 'default'],
            description: 'Network mode for build and test containers. Use default for stricter isolation.'
        )
    }

    options {
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    environment {
        IMAGE             = "unifi-wifi-tool:${BUILD_NUMBER}"
        AUTH_CONTAINER    = "unifi-wifi-ci-auth-${BUILD_NUMBER}"
        SECURE_CONTAINER  = "unifi-wifi-ci-secure-${BUILD_NUMBER}"
        COMPOSE_PROJECT   = "unifi-wifi-ci-${BUILD_NUMBER}"
        DOCKER_NETWORK    = "${params.DOCKER_NETWORK ?: 'host'}"
        DOCKER_BUILDKIT   = "1"
        CI                = "true"
    }

    stages {
        stage('Validate toolchain') {
            steps {
                sh '''
                    set -eu
                    command -v docker >/dev/null 2>&1 || {
                        echo "ERROR: docker CLI is required on this Jenkins agent." >&2
                        exit 1
                    }
                    docker version
                    docker info --format '{{.ServerVersion}}'
                '''
            }
        }

        stage('Backend tests') {
            steps {
                sh '''
                    set -eu
                    rm -f backend/test-results.xml
                    docker run --rm \
                        --network "$DOCKER_NETWORK" \
                        -v "$WORKSPACE/backend:/src" \
                        -w /src \
                        -e AUTH_DISABLED=true \
                        -e DATABASE_URL=sqlite:////tmp/ci-test.db \
                        -e SECRET_KEY=jenkins-test-secret-key-0123456789 \
                        python:3.13-slim \
                        sh -ec "pip install --quiet --no-cache-dir -r requirements-dev.txt && pytest --junitxml=test-results.xml"
                '''
            }
        }

        stage('Frontend build') {
            steps {
                sh '''
                    set -eu
                    docker run --rm \
                        --network "$DOCKER_NETWORK" \
                        -v "$WORKSPACE/frontend:/src" \
                        -v "unifi-wifi-ci-node-modules-$BUILD_NUMBER:/src/node_modules" \
                        -w /src \
                        node:22-alpine \
                        sh -ec "npm ci --no-audit --no-fund && npm run build"
                '''
            }
        }

        stage('Docker build') {
            steps {
                sh '''
                    set -eu
                    docker build --pull --network "$DOCKER_NETWORK" -t "$IMAGE" .
                    docker image inspect "$IMAGE" > image-inspect.json
                '''
            }
            post {
                success {
                    archiveArtifacts artifacts: 'image-inspect.json', allowEmptyArchive: true
                }
            }
        }

        stage('Compose config') {
            steps {
                script {
                    def composeAvailable = sh(
                        script: 'docker compose version >/dev/null 2>&1',
                        returnStatus: true
                    ) == 0
                    if (composeAvailable) {
                        sh 'ENV_FILE=.env.example docker compose -p "$COMPOSE_PROJECT" config -q'
                    } else {
                        echo 'Docker Compose plugin not available; skipping compose validation.'
                    }
                }
            }
        }

        stage('Container smoke test') {
            steps {
                sh '''
                    set -eu

                    cleanup() {
                        docker rm -f "$AUTH_CONTAINER" "$SECURE_CONTAINER" >/dev/null 2>&1 || true
                    }
                    trap cleanup EXIT

                    echo "=== Starting unauthenticated smoke container ==="
                    # Network "none" keeps the test hermetic: all HTTP checks run
                    # inside the container with docker exec, so no host ports are
                    # published and no bridge is required.
                    docker run -d --name "$AUTH_CONTAINER" \
                        --network none \
                        -e AUTH_DISABLED=true \
                        -e SECRET_KEY=jenkins-smoke-secret-key-0123456789 \
                        -e SCHEDULER_ENABLED=false \
                        -e UNIFI_HOST= \
                        -e DATABASE_URL=sqlite:////tmp/smoke.db \
                        "$IMAGE" >/dev/null

                    ready=0
                    for i in $(seq 1 60); do
                        if docker exec "$AUTH_CONTAINER" python -c \
                            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/healthz', timeout=2)" \
                            >/dev/null 2>&1; then
                            ready=1
                            break
                        fi
                        sleep 1
                    done
                    if [ "$ready" -ne 1 ]; then
                        echo "ERROR: container did not become healthy" >&2
                        docker logs "$AUTH_CONTAINER"
                        exit 1
                    fi

                    docker exec "$AUTH_CONTAINER" python -c \
                        "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/healthz', timeout=3).read().decode())" \
                        | tee smoke-health.json
                    echo

                    # The multi-stage image must contain the built SPA, not the
                    # backend's "frontend not built" placeholder.
                    docker exec -i "$AUTH_CONTAINER" python - <<'PY'
import sys
import urllib.request

body = urllib.request.urlopen("http://127.0.0.1:8000/", timeout=3).read().decode()
if 'id="root"' not in body:
    print("ERROR: frontend index.html was not served", file=sys.stderr)
    sys.exit(1)
print("frontend index OK")
PY

                    docker exec -i "$AUTH_CONTAINER" python - <<'PY'
import sys
import urllib.request

response = urllib.request.urlopen("http://127.0.0.1:8000/api/system/status", timeout=5)
if response.getcode() != 200:
    print(f"ERROR: /api/system/status returned {response.getcode()}", file=sys.stderr)
    sys.exit(1)
print("status endpoint OK")
PY

                    if docker logs "$AUTH_CONTAINER" 2>&1 | grep -q "Traceback (most recent call last)"; then
                        echo "ERROR: traceback found in container logs" >&2
                        docker logs "$AUTH_CONTAINER"
                        exit 1
                    fi

                    docker stop "$AUTH_CONTAINER" >/dev/null

                    echo "=== Starting authenticated smoke container ==="
                    docker run -d --name "$SECURE_CONTAINER" \
                        --network none \
                        -e AUTH_DISABLED=false \
                        -e APP_USERNAME=admin \
                        -e APP_PASSWORD=ci-password \
                        -e SECRET_KEY=jenkins-smoke-secret-key-0123456789 \
                        -e SCHEDULER_ENABLED=false \
                        -e UNIFI_HOST= \
                        -e DATABASE_URL=sqlite:////tmp/secure.db \
                        "$IMAGE" >/dev/null

                    ready=0
                    for i in $(seq 1 60); do
                        if docker exec "$SECURE_CONTAINER" python -c \
                            "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/healthz', timeout=2)" \
                            >/dev/null 2>&1; then
                            ready=1
                            break
                        fi
                        sleep 1
                    done
                    if [ "$ready" -ne 1 ]; then
                        echo "ERROR: authenticated container did not become healthy" >&2
                        docker logs "$SECURE_CONTAINER"
                        exit 1
                    fi

                    # Exercise auth, CSRF, and the device API end-to-end.
                    docker exec -i "$SECURE_CONTAINER" python - <<'PY'
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"


def expect_http_error(request, code, label, opener=None):
    open_request = opener.open if opener else urllib.request.urlopen
    try:
        open_request(request, timeout=5)
    except urllib.error.HTTPError as exc:
        if exc.code != code:
            print(f"ERROR: {label} returned {exc.code}, expected {code}", file=sys.stderr)
            sys.exit(1)
        return
    print(f"ERROR: {label} unexpectedly succeeded", file=sys.stderr)
    sys.exit(1)


# 1. Unauthenticated API access is rejected.
expect_http_error(urllib.request.Request(BASE + "/api/devices"), 401, "unauthenticated /api/devices")

# 2. Wrong password is rejected.
wrong = urllib.request.Request(
    BASE + "/api/auth/login",
    data=json.dumps({"username": "admin", "password": "wrong"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
expect_http_error(wrong, 401, "wrong-password login")

# 3. Correct login returns a session cookie and CSRF token.
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
login = urllib.request.Request(
    BASE + "/api/auth/login",
    data=json.dumps({"username": "admin", "password": "ci-password"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with opener.open(login, timeout=5) as response:
    if response.getcode() != 200:
        print(f"ERROR: login returned {response.getcode()}", file=sys.stderr)
        sys.exit(1)
    payload = json.loads(response.read())
csrf = payload.get("csrf_token")
if not csrf:
    print("ERROR: login response missing csrf_token", file=sys.stderr)
    sys.exit(1)

# 4. Authenticated read works.
with opener.open(urllib.request.Request(BASE + "/api/devices"), timeout=5) as response:
    if response.getcode() != 200:
        print(f"ERROR: authenticated /api/devices returned {response.getcode()}", file=sys.stderr)
        sys.exit(1)

# 5. Mutation without CSRF is rejected.
no_csrf = urllib.request.Request(
    BASE + "/api/devices",
    data=json.dumps({"mac": "aa:bb:cc:dd:ee:01", "label": "ci"}).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
expect_http_error(no_csrf, 403, "mutation without CSRF token", opener)

# 6. Mutation with CSRF succeeds.
with_csrf = urllib.request.Request(
    BASE + "/api/devices",
    data=json.dumps({"mac": "aa:bb:cc:dd:ee:01", "label": "ci"}).encode(),
    headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
    method="POST",
)
with opener.open(with_csrf, timeout=5) as response:
    if response.getcode() != 201:
        print(f"ERROR: device create returned {response.getcode()}", file=sys.stderr)
        sys.exit(1)
    created = json.loads(response.read())
if created.get("mac") != "aa:bb:cc:dd:ee:01":
    print(f"ERROR: unexpected created device: {created}", file=sys.stderr)
    sys.exit(1)

print("auth/CSRF/device API smoke test OK")
PY

                    echo "=== Smoke tests passed ==="
                '''
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'backend/test-results.xml'
            archiveArtifacts artifacts: 'image-inspect.json, smoke-health.json', allowEmptyArchive: true
            sh '''
                docker rm -f "$AUTH_CONTAINER" "$SECURE_CONTAINER" >/dev/null 2>&1 || true
                docker volume rm "unifi-wifi-ci-node-modules-$BUILD_NUMBER" >/dev/null 2>&1 || true
                docker rmi "$IMAGE" >/dev/null 2>&1 || true
                rm -f smoke-cookies.txt smoke-login.json
            '''
        }
        failure {
            sh '''
                echo "--- unauthenticated container logs ---"
                docker logs "$AUTH_CONTAINER" 2>&1 || true
                echo "--- authenticated container logs ---"
                docker logs "$SECURE_CONTAINER" 2>&1 || true
            '''
        }
    }
}
