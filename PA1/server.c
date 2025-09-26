/** @file server.c
 * @brief Main server logic file used in conjuction
 * with server.h.
 *
 * @usage: ./server <PORT#>
 *
 * @author Joshua Trujillo
 * @identikey: jotr7489
 */

#include "server.h"

/* Global variables -- */
static int self_pipe[2]; // Cheeky little method to wake up select() so SIGINT is immediate

/* -- Main functions -- */

/**
 * @brief Safely frees all dynamically allocated memory and closes file 
 * descriptors associated with a single client-handling thread. This is a 
 * crucial function for preventing memory leaks and resource exhaustion.
 * @param client_fd The client's socket file descriptor.
 * @param arg The dynamically allocated argument passed to the thread.
 * @param buffer The dynamically allocated buffer for requests.
 * @param file_name The dynamically allocated string for the file name.
 * @param response The dynamically allocated buffer for the response.
 */
void cleanup_thread_resources(int client_fd, void *arg, 
                            char *buffer, char *file_name, 
                            char *response) 
{
    if (client_fd >= 0) {
        close(client_fd);
    }
    if (arg) {
        free(arg);
    }
    if (buffer) {
        free(buffer);
    }
    if (file_name) {
        free(file_name);
    }
    if (response) {
        free(response);
    }
}

/**
 * @brief Gracefully handles termination signals like SIGINT (from pressing Ctrl+C)
 * or SIGTERM. It uses the "self-pipe trick" where it writes a single dummy
 * byte into a pipe. The main server loop is blocked on select(), waiting for
 * activity on the server socket OR this pipe. Writing to the pipe "wakes up"
 * select(), allowing the main loop to break and the server to shut down cleanly.
 * @param signum The signal number that was caught.
 */
void handle_signal(int signum)
{
    (void)signum; // Silence compiler!, For I am the Creator

    // Write a byte to the pipe to unblock select()
    char dummy = 'x';
    write(self_pipe[1], &dummy, 1);
}

/**
 * @brief Creates and sends a standard HTTP error response to the client 
 * (e.g., 404 Not Found, 403 Forbidden).
 * @param client_fd The socket file descriptor for the client.
 * @param status_code The integer HTTP status code (e.g., 404).
 * @param http_version The HTTP version string (e.g., "HTTP/1.1").
 * @param keep_alive An integer flag (1 or 0) indicating if the connection
 * should be kept open.
 */
void send_error_response(int client_fd, int status_code, 
                        const char *http_version, int keep_alive) 
{
    char response[BUFFER_SIZE];
    const char *status_message;

    // Determine the message based on the status code
    if (status_code == 404) {
        status_message = "Not Found";
    } else if (status_code == 403) {
        status_message = "Forbidden";
    } else if (status_code == 405) {
        status_message = "Method Not Allowed";
    } else if (status_code == 505) {
        status_message = "HTTP Version Not Supported";
    } else if (status_code == 500) {
        status_message = "Internal Server Error";
    } else {
        // Default to a generic bad request for other errors
        status_code = 400;
        status_message = "Bad Request";
    }

    // Create the body first to calculate Content-Length
    char body[256];
    int body_len = snprintf(body, sizeof(body), "%d %s", status_code, status_message);

    // Use snprintf to safely build the HTTP response with proper version and connection handling
    const char *connection_header = keep_alive ? "Keep-alive" : "close";
    snprintf(response, sizeof(response),
             "%s %d %s\r\n"
             "Content-Type: text/plain\r\n"
             "Content-Length: %d\r\n"
             "Connection: %s\r\n"
             "\r\n"
             "%s",
             http_version, status_code, status_message, body_len, connection_header, body);

    // Send the response and ignore potential errors for this simple server
    send(client_fd, response, strlen(response), 0);
}

/**
 * @brief Creates a successful HTTP 200 OK response, including all necessary 
 * headers and the complete content of the requested file. It efficiently 
 * builds the entire response (headers and file body) into a single buffer
 * before sending.
 * @param file_fd The file descriptor for the open file to be sent.
 * @param file_name The name of the file, used to determine MIME type.
 * @param http_version The HTTP version string (e.g., "HTTP/1.1").
 * @param response The output buffer where the full response will be built.
 * @param response_len A pointer to a size_t variable that will store the final
 * total length of the response.
 * @param total_response_size The total allocated size of the response buffer.
 * @param keep_alive An integer flag (1 or 0) indicating if the connection
 * should be kept open.
 */
void build_http_response(int file_fd, const char *file_name, 
                        const char *http_version, 
                        char *response, size_t *response_len, 
                        size_t total_response_size, int keep_alive)
{
    struct stat file_stat;
    fstat(file_fd, &file_stat);
    off_t file_size = file_stat.st_size;

    const char *mime_type = get_mime_type(get_file_extension(file_name));
    const char *connection_header = keep_alive ? "Keep-alive" : "close";
    
    char header[BUFFER_SIZE];
    int header_len = snprintf(header, BUFFER_SIZE, 
                            "%s 200 OK\r\n"
                            "Content-Type: %s\r\n"
                            "Content-Length: %ld\r\n"
                            "Connection: %s\r\n"
                            "\r\n",
                            http_version, mime_type, file_size, connection_header);

    memcpy(response, header, header_len);
    *response_len = header_len;

    ssize_t bytes_read;
    while ((bytes_read = read(file_fd, response + *response_len, total_response_size - *response_len)) > 0)
    {
        *response_len += bytes_read;
    }
}

/**
 * @brief A simple utility function to extract the extension from a file name.
 * It finds the last occurrence of a '.' character in the file name and returns
 * a pointer to the character that follows it.
 * @param file_name The full name of the file.
 * @return A pointer to the start of the file extension string.
 */
const char *get_file_extension(const char *file_name)
{
    const char *dot = strrchr(file_name, '.');
    if (!dot || dot == file_name)
    {
        return "";
    }
    return dot + 1;
}

/**
 * @brief Maps a file extension to its corresponding standard MIME type. This is
 * necessary for the browser to correctly interpret the content being sent.
 * It defaults to "application/octet-stream" for unknown file types.
 * @param file_ext The file extension string (e.g., "html", "jpg").
 * @return A string literal representing the MIME type.
 */
const char *get_mime_type(const char *file_ext)
{
    if (strcasecmp(file_ext, "html") == 0 || strcasecmp(file_ext, "htm") == 0 )
    {
        return "text/html";
    } else if (strcasecmp(file_ext, "txt") == 0)
    {
        return "text/plain";
    } else if (strcasecmp(file_ext, "css") == 0)
    {
        return "text/css";
    } else if (strcasecmp(file_ext, "jpg") == 0 || strcasecmp(file_ext, "jpeg") == 0)
    {
        return "image/jpg";  // Assignment specifies "image/jpg"
    } else if (strcasecmp(file_ext, "png") == 0)
    {
        return "image/png";
    } else if (strcasecmp(file_ext, "gif") == 0)
    {
        return "image/gif";
    } else if (strcasecmp(file_ext, "ico") == 0)
    {
        return "image/x-icon";
    } else if (strcasecmp(file_ext, "js") == 0)
    {
        return "application/javascript";
    } else {
        return "application/octet-stream";
    }
}

/**
 * @brief Decodes a URL-encoded string. Web browsers replace special characters
 * in URLs with '%' followed by a two-digit hexadecimal code (e.g., a space
 * becomes "%20"). This function converts those codes back into their actual
 * characters.
 * @param str The URL-encoded input string.
 * @return A new, dynamically allocated string with the URL decoded. The caller
 * is responsible for freeing this memory.
 */
char *url_decode(const char *str) 
{
    size_t str_len = strlen(str);
    char *decoded = malloc(str_len + 1);
    if (!decoded) return NULL;
    
    size_t decoded_len = 0;

    for (size_t i = 0; i < str_len; i++)
    {
        if (str[i] == '%' && i + 2 < str_len)
        {
            int hex_val;
            if (sscanf(str + i + 1, "%2x", &hex_val) == 1) {
                decoded[decoded_len++] = (char)hex_val;
                i += 2;
            } else {
                decoded[decoded_len++] = str[i];
            }
        } else {
            decoded[decoded_len++] = str[i];
        }
    }

    decoded[decoded_len] = '\0';
    return decoded;
}

/**
 * @brief Checks the "Connection:" header in an HTTP request to see if the
 * client has requested to use a persistent connection ("keep-alive").
 * @param buffer The buffer containing the full HTTP request from the client.
 * @return 1 if "Connection: Keep-alive" is found, 0 otherwise.
 */
int parse_connection_header(const char *buffer) {
    // Look for Connection header in the request
    const char *connection_line = strcasestr(buffer, "Connection:");
    if (!connection_line) {
        return 0; // No connection header, default to close
    }
    
    // Check for keep-alive
    if (strcasestr(connection_line, "Keep-alive")) {
        return 1;
    }
    
    return 0; // Default to close
}

/**
 * @brief The core worker function that runs in its own thread for each 
 * connected client. It is responsible for reading, parsing, and responding 
 * to one or more HTTP requests from that client. It supports HTTP pipelining
 * by looping to process multiple requests on the same connection if it is
 * kept alive.
 * * @details
 * 1.  **Setup**: Allocates a buffer and sets a socket timeout to prevent hangs.
 * 2.  **Main Loop**: Enters a loop to handle multiple requests on one connection.
 * 3.  **Receive & Parse**: Reads data, looks for the end-of-headers marker
 * ("\r\n\r\n"), and parses the request line (method, URI, version).
 * 4.  **Validation & Security**:
 * - Determines `keep-alive` status.
 * - Validates the method (`GET`), HTTP version, and presence of `Host` header.
 * - Prevents path traversal attacks by checking for ".." and using `realpath()`
 * to ensure the requested file is within the designated web root directory.
 * 5.  **Serve File**: If all checks pass, it opens the file, calls 
 * `build_http_response()` to construct the full response, and sends it.
 * 6.  **Pipelining Support**: After processing, it uses `memmove()` to shift any
 * remaining data in the buffer to the beginning, preparing for the next request.
 * 7.  **Cleanup**: When the loop ends (connection closes), it calls
 * `cleanup_thread_resources()` to free all memory and close the socket.
 * * @param arg A void pointer to a dynamically allocated integer containing the
 * client's socket file descriptor.
 * @return NULL when the thread is finished.
 */
void *handle_client(void *arg) 
{
    const char *web_root = DIRECTORY;
    int client_fd = *((int *)arg);
    char *buffer = (char *)malloc(BUFFER_SIZE * sizeof(char));
    
    // Buffer management variables for pipelining
    ssize_t buffer_len = 0;
    char *request_start = buffer;

    if (!buffer) {
        cleanup_thread_resources(client_fd, arg, NULL, NULL, NULL);
        return NULL;
    }

    // Set a timeout for the socket
    struct timeval timeout;
    timeout.tv_sec = 10; // 10 second timeout
    timeout.tv_usec = 0;
    setsockopt(client_fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));

    while (1) { // Main loop to handle multiple requests
        // Find the end of a complete HTTP request
        char *request_end = strstr(request_start, "\r\n\r\n");

        if (!request_end) {
            // No complete request in buffer, try to receive more data
            ssize_t bytes_received = recv(client_fd, buffer + buffer_len, BUFFER_SIZE - buffer_len - 1, 0);
            if (bytes_received <= 0) {
                // Client disconnected or timeout occurred
                break;
            }
            buffer_len += bytes_received;
            buffer[buffer_len] = '\0';
            request_start = buffer; // Start parsing from the beginning again
            if (buffer_len > 0) continue; 
            else break;
        }

        char method[16], uri[2048], version_str[16];
        char http_version_full[32] = "HTTP/1.1";
        char *file_name = NULL;
        char *response = NULL;
        
        request_end[2] = '\0'; // Temporarily terminate string for safe parsing

        if (sscanf(request_start, "%15s %2047s HTTP/%15s", method, uri, version_str) != 3) {
            send_error_response(client_fd, 400, http_version_full, 0);
            break;
        }

        snprintf(http_version_full, sizeof(http_version_full), "HTTP/%s", version_str);

        int keep_alive = (strcmp(version_str, "1.1") == 0);
        if (strcasestr(request_start, "Connection:") && strcasestr(request_start, "close")) {
            keep_alive = 0;
        } else if (strcmp(version_str, "1.0") == 0 && strcasestr(request_start, "Connection:") && strcasestr(request_start, "keep-alive")) {
            keep_alive = 1;
        }
        
        if (strcmp(version_str, "1.1") == 0 && strcasestr(request_start, "Host:") == NULL)
        {
            send_error_response(client_fd, 400, http_version_full, 0);
            keep_alive = 0;
        }

        if (strcmp(method, "GET") != 0) {
            send_error_response(client_fd, 405, http_version_full, keep_alive);
        } else if (strcmp(version_str, "1.0") != 0 && strcmp(version_str, "1.1") != 0) {
            send_error_response(client_fd, 505, "HTTP/1.1", 0);
            keep_alive = 0;
        } else {
            file_name = url_decode(uri + 1);
            if (!file_name) {
                send_error_response(client_fd, 500, http_version_full, 0);
                keep_alive = 0;
            } else {
                if (file_name[0] == '\0' || file_name[strlen(file_name)-1] == '/') {
                    char path_html[PATH_MAX];
                    snprintf(path_html, sizeof(path_html), "%s%sindex.html", web_root, file_name);

                    // Check if index.html exists
                    if (access(path_html, F_OK) == 0) {
                        strcat(file_name, "index.html");
                    } else {
                        // If not, check for index.htm
                        strcat(file_name, "index.htm");
                    }
                }

                if (strstr(file_name, "..") != NULL) {
                     send_error_response(client_fd, 403, http_version_full, keep_alive);
                } else {
                    char full_path[PATH_MAX];
                    snprintf(full_path, sizeof(full_path), "%s%s", web_root, file_name);

                    char resolved_path[PATH_MAX];
                    if (realpath(full_path, resolved_path) == NULL) {
                        if (errno == EACCES) send_error_response(client_fd, 403, http_version_full, keep_alive);
                        else if (errno == ENOENT) send_error_response(client_fd, 404, http_version_full, keep_alive);
                        else send_error_response(client_fd, 500, http_version_full, keep_alive);
                    } else {
                        char root_path_real[PATH_MAX];
                        realpath(web_root, root_path_real);
                        
                        if (strncmp(resolved_path, root_path_real, strlen(root_path_real)) != 0) {
                            send_error_response(client_fd, 403, http_version_full, keep_alive);
                        } else {
                            struct stat file_stat;
                            if (stat(resolved_path, &file_stat) < 0) {
                                 if (errno == EACCES) send_error_response(client_fd, 403, http_version_full, keep_alive);
                                 else send_error_response(client_fd, 404, http_version_full, keep_alive);
                            } else {
                                 int file_fd = open(resolved_path, O_RDONLY);
                                 if (file_fd < 0) {
                                     if (errno == EACCES) send_error_response(client_fd, 403, http_version_full, keep_alive);
                                     else send_error_response(client_fd, 404, http_version_full, keep_alive);
                                 } else {
                                     off_t file_size = file_stat.st_size;
                                     size_t response_size = file_size + 1024;
                                     response = (char *)malloc(response_size);
                                     if (response) {
                                        size_t response_len;
                                        build_http_response(file_fd, resolved_path, http_version_full, response, &response_len, response_size, keep_alive);
                                        send(client_fd, response, response_len, 0);
                                        free(response);
                                     } else {
                                         send_error_response(client_fd, 500, http_version_full, 0);
                                         keep_alive = 0;
                                     }
                                     close(file_fd);
                                 }
                            }
                        }
                    }
                }
            }
        }
        if (file_name) free(file_name);
        
        request_end[2] = '\r'; // Restore buffer

        size_t processed_len = (request_end + 4) - request_start;
        
        buffer_len -= processed_len;
        memmove(buffer, request_start + processed_len, buffer_len);
        buffer[buffer_len] = '\0';
        request_start = buffer;

        if (!keep_alive) {
            break;
        }
    }

    cleanup_thread_resources(client_fd, arg, buffer, NULL, NULL);
    return NULL;
}

/**
 * @brief The entry point of the server application. It is responsible for
 * setting up the listening socket, accepting incoming client connections,
 * and creating a new thread for each one. It also sets up signal handling
 * for a graceful shutdown.
 * * @details
 * 1.  **Argument Check**: Verifies that the user provided a port number.
 * 2.  **Socket Setup**: Performs the standard `socket()`, `setsockopt()`, `bind()`,
 * and `listen()` sequence to prepare the server to accept connections.
 * 3.  **Signal & Pipe Setup**: Creates the self-pipe and registers the
 * `handle_signal` function for graceful shutdown on `SIGINT` or `SIGTERM`.
 * 4.  **Event Loop**: Enters the main `while(1)` loop, using `select()` to wait
 * for activity on either the listening socket (new connection) or the
 * self-pipe (shutdown signal).
 * 5.  **Thread Creation**: When a new connection is accepted via `accept()`, it
 * creates a new, detached thread using `pthread_create()` and `pthread_detach()`,
 * assigning the `handle_client` function to manage that specific client.
 * 6.  **Shutdown**: Once the loop is broken by a signal, it prints a shutdown
 * message and closes all open file descriptors before exiting.
 * * @param argc The number of command-line arguments.
 * @param argv An array of command-line argument strings.
 * @return 0 on successful shutdown, non-zero on failure.
 */
int main(int argc, char** argv)
{
    if (argc != 2)
    {
        printf("Usage: ./server <PORT>\n");
        exit(-1);
    }

    int server_fd;
    int port = atoi(argv[1]);
    struct sockaddr_in server_addr;

    // Create server socket
    if ((server_fd = socket(AF_INET, SOCK_STREAM, 0)) < 0)
    {
        perror("Error: Socket creation failed.");
        exit(EXIT_FAILURE);
    }

    // Config socket
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = INADDR_ANY;
    server_addr.sin_port = htons(port);

    int opt = 1;
    if (setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt))) {
        perror("Error: Setting socket options.");
        close(server_fd);
        exit(EXIT_FAILURE);
    }

    // Bind socket to port
    if (bind(server_fd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0)
    {
        perror("Error: Socket binding failed.");
        close(server_fd);
        exit(EXIT_FAILURE);
    }

    // Listen for connections on socket
    if (listen(server_fd, MAX_CONNECTIONS) < 0)
    {
        perror("Error: Listening on socket failed.");
        close(server_fd);
        exit(EXIT_FAILURE);
    }

    if (pipe(self_pipe) < 0) {
        perror("Error: Creating pipe failed.");
        close(server_fd);
        exit(EXIT_FAILURE);
    }
    
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    printf("Server is listening on port %d. Press Ctrl+C to exit.\n", port);

    while(1)
    {   
        fd_set read_fds;
        FD_ZERO(&read_fds);
        FD_SET(server_fd, &read_fds);
        FD_SET(self_pipe[0], &read_fds);

        int max_fd = (server_fd > self_pipe[0]) ? server_fd : self_pipe[0];

        // Wait indefinitely for activity on either the socket or the pipe
        if (select(max_fd + 1, &read_fds, NULL, NULL, NULL) < 0) {
            perror("Error: select failed");
            continue;
        }

        // If pipe has data, signal was caught
        if (FD_ISSET(self_pipe[0], &read_fds))
        {
            break;
        }

        if (FD_ISSET(server_fd, &read_fds))
        {
            // Client info
            struct sockaddr_in client_addr;
            socklen_t client_addr_len = sizeof(client_addr);
            int client_socket;

            // Accept client connection
            client_socket = accept(server_fd, (struct sockaddr *)&client_addr, &client_addr_len);
            
            // Check if accept() failed
            if (client_socket < 0)
            {
                perror("Error: Accepting failed.");
                continue;
            }

            int *client_fd = malloc(sizeof(int));
            if (client_fd == NULL) {
                perror("Error: Could not allocate memory for thread.");
                close(client_socket);
                continue;
            }
            *client_fd = client_socket;

            // Create new thread to handle client request
            pthread_t thread_id;
            if (pthread_create(&thread_id, NULL, handle_client, (void *)client_fd) != 0)
            {
                perror("Error: Failed to create thread.");
                close(*client_fd); 
                free(client_fd);
                continue;
            }
            
            // Detach the thread so its resources are cleaned up automatically on exit
            pthread_detach(thread_id);
        }
    }

    printf("\nShutting down server...\n");
    close(server_fd);
    close(self_pipe[0]);
    close(self_pipe[1]);
    return 0;
}