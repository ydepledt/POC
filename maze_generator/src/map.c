#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <time.h>
#include "map.h"

Map *create_map(int width, int height) {
    // Allocate memory for map struct
    Map *map = malloc(sizeof(Map));
    if (map == NULL) {
        printf("Memory allocation failed.\n");
        return NULL; // Memory allocation failed
    }

    map->width = width;
    map->height = height;

    // Allocate memory for edges array-like structure
    map->edges = (Edges*)malloc(height * width * sizeof(Edges));
    if (map->edges == NULL) {
        printf("Memory allocation failed.\n");
        free(map); // Free previously allocated memory
        return NULL; // Memory allocation failed
    }

    // Initialize edges (assuming all edges initially have cost 0)
    for (int i = 0; i < height * width; i++) {
        map->edges[i].down = 0;
        map->edges[i].right = 0;
    }

    return map;
}

Map *create_map_weighted(int width, int height, int down_size, int right_size, int *down, int *right) {
    // Allocate memory for map struct
    Map *map = malloc(sizeof(Map));
    if (map == NULL) {
        printf("Memory allocation failed.\n");
        return NULL; // Memory allocation failed
    }

    map->width = width;
    map->height = height;

    // Allocate memory for edges array-like structure
    map->edges = malloc(height * width * sizeof(Edges));
    if (map->edges == NULL) {
        printf("Memory allocation failed.\n");
        free(map); // Free previously allocated memory
        return NULL; // Memory allocation failed
    }

    // Check if down and right arrays are not NULL
    if (down == NULL || right == NULL) {
        free(map->edges); // Free previously allocated memory
        free(map); // Free previously allocated memory
        printf("Down and right arrays cannot be NULL.\n");
        return NULL; // Memory allocation failed
    }
    
    // Check if down and right len are not greater than height * width
    if (down_size > height * width || right_size > height * width) {
        free(map->edges); // Free previously allocated memory
        free(map); // Free previously allocated memory
        printf("Down and right arrays cannot be greater than %d.\n", height * width);
        return NULL; // Memory allocation failed
    }

    // Initialize edges with down and right arrays and 0 after the arrays
    for (int i = 0; i < height * width; i++) {
        map->edges[i].down = (i < down_size) ? down[i] : 0;
        map->edges[i].right = (i < right_size) ? right[i] : 0;
    }

    return map;
}

Map *create_random_map(int height, int width, int min_weight, int max_weight) {
    // Initialize random number generator
    srand(time(NULL));

    // Allocate memory for map struct
    Map *map = malloc(sizeof(Map));
    if (map == NULL) {
        printf("Memory allocation failed.\n");
        return NULL; // Memory allocation failed
    }

    map->width = width;
    map->height = height;

    // Allocate memory for edges array-like structure
    map->edges = malloc(height * width * sizeof(Edges));
    if (map->edges == NULL) {
        free(map); // Free previously allocated memory
        return NULL; // Memory allocation failed
    }

    // Initialize edges with random values
    for (int i = 0; i < height * width; i++) {
        map->edges[i].down  = rand() % (max_weight - min_weight + 1) + min_weight;
        map->edges[i].right = rand() % (max_weight - min_weight + 1) + min_weight;
    }

    return map;

}

void destroy_map(Map *map) {
    if (map != NULL) {
        if (map->edges != NULL) {
            free(map->edges);
        }
        free(map);
    }
}

void print_map(Map* map) {
    if (map == NULL) {
        printf("Map is not initialized.\n");
        return;
    }
    else if (map->edges == NULL) {
        printf("Map edges are not initialized.\n");
        return;
    }

    printf("Map:\n");
    for (int i = 0; i < map->height; i++) {
        for (int j = 0; j < map->width; j++) {
            printf("(%d, %d) ", map->edges[i * map->width + j].down, map->edges[i * map->width + j].right);
        }
        printf("\n");
    }
}

bool validate_input(Map *map, int row, int col) {
    if (map == NULL) {
        printf("Map is not initialized.\n");
        return false;
    }
    else if (map->edges == NULL) {
        printf("Map edges are not initialized.\n");
        return false;
    }
    else if (row < 0 || row >= map->height) {
        printf("Invalid row index.\n");
        printf("Please select a row between 0 and %d.\n", map->height - 1);
        return false;
    }
    else if (col < 0 || col >= map->width) {
        printf("Invalid column index.\n");
        printf("Please select a column between 0 and %d.\n", map->width - 1);
        return false;
    }
    return true;
}

void change_edge_down_right(Map *map, int row, int col, int down, int right) {
    if (!validate_input(map, row, col)) {
        return;
    }

    map->edges[row * map->width + col].down = down;
    map->edges[row * map->width + col].right = right;
}

void change_edge_down(Map *map, int row, int col, int down) {
    if (!validate_input(map, row, col)) {
        return;
    }

    map->edges[row * map->width + col].down = down;
}

void change_edge_right(Map *map, int row, int col, int right) {
    if (!validate_input(map, row, col)) {
        return;
    }

    map->edges[row * map->width + col].right = right;
}

void find_neighbors_row_col(Map *map, Neighbors *neighbors, int row, int col) {
    if (!validate_input(map, row, col)) {
        return;
    }

    neighbors->nb = 0;

    int height = map->height;
    int width  = map->width;

    if (row < height - 1) {
        neighbors->neighbors[BELOW] = (row + 1) * width + col;
        neighbors->costs[BELOW] = map->edges[row * width + col].down;
        neighbors->nb++;
    }
    else {
        neighbors->neighbors[BELOW] = -1;
        neighbors->costs[BELOW] = INFINITY;
    }

    if (col < width - 1) {
        neighbors->neighbors[RIGHT] = row * width + col + 1;
        neighbors->costs[RIGHT] = map->edges[row * width + col].right;
        neighbors->nb++;
    }
    else {
        neighbors->neighbors[RIGHT] = -1;
        neighbors->costs[RIGHT] = INFINITY;
    }

    if (row > 0) {
        neighbors->neighbors[ABOVE] = (row - 1) * width + col;
        neighbors->costs[ABOVE] = map->edges[(row - 1) * width + col].down;
        neighbors->nb++;
    }
    else {
        neighbors->neighbors[ABOVE] = -1;
        neighbors->costs[ABOVE] = INFINITY;
    }

    if (col > 0) {
        neighbors->neighbors[LEFT] = row * width + col - 1;
        neighbors->costs[LEFT] = map->edges[row * width + col - 1].right;
        neighbors->nb++;
    }
    else {
        neighbors->neighbors[LEFT] = -1;
        neighbors->costs[LEFT] = INFINITY;
    }
}

void find_neighbors(Map *map, Neighbors *neighbors, int nb_node) {
    int row = nb_node / map->width;
    int col = nb_node % map->width;
    find_neighbors_row_col(map, neighbors, row, col);
}
