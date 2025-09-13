#!/bin/bash

# --- Configuration ---
HOST="localhost"
PORT="8080"
LOG_FILE="test_results.log"
WWW_DIR="./www"
# --- End Configuration ---

# This function prints a header, then executes the command that follows
run_test() {
  echo "===== $1 ====="
  # The shift command removes the first argument ($1), 
  # so $@ now contains only the actual command to run.
  shift
  "$@"
  echo ""
  echo ""
}

# --- Test Setup ---
# Creates a test directory and a file with no read permissions.
setup_tests() {
  echo "--- Setting up test environment ---"
  # Create a test subdirectory for the directory index test
  mkdir -p "$WWW_DIR/testdir"
  echo "<h1>Subdirectory Index</h1>" > "$WWW_DIR/testdir/index.html"

  # Create a file and remove read permissions for the 403 test
  echo "This file is forbidden." > "$WWW_DIR/forbidden.html"
  chmod 200 "$WWW_DIR/forbidden.html" # Write-only permissions
  echo "--- Setup complete ---"
  echo ""
}

# --- Test Teardown ---
# Cleans up the files and directories created during setup.
teardown_tests() {
  echo "--- Tearing down test environment ---"
  rm -rf "$WWW_DIR/testdir"
  rm -f "$WWW_DIR/forbidden.html"
  echo "--- Teardown complete ---"
}

# --- Main Script ---

# Redirect all output from this point forward to the log file
exec > "$LOG_FILE" 2>&1

# Run setup
setup_tests

echo "===== SERVER TEST SUITE RUNNING ====="
echo "Date: $(date)"
echo "Target: http://$HOST:$PORT"
echo "====================================="
echo ""

# --- Core Functionality Tests ---
run_test "Test 1: Basic GET for index.html" curl -v "http://$HOST:$PORT/"
run_test "Test 2: Serving an Image" curl -v "http://$HOST:$PORT/images/welcome.png" -o /dev/null
run_test "Test 3: Default Directory Page" curl -v "http://$HOST:$PORT/testdir/"

# --- Error Handling Tests ---
run_test "Test 4: 404 Not Found Error" curl -v "http://$HOST:$PORT/nonexistent-file.html"
run_test "Test 5: 405 Method Not Allowed" curl -v -X POST "http://$HOST:$PORT/index.html"
run_test "Test 6: 403 Forbidden (File Permissions)" curl -v "http://$HOST:$PORT/forbidden.html"

# CHANGED: Replaced curl with nc to send a literal unsupported HTTP version string.
echo "===== Test 7: 505 HTTP Version Not Supported ====="
echo -e "Sending request:\nGET / HTTP/2.0\r\nHost: $HOST:$PORT\r\n"
(echo -en "GET / HTTP/2.0\r\nHost: $HOST:$PORT\r\n\r\n") | nc $HOST $PORT
echo ""
echo ""

# --- Security Tests ---
# CHANGED: Renamed test from "400 Bad Request" to "403 Forbidden" to reflect the correct expected error.
run_test "Test 8: 403 Forbidden (Path Traversal)" curl -v "http://$HOST:$PORT/../server.c"
run_test "Test 9: 403 Forbidden (Absolute Path)" curl -v "http://$HOST:$PORT/etc/passwd"

# --- Protocol and Connection Tests ---
run_test "Test 10: HTTP/1.0 Request" curl -v --http1.0 "http://$HOST:$PORT/"

echo "===== Test 11: Pipelining Test ====="
# Sends two requests back-to-back without waiting. The server should process both.
# The second request uses "Connection: close" to terminate.
REQUEST_DATA="GET /index.html HTTP/1.1\r\nHost: $HOST:$PORT\r\nConnection: keep-alive\r\n\r\nGET /css/style.css HTTP/1.1\r\nHost: $HOST:$PORT\r\nConnection: close\r\n\r\n"
# CHANGED: Added logging to show the exact request being sent.
echo -e "Sending pipelined request:\n$REQUEST_DATA"
(echo -en "$REQUEST_DATA") | nc $HOST $PORT
echo ""
echo ""

echo "===== TESTS COMPLETE ====="

# Run teardown
teardown_tests

# Stop redirecting output and print the final message to the console
exec >/dev/tty 2>&1

echo "All tests have been run. Results are in the file: $LOG_FILE"