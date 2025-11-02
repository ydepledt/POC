_GUI = $(if $(NOGUI),,-D GUI -Werror)
_DEBUG = $(if $(DEBUG),-D DEBUG,)
_OPT = $(if $(OPT),-O3 -flto,)
CC = gcc
CFLAGS = -g -std=c99 -Wall $(_OPT) $(_GUI) $(_DEBUG) -I./include
LDFLAGS = -lm

.PHONY: clean check-syntax compile-all

OBJ_DIR := obj
BIN_DIR := bin
SRC_DIR := src

# compile rules
$(OBJ_DIR)/%.o: $(SRC_DIR)/%.c
	$(CC) $(CFLAGS) -o $@ -c $< -I./include

$(OBJ_DIR)/%.o: ./tests/%.c
	$(CC) $(CFLAGS) -o $@ -c $<

# Variable for object files
OBJECTS = $(OBJ_DIR)/map.o $(OBJ_DIR)/maze.o $(OBJ_DIR)/loader.o $(OBJ_DIR)/writer.o $(OBJ_DIR)/prim.o

# Define targets for executables
main: $(OBJ_DIR)/main.o $(OBJECTS)
	$(CC) $(CFLAGS) -o $(BIN_DIR)/main $^ $(LDFLAGS) -I./include

app-generate-maze: $(OBJ_DIR)/app-generate-maze.o $(OBJECTS)
	$(CC) $(CFLAGS) -o $(BIN_DIR)/app-generate-maze $^ $(LDFLAGS) -I./include

app-generate-random-map: $(OBJ_DIR)/app-generate-random-map.o $(OBJECTS)
	$(CC) $(CFLAGS) -o $(BIN_DIR)/app-generate-random-map $^ $(LDFLAGS) -I./include

# put all your applications and tests executables as prerequisite of this rule
compile-all: main app-generate-maze app-generate-random-map

# rule to remove all .o files and all executables
clean:
	-rm -rf $(OBJ_DIR)/*.o $(BIN_DIR)/*

# rule to valgrind main
valgrind_main: main
	valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes $(BIN_DIR)/main

# rule to valgrind app-generate-maze
valgrind_app-generate-maze: app-generate-maze
	valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes $(BIN_DIR)/app-generate-maze

# rule to valgrind app-generate-random-maze
valgrind_app-generate-random-map: app-generate-random-map
	valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes $(BIN_DIR)/app-generate-random-map