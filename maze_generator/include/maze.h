#ifndef MAZE_H
#define MAZE_H

#include <stdio.h>
#include <stdlib.h>
#include "map.h"

typedef struct {
    int width;
    int height;
    int cost;
    int *predecessors;
} Maze;

Maze *create_maze(int width, int height);
void destroy_maze(Maze *maze);

void print_maze(Maze *maze);
void generate_image(Maze *maze, char *filename, int scaling_factor);

#endif /* MAZE_H */