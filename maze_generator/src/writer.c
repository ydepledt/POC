#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include "map.h"
#include "writer.h"

void write_map(Map *map, const char *subfix) {
    int width = map->width;
    int height = map->height;

    char filename[100];
    if (strcmp(subfix, "") == 0) {
        sprintf(filename, "data_map/map_%d_%d.txt", width, height);
    } 
    else {
        sprintf(filename, "data_map/map_%d_%d_%s.txt", width, height, subfix);
    }

    FILE *file = fopen(filename, "w");
    if (file == NULL) {
        fprintf(stderr, "Error: Could not open file.\n");
        exit(EXIT_FAILURE);
    }

    fprintf(file, "%d %d\n", width, height);

    for (int i = 0; i < height * width; i++) {
        fprintf(file, "%d %d\n", map->edges[i].down, map->edges[i].right);
    }
}
    