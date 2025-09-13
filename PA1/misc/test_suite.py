#!/usr/bin/env python3
"""
Improved Test Suite for HTTP Server
Better handling of HTTP responses and more reliable testing.

Usage: python3 improved_test_suite.py [server_host] [server_port]
Default: localhost:8080
"""

import socket
import threading
import time
import sys
import os
import subprocess
import signal
import random
import string
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
import statistics
from datetime import datetime # Added for timestamped log files

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

    @classmethod
    def disable(cls):
        """Disable all color codes by setting them to empty strings."""
        cls.GREEN = ''
        cls.RED = ''
        cls.YELLOW = ''
        cls.BLUE = ''
        cls.PURPLE = ''
        cls.CYAN = ''
        cls.END = ''
        cls.BOLD = ''

class HTTPResponse:
    """Simple HTTP response parser"""
    def __init__(self, raw_response):
        self.raw = raw_response
        self.status_code = None
        self.status_message = None
        self.headers = {}
        self.body = ""
        self._parse()
    
    def _parse(self):
        if not self.raw:
            return
        
        try:
            # Split headers and body
            parts = self.raw.split('\r\n\r\n', 1)
            header_section = parts[0]
            self.body = parts[1] if len(parts) > 1 else ""
            
            # Parse status line
            lines = header_section.split('\r\n')
            if lines:
                status_line = lines[0]
                parts = status_line.split(' ', 2)
                if len(parts) >= 2:
                    self.status_code = parts[1]
                    self.status_message = parts[2] if len(parts) > 2 else ""
                
                # Parse headers
                for line in lines[1:]:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        self.headers[key.strip().lower()] = value.strip()
        
        except Exception as e:
            print(f"Error parsing response: {e}")
    
    def get_header(self, name):
        return self.headers.get(name.lower(), "")
    
    def is_success(self):
        return self.status_code and self.status_code.startswith('2')
    
    def get_status(self):
        return f"{self.status_code} {self.status_message}" if self.status_code else "UNKNOWN"

class HTTPServerTester:
    def __init__(self, host='localhost', port=8080):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.test_results = []
        self.server_process = None
        
    def print_status(self, message, status='INFO'):
        """Print colored status messages"""
        colors = {
            'PASS': Colors.GREEN,
            'FAIL': Colors.RED,
            'WARN': Colors.YELLOW,
            'INFO': Colors.BLUE,
            'STRESS': Colors.PURPLE
        }
        print(f"{colors.get(status, Colors.BLUE)}[{status}]{Colors.END} {message}")
    
    def setup_test_environment(self):
        """Create test files and directories"""
        self.print_status("Setting up test environment...")
        
        # Create www directory structure
        os.makedirs('www/subdir', exist_ok=True)
        os.makedirs('www/images', exist_ok=True)
        
        # Create test files
        test_files = {
            'www/index.html': '''<!DOCTYPE html>
<html><head><title>Test Page</title></head>
<body><h1>Hello World</h1><p>This is a test page.</p></body></html>''',
            
            'www/test.css': '''body { color: blue; font-family: Arial; }
h1 { color: red; }''',
            
            'www/script.js': '''console.log("Hello from JavaScript!");
function testFunction() { return "test"; }''',
            
            'www/data.txt': 'This is a plain text file.\nLine 2\nLine 3',
            
            'www/subdir/page.html': '''<!DOCTYPE html>
<html><head><title>Subdir Page</title></head>
<body><h1>Subdirectory Page</h1></body></html>''',
            
            'www/large.html': '<html><body>' + 'A' * 50000 + '</body></html>',  # 50KB file
            
            'www/binary.dat': bytes([i % 256 for i in range(1000)])  # Binary data
        }
        
        for filepath, content in test_files.items():
            with open(filepath, 'wb' if isinstance(content, bytes) else 'w') as f:
                f.write(content)
        
        self.print_status("Test environment created", 'PASS')
    
    def start_server(self, server_executable='./server'):
        """Start the HTTP server for testing"""
        if not os.path.exists(server_executable):
            self.print_status(f"Server executable {server_executable} not found", 'FAIL')
            return False
        
        try:
            self.server_process = subprocess.Popen(
                [server_executable, str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            time.sleep(2)  # Give server time to start
            
            # Check if server is running
            if self.server_process.poll() is not None:
                stderr = self.server_process.stderr.read()
                self.print_status(f"Server failed to start: {stderr}", 'FAIL')
                return False
            
            self.print_status(f"Server started on {self.host}:{self.port}", 'PASS')
            return True
            
        except Exception as e:
            self.print_status(f"Failed to start server: {e}", 'FAIL')
            return False
    
    def stop_server(self):
        """Stop the HTTP server"""
        if self.server_process:
            # Send SIGTERM for graceful shutdown
            self.server_process.send_signal(signal.SIGTERM)
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()
            self.print_status("Server stopped", 'INFO')
    
    def send_http_request(self, method="GET", path="/", headers=None, body=None, timeout=5):
        """Send HTTP request and return parsed response"""
        if headers is None:
            headers = {}
        
        # Build request
        request_lines = [f"{method} {path} HTTP/1.1"]
        
        # Add default headers
        if 'host' not in [h.lower() for h in headers.keys()]:
            headers['Host'] = f"{self.host}:{self.port}"
        
        for key, value in headers.items():
            request_lines.append(f"{key}: {value}")
        
        request_lines.append("")  # Empty line before body
        
        if body:
            request_lines.append(body)
        
        request_lines.append("")  # Final empty line
        request_data = '\r\n'.join(request_lines)
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))
            
            sock.sendall(request_data.encode('utf-8'))
            
            # Receive response
            response_data = b""
            while True:
                try:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    response_data += chunk
                    
                    # Check if we have complete response
                    if b'\r\n\r\n' in response_data:
                        header_end = response_data.find(b'\r\n\r\n') + 4
                        headers_part = response_data[:header_end].decode('utf-8', errors='ignore')
                        
                        # Check for Content-Length
                        content_length = None
                        for line in headers_part.split('\r\n'):
                            if line.lower().startswith('content-length:'):
                                content_length = int(line.split(':', 1)[1].strip())
                                break
                        
                        if content_length is not None:
                            total_expected = header_end + content_length
                            if len(response_data) >= total_expected:
                                response_data = response_data[:total_expected]
                                break
                        else:
                            # No content-length, assume complete
                            break
                            
                except socket.timeout:
                    break
            
            sock.close()
            
            return HTTPResponse(response_data.decode('utf-8', errors='ignore'))
            
        except Exception as e:
            return HTTPResponse(f"ERROR: {str(e)}")
    
    def test_basic_functionality(self):
        """Test basic HTTP server functionality"""
        self.print_status("=== BASIC FUNCTIONALITY TESTS ===", 'INFO')
        
        tests = [
            ("GET index.html", "/", "Hello World"),
            ("GET CSS file", "/test.css", "color: blue"),
            ("GET JavaScript file", "/script.js", "console.log"),
            ("GET text file", "/data.txt", "plain text"),
            ("GET subdirectory file", "/subdir/page.html", "Subdirectory"),
            ("GET large file", "/large.html", "AAAA"),
            ("GET explicit index", "/index.html", "Hello World"),
        ]
        
        for test_name, path, expected_content in tests:
            response = self.send_http_request(path=path)
            
            if response.is_success() and expected_content in response.body:
                self.print_status(f"{test_name}: PASS", 'PASS')
                self.test_results.append(('PASS', test_name))
            else:
                self.print_status(f"{test_name}: FAIL", 'FAIL')
                self.print_status(f"  Status: {response.get_status()}", 'FAIL')
                if response.body:
                    preview = response.body[:100].replace('\n', '\\n')
                    self.print_status(f"  Body preview: {preview}...", 'FAIL')
                self.test_results.append(('FAIL', test_name))
    
    def test_http_compliance(self):
        """Test HTTP protocol compliance"""
        self.print_status("=== HTTP COMPLIANCE TESTS ===", 'INFO')
        
        tests = [
            ("HTTP/1.0 request", "GET / HTTP/1.0\r\n\r\n", ["200"]),
            ("HTTP/1.1 with Host", "GET / HTTP/1.1\r\nHost: localhost\r\n\r\n", ["200"]),
            ("HTTP/1.1 without Host", "GET / HTTP/1.1\r\n\r\n", ["400"]),
            ("Invalid HTTP version", "GET / HTTP/2.0\r\nHost: localhost\r\n\r\n", ["505"]),
            ("POST method", "POST / HTTP/1.1\r\nHost: localhost\r\n\r\n", ["405"]),
            ("PUT method", "PUT / HTTP/1.1\r\nHost: localhost\r\n\r\n", ["405"]),
            ("DELETE method", "DELETE / HTTP/1.1\r\nHost: localhost\r\n\r\n", ["405"]),
        ]
        
        for test_name, raw_request, expected_codes in tests:
            response = self.send_raw_request(raw_request)
            
            success = any(code in response for code in expected_codes)
            if success:
                self.print_status(f"{test_name}: PASS", 'PASS')
                self.test_results.append(('PASS', test_name))
            else:
                self.print_status(f"{test_name}: FAIL", 'FAIL')
                self.print_status(f"  Expected: {expected_codes}, Got: {response[:100]}", 'FAIL')
                self.test_results.append(('FAIL', test_name))
    
    def send_raw_request(self, request_data, timeout=5):
        """Send raw HTTP request and return response"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))
            
            if isinstance(request_data, str):
                request_data = request_data.encode()
            
            sock.sendall(request_data)
            
            response = b""
            while True:
                try:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    response += chunk
                    time.sleep(0.01)  # Small delay to get complete response
                except socket.timeout:
                    break
            
            sock.close()
            
            return response.decode('utf-8', errors='ignore')
        except Exception as e:
            return f"ERROR: {str(e)}"

    def test_keep_alive(self):
        """Test explicit keep-alive functionality."""
        self.print_status("=== KEEP-ALIVE TEST ===", 'INFO')
        test_name = "Persistent connection (keep-alive)"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((self.host, self.port))

                # Request 1
                req1 = "GET /index.html HTTP/1.1\r\nHost: test\r\nConnection: keep-alive\r\n\r\n"
                sock.sendall(req1.encode())
                res1 = sock.recv(4096).decode()

                # Request 2
                req2 = "GET /test.css HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n"
                sock.sendall(req2.encode())
                res2 = sock.recv(4096).decode()
                
                # Check if both responses were successful
                if "200 OK" in res1 and "Hello World" in res1 and "200 OK" in res2 and "color: blue" in res2:
                    self.print_status(f"{test_name}: PASS", "PASS")
                    self.test_results.append(("PASS", test_name))
                else:
                    self.print_status(f"{test_name}: FAIL", "FAIL")
                    self.test_results.append(("FAIL", test_name))

        except Exception as e:
            self.print_status(f"{test_name}: FAIL with exception - {e}", "FAIL")
            self.test_results.append(("FAIL", test_name))
    
    def test_pipelining(self):
        """Test HTTP pipelining."""
        self.print_status("=== HTTP PIPELINING TEST ===", 'INFO')
        test_name = "Pipelined requests"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                sock.connect((self.host, self.port))

                # Send two requests back-to-back without waiting for a response
                req1 = "GET /index.html HTTP/1.1\r\nHost: test\r\n\r\n"
                req2 = "GET /data.txt HTTP/1.1\r\nHost: test\r\nConnection: close\r\n\r\n"
                pipelined_request = req1 + req2
                sock.sendall(pipelined_request.encode())

                # Receive all data
                full_response = b""
                while True:
                    try:
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        full_response += chunk
                    except socket.timeout:
                        break
                
                full_response_str = full_response.decode()

                # Check if we got two distinct successful responses
                if (full_response_str.count("200 OK") == 2 and
                    "Hello World" in full_response_str and
                    "plain text file" in full_response_str):
                    self.print_status(f"{test_name}: PASS", "PASS")
                    self.test_results.append(("PASS", test_name))
                else:
                    self.print_status(f"{test_name}: FAIL", "FAIL")
                    self.print_status(f"  Response Preview: {full_response_str[:200]}...", "FAIL")
                    self.test_results.append(("FAIL", test_name))

        except Exception as e:
            self.print_status(f"{test_name}: FAIL with exception - {e}", "FAIL")
            self.test_results.append(("FAIL", test_name))


    def test_error_handling(self):
        """Test error handling and edge cases"""
        self.print_status("=== ERROR HANDLING TESTS ===", 'INFO')
        
        tests = [
            ("404 Not Found", "/nonexistent.html", ["404"]),
            ("Directory without index", "/images/", ["403", "404"]), # 403 is also acceptable
            ("Very long URI", "/" + "a" * 3000, ["400", "414"]), # 414 URI too long
        ]
        
        for test_name, path, expected_codes in tests:
            response = self.send_http_request(path=path)
            
            success = any(code in response.status_code for code in expected_codes) if response.status_code else False
            if success:
                self.print_status(f"{test_name}: PASS", 'PASS')
                self.test_results.append(('PASS', test_name))
            else:
                self.print_status(f"{test_name}: FAIL", 'FAIL')
                self.print_status(f"  Expected: {expected_codes}, Got: {response.get_status()}", 'FAIL')
                self.test_results.append(('FAIL', test_name))
        
        # Test malformed requests
        malformed_tests = [
            ("Empty request", ""),
            ("Malformed request line", "INVALID REQUEST\r\n\r\n"),
            ("Missing HTTP version", "GET /\r\n\r\n"),
        ]
        
        for test_name, raw_request in malformed_tests:
            response = self.send_raw_request(raw_request)
            
            if "400" in response or "ERROR:" in response:
                self.print_status(f"{test_name}: PASS", 'PASS')
                self.test_results.append(('PASS', test_name))
            else:
                self.print_status(f"{test_name}: FAIL", 'FAIL')
                self.test_results.append(('FAIL', test_name))
    
    def test_security(self):
        """Test security features"""
        self.print_status("=== SECURITY TESTS ===", 'INFO')
        
        # Path traversal attempts
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\drivers\\etc\\hosts",
            "....//....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%2f..%2f..%2fetc%2fpasswd",
            "../",
            "../../",
            "../../../"
        ]
        
        for attempt in traversal_attempts:
            response = self.send_http_request(path=f"/{attempt}")
            
            # Should return 400, 403, or 404, not 200
            if response.is_success():
                self.print_status(f"Path traversal vulnerability: {attempt}", 'FAIL')
                self.test_results.append(('FAIL', f"Security: {attempt}"))
            else:
                self.print_status(f"Path traversal blocked: {attempt}", 'PASS')
                self.test_results.append(('PASS', f"Security: {attempt}"))
    
    def test_content_types(self):
        """Test content type handling"""
        self.print_status("=== CONTENT TYPE TESTS ===", 'INFO')
        
        expected_types = {
            '/': 'text/html',
            '/test.css': 'text/css',
            '/script.js': 'application/javascript',
            '/data.txt': 'text/plain',
        }
        
        for path, expected_type in expected_types.items():
            response = self.send_http_request(path=path)
            content_type = response.get_header('content-type')
            
            if expected_type in content_type:
                self.print_status(f"Content-Type {path}: PASS", 'PASS')
                self.test_results.append(('PASS', f"Content-Type: {path}"))
            else:
                self.print_status(f"Content-Type {path}: FAIL (got: {content_type})", 'FAIL')
                self.test_results.append(('FAIL', f"Content-Type: {path}"))
    
    def test_detailed_response_analysis(self):
        """Detailed analysis of server responses for debugging"""
        self.print_status("=== DETAILED RESPONSE ANALYSIS ===", 'INFO')
        
        response = self.send_http_request(path="/")
        
        self.print_status(f"Status: {response.get_status()}", 'INFO')
        self.print_status(f"Headers: {response.headers}", 'INFO')
        self.print_status(f"Body length: {len(response.body)}", 'INFO')
        self.print_status(f"Body preview: {response.body[:200]}...", 'INFO')
        
        # Try raw request for comparison
        raw_response = self.send_raw_request("GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        self.print_status(f"Raw response preview: {raw_response[:300]}...", 'INFO')
    
    def stress_test_concurrent_connections(self, num_threads=20, requests_per_thread=10):
        """Stress test with concurrent connections"""
        self.print_status(f"=== CONCURRENT STRESS TEST ({num_threads} threads, {requests_per_thread} req/thread) ===", 'STRESS')
        
        def worker_thread(thread_id):
            """Worker function for stress testing"""
            successes = 0
            failures = 0
            response_times = []
            
            for i in range(requests_per_thread):
                start_time = time.time()
                
                try:
                    # Random file selection for varied load
                    files = ['/', '/test.css', '/script.js', '/data.txt']
                    selected_file = random.choice(files)
                    
                    response = self.send_http_request(path=selected_file, timeout=10)
                    
                    end_time = time.time()
                    response_time = end_time - start_time
                    response_times.append(response_time)
                    
                    if response.is_success():
                        successes += 1
                    else:
                        failures += 1
                        
                except Exception as e:
                    failures += 1
                    end_time = time.time()
                    response_times.append(end_time - start_time)
            
            return thread_id, successes, failures, response_times
        
        # Execute stress test
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_thread, i) for i in range(num_threads)]
            
            total_successes = 0
            total_failures = 0
            all_response_times = []
            
            for future in as_completed(futures):
                thread_id, successes, failures, response_times = future.result()
                total_successes += successes
                total_failures += failures
                all_response_times.extend(response_times)
        
        end_time = time.time()
        total_time = end_time - start_time
        total_requests = num_threads * requests_per_thread
        
        # Calculate statistics
        if all_response_times:
            avg_response_time = statistics.mean(all_response_times)
            median_response_time = statistics.median(all_response_times)
            max_response_time = max(all_response_times)
            min_response_time = min(all_response_times)
            requests_per_second = total_requests / total_time
            
            # Results
            self.print_status(f"Total requests: {total_requests}", 'STRESS')
            self.print_status(f"Successes: {total_successes}", 'STRESS')
            self.print_status(f"Failures: {total_failures}", 'STRESS')
            self.print_status(f"Success rate: {(total_successes/total_requests)*100:.2f}%", 'STRESS')
            self.print_status(f"Total time: {total_time:.2f}s", 'STRESS')
            self.print_status(f"Requests/second: {requests_per_second:.2f}", 'STRESS')
            self.print_status(f"Response time - Avg: {avg_response_time*1000:.2f}ms, Median: {median_response_time*1000:.2f}ms", 'STRESS')
            self.print_status(f"Response time - Min: {min_response_time*1000:.2f}ms, Max: {max_response_time*1000:.2f}ms", 'STRESS')
            
            # Determine pass/fail
            success_rate = (total_successes / total_requests) * 100
            if success_rate >= 95 and avg_response_time < 2.0:  # 95% success rate, under 2s avg response
                self.print_status("Concurrent stress test: PASS", 'PASS')
                self.test_results.append(('PASS', 'Concurrent stress test'))
            else:
                self.print_status("Concurrent stress test: FAIL", 'FAIL')
                self.test_results.append(('FAIL', 'Concurrent stress test'))
        else:
            self.print_status("Concurrent stress test: FAIL (No response times recorded)", 'FAIL')
            self.test_results.append(('FAIL', 'Concurrent stress test'))
    
    def run_all_tests(self):
        """Run the complete test suite"""
        self.print_status("Starting HTTP Server Test Suite", 'INFO')
        self.print_status(f"Target: {self.base_url}", 'INFO')
        
        try:
            # Setup
            self.setup_test_environment()
            
            if not self.start_server():
                return False
            
            # Wait for server to be ready
            time.sleep(1)
            
            # Detailed analysis first
            self.test_detailed_response_analysis()
            
            # Basic functionality tests
            self.test_basic_functionality()
            self.test_http_compliance()
            self.test_keep_alive() # New Test
            self.test_pipelining() # New Test
            self.test_error_handling()
            self.test_content_types()
            self.test_security()
            
            # Stress tests (lighter for reliability)
            self.stress_test_concurrent_connections(20, 10)
            
            # Print summary
            self.print_test_summary()
            
        finally:
            self.stop_server()
            self.cleanup_test_environment()
    
    def print_test_summary(self):
        """Print test results summary"""
        self.print_status("=== TEST SUMMARY ===", 'INFO')
        
        passed = sum(1 for result, _ in self.test_results if result == 'PASS')
        failed = sum(1 for result, _ in self.test_results if result == 'FAIL')
        total = len(self.test_results)
        
        if total > 0:
            self.print_status(f"Total tests: {total}", 'INFO')
            self.print_status(f"Passed: {passed}", 'PASS')
            self.print_status(f"Failed: {failed}", 'FAIL')
            self.print_status(f"Success rate: {(passed/total)*100:.1f}%", 'INFO')
            
            if failed > 0:
                self.print_status("Failed tests:", 'FAIL')
                for result, test_name in self.test_results:
                    if result == 'FAIL':
                        self.print_status(f"  - {test_name}", 'FAIL')
    
    def cleanup_test_environment(self):
        """Clean up test files"""
        import shutil
        if os.path.exists('www'):
            shutil.rmtree('www')
        self.print_status("Test environment cleaned up", 'INFO')

def main():
    """Main function to run the test suite and handle logging."""
    host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8080
    
    # --- NEW LOGGING CODE STARTS HERE ---
    log_filename = f"test_results_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        with open(log_filename, 'w') as log_file:
            sys.stdout = log_file
            sys.stderr = log_file
            
            # Disable colors for clean log file
            Colors.disable()
            
            tester = HTTPServerTester(host, port)
            
            try:
                tester.run_all_tests()
            except KeyboardInterrupt:
                print(f"\nTest interrupted by user")
            except Exception as e:
                print(f"Test suite error: {e}")
                import traceback
                traceback.print_exc()
    finally:
        # Restore original stdout/stderr
        sys.stdout = original_stdout
        sys.stderr = original_stderr
            
    # Print final message to the console
    print(f"\n{Colors.BOLD}{Colors.GREEN}Tests complete. Results have been saved to:{Colors.END} {log_filename}")

if __name__ == "__main__":
    main()