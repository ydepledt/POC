#include <stdio.h>
#include <stdlib.h>
#include "map.h"
#include "loader.h"
#include "maze.h"
#include "prim.h"

int main(int argc, char *argv[]) {
    if (argc < 2) {
        printf("Error: No input file provided.\n");
        return EXIT_FAILURE;
    }

    Map *map = load_map(argv[1]);
    if (map == NULL) {
        printf("Error: Could not load map.\n");
        return EXIT_FAILURE;
    }

    int width = map->width;
    int height = map->height;

    Maze *maze = create_maze(width, height);
    if (maze == NULL) {
        printf("Error: Could not create maze.\n");
        destroy_map(map);
        return EXIT_FAILURE;
    }

    prim(map, maze);

    char filename[100];
    sprintf(filename, "./generated_maze/maze_%d_%d.pbm", width, height);

    int scaling_factor = (argc == 3) ? atoi(argv[2]) : 2;

    generate_image(maze, filename, scaling_factor);

    destroy_map(map);
    destroy_maze(maze);

    return EXIT_SUCCESS;
}
