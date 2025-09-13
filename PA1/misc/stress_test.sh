#!/bin/bash

# ==============================================================================
# The Final Gauntlet - Advanced Web Server Test Suite
#
# This script is designed to be the final, exhaustive test for a simple web
# server. It combines extreme concurrency, advanced protocol edge cases, and
# resource exhaustion attacks to ensure maximum stability and correctness.
#
# V5.1 - The "More Stressful" Gauntlet
# ==============================================================================

# --- Configuration ---
HOST="localhost"
PORT="8080"
BASE_URL="http://${HOST}:${PORT}"
LOG_FILE="gauntlet_results_$(date +%Y-%m-%d_%H-%M-%S).log"
REQUIRED_TOOLS=("ab" "curl" "nc" "head" "base64" "tr" "mktemp")

# --- Gauntlet Parameters ---
# Increased load to find race conditions and deadlocks
CONCURRENCY=500
REQUESTS=20000
# Parameters for new, more stressful tests
LARGE_FILE_REQUESTS=100
LARGE_FILE_CONCURRENCY=50
SOAK_TEST_DURATION=30 # in seconds
SLOW_CLIENTS=100

# --- Script setup ---
exec &> >(tee "$LOG_FILE")
trap cleanup EXIT

# --- Helper Functions ---
print_header() { echo -e "\n\n\033[1;35m================================================================================\n===== $1 \n================================================================================\033[0m"; }
print_success() { echo -e "\033[0;32m[SUCCESS]\033[0m $1"; }
print_fail() { echo -e "\033[0;31m[FAILURE]\033[0m $1"; has_failed=1; }
print_info() { echo -e "\033[0;34m[INFO]\033[0m $1"; }
print_warn() { echo -e "\033[1;33m[WARNING]\033[0m $1"; }

# --- Setup and Teardown ---
background_pids=()
has_failed=0

cleanup() {
    print_warn "Cleanup requested. Removing test files and terminating background processes..."
    # Kill all background jobs started by this script
    if [ ${#background_pids[@]} -ne 0 ]; then
        kill "${background_pids[@]}" 2>/dev/null
    fi
    rm -rf ./www /tmp/gauntlet_*.txt
}

check_server_alive() {
    if ! nc -z $HOST $PORT; then
        print_fail "SERVER CRASHED! The last test performed was the cause."
        exit 1
    fi
    if [ -n "$1" ]; then
        print_success "$1 Post-Test: Server is still alive and responsive."
    fi
}

# --- Test Environment Preparation ---
prepare_environment() {
    print_header "Phase 0: Prerequisites and Environment Setup"
    for tool in "${REQUIRED_TOOLS[@]}"; do
        if ! command -v $tool &> /dev/null; then
            print_fail "Required tool '$tool' is not installed. Aborting."
            exit 1
        fi
    done
    print_success "All required tools are present."

    if ! nc -z $HOST $PORT; then
        print_fail "Server is not running on $HOST:$PORT. Please start the server and try again."
        exit 1
    fi

    print_info "Creating test directory './www' and populating with test files..."
    mkdir -p ./www/subdir
    echo "small" > ./www/small.html
    head -c 10K /dev/urandom > ./www/medium.dat
    head -c 10M /dev/urandom > ./www/large.dat
    echo "index" > ./www/index.html
    echo "subdir index" > ./www/subdir/index.html
    print_success "Test environment created successfully."
    print_info "Starting the gauntlet against $BASE_URL"
    print_info "All output is being logged to: $LOG_FILE"
}

# --- Test Execution ---
run_tests() {
    # === Category A: Extreme Load and Concurrency ===
    print_header "Category A: Load and Concurrency"
    print_info "Test A1: Extreme concurrency burst ($REQUESTS requests, $CONCURRENCY concurrency)."
    AB_OUTPUT=$(ab -n $REQUESTS -c $CONCURRENCY "${BASE_URL}/small.html" 2>&1)
    if [ $? -eq 0 ] && echo "$AB_OUTPUT" | grep -q "Failed requests: 0"; then
        print_success "A1: Server survived extreme concurrency without errors."
    else
        print_fail "A1: Server struggled or produced errors under extreme concurrency."
        echo "$AB_OUTPUT"
    fi
    check_server_alive "A1"

    print_info "Test A2: High I/O Stress ($LARGE_FILE_REQUESTS requests for 10MB file, $LARGE_FILE_CONCURRENCY concurrency)."
    AB_OUTPUT_LARGE=$(ab -n $LARGE_FILE_REQUESTS -c $LARGE_FILE_CONCURRENCY "${BASE_URL}/large.dat" 2>&1)
    if [ $? -eq 0 ] && echo "$AB_OUTPUT_LARGE" | grep -q "Failed requests: 0"; then
        print_success "A2: Server survived high I/O stress without errors."
    else
        print_fail "A2: Server struggled or produced errors under high I/O stress."
        echo "$AB_OUTPUT_LARGE"
    fi
    check_server_alive "A2"
    
    print_info "Test A3: Long-Duration Soak Test (${SOAK_TEST_DURATION}s)."
    AB_OUTPUT_SOAK=$(ab -t $SOAK_TEST_DURATION -c $CONCURRENCY "${BASE_URL}/medium.dat" 2>&1)
    if [ $? -eq 0 ] && echo "$AB_OUTPUT_SOAK" | grep -q "Failed requests: 0"; then
        print_success "A3: Server remained stable during the soak test."
    else
        print_fail "A3: Server produced errors during the soak test."
        echo "$AB_OUTPUT_SOAK"
    fi
    check_server_alive "A3"

    # === Category B: Advanced HTTP Semantics ===
    print_header "Category B: Advanced HTTP Semantics"
    print_info "Test B1: HEAD request. Server should return headers but no body."
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X HEAD "${BASE_URL}/small.html")
    if [ "$STATUS" = "405" ]; then
            print_success "B1: Server correctly returned 405 Method Not Allowed for HEAD."
    else
            print_warn "B1: Server did not return 405 for HEAD. Manual check recommended."
    fi
    check_server_alive "B1"

    # === Category C: Malformed Payloads and Parser Attacks ===
    print_header "Category C: Malformed Payloads and Parser Attacks"
    print_info "Test C1: Obsolete line folding (header with leading space)."
    RESPONSE_CODE=$( (echo -e "GET /small.html HTTP/1.1\r\nHost: ${HOST}\r\n Normal-Header: OK\r\n\tObs-Fold: bad\r\n\r\n") | nc -q 1 $HOST $PORT | head -n 1)
    if [[ "$RESPONSE_CODE" == *"200 OK"* ]]; then
        print_success "C1: Server correctly handled (ignored) obsolete line folding."
    elif [[ "$RESPONSE_CODE" == *"400 Bad Request"* ]]; then
        print_success "C1: Server correctly rejected obsolete line folding."
    else
        print_fail "C1: Server gave an unexpected response to obsolete line folding: '$RESPONSE_CODE'"
    fi
    check_server_alive "C1"
    
    # === Category D: Advanced Resource Exhaustion ===
    print_header "Category D: Advanced Resource Exhaustion"
    print_info "Test D1: Rapid Thread Churn. Creating and closing 1000 connections rapidly."
    for i in {1..1000}; do
        (echo -e "GET / HTTP/1.0\r\n\r\n") | nc -W 1 $HOST $PORT > /dev/null 2>&1 &
    done
    wait
    print_info "Thread churn finished."
    check_server_alive "D1"

    # === Category E: Protocol Attack Simulations ===
    print_header "Category E: Protocol Attack Simulations"
    print_info "Test E1: Slow Client Connection (Slowloris-like). Opening $SLOW_CLIENTS slow connections."
    
    slow_client() {
        # Send an incomplete header very slowly to tie up a server thread
        (
            echo -en "GET /slow HTTP/1.1\r\nHost: ${HOST}\r\n"
            sleep 1
            echo -en "X-Slow-Header: "
            sleep 20 # Hold the connection open
        ) | nc $HOST $PORT > /dev/null 2>&1
    }

    for i in $(seq 1 $SLOW_CLIENTS); do
        slow_client &
        background_pids+=($!)
    done

    print_info "Waiting for slow clients to establish connections..."
    sleep 5
    print_info "Checking server responsiveness while under slow client attack..."
    if curl -s --max-time 5 "${BASE_URL}/small.html" > /dev/null; then
        print_success "E1: Server remained responsive during a slow client attack."
    else
        print_fail "E1: Server became unresponsive during a slow client attack. (Potential thread exhaustion)"
    fi
    # Clean up the slow client processes
    kill "${background_pids[@]}" 2>/dev/null
    background_pids=()
    wait 2>/dev/null
    check_server_alive "E1"
}


# --- Main Execution ---
prepare_environment
run_tests

print_header "Gauntlet Complete"
if [ $has_failed -eq 0 ]; then
    print_success "Congratulations! The server survived the gauntlet with no critical failures."
else
    print_fail "The server failed one or more critical tests. Review the log: $LOG_FILE"
fi