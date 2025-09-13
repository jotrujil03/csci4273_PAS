/** @file server.h
 *  @brief Main header file for PA1 - TCP Web Server.
 *
 *  This file contains all necessary includes, definitions, and function
 *  prototypes used across the server project.
 *
 *  @author Joshua Trujillo
 *  @identikey: jotr7489
 */

#ifndef SERVER_H
#define SERVER_H
#define _GNU_SOURCE

/* -- Definitions -- */
#define MAX_CONNECTIONS 50
#define BUFFER_SIZE 65536
#define DIRECTORY "./www/"

/* -- Includes -- */
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <sys/stat.h>
#include <limits.h>
#include <regex.h>
#include <ctype.h>
#include <signal.h>
#include <string.h>
#include <strings.h>
#include <fcntl.h>
#include <unistd.h>
#include <errno.h>

/* -- Functions Prototypes -- */
void *handle_client(void *arg);
void build_http_response(int file_fd,
                        const char *file_name,
                        const char *http_version,
                        char * response,
                        size_t *response_len,
                        size_t total_response_size,
                        int keep_alive);

char *url_decode(const char *str);
const char *get_file_extension(const char *file_name);
const char *get_mime_type(const char *file_ext);
void send_error_response(int client_fd, int status_code, 
                        const char *http_version, 
                        int keep_alive);

void handle_signal(int signum);
void cleanup_thread_resources(int client_fd, void *arg, 
                            char *buffer, char *file_name, 
                            char *response);
                            
int parse_connection_header(const char *buffer);

#endif // SERVER_H