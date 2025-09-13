# Makefile for the TCP Web Server
# Author: Joshua Trujillo
# identikey: jotr7489

# Compiler and compiler flags
CC = gcc
CFLAGS = -Wall -Wextra -g -std=c23
LDFLAGS = -pthread

# The name of the executable
TARGET = server

# The source file
SOURCES = server.c

# Default rule: build the executable
all: $(TARGET)

# Rule to link the object file into the final executable
$(TARGET): $(SOURCES)
	$(CC) $(CFLAGS) -o $(TARGET) $(SOURCES) $(LDFLAGS)
	@echo "Build complete: $(TARGET)"

# Phony targets are not actual files
.PHONY: all clean