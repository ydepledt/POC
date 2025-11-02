#ifndef MAP_H
#define MAP_H

#include <stdbool.h>

#define INFINITY 999999

typedef enum {
    BELOW,
    RIGHT,
    ABOVE,
    LEFT
} Direction;

// Structure for edges
typedef struct {
    int down;           // Cost of edge going down
    int right;          // Cost of edge going right
} Edges;

// Structure for map
typedef struct {
    int height;         // Height of the map
    int width;          // Width of the map
    Edges *edges;       // Pointer to edges array
} Map;

// Structure for neighbors
typedef struct {
    int nb;             // Number of neighbors
    int neighbors[4];   // Array of neighbors
    int costs[4];       // Array of costs
} Neighbors;

// Function prototypes
Map *create_map(int height, int width);
Map *create_map_weighted(int width, int height, int down_size, int right_size, int *down, int *right);
Map *create_random_map(int height, int width, int min_weight, int max_weight);
void destroy_map(Map *map);
void print_map(Map* map);

bool validate_input(Map *map, int row, int col);
void change_edge_down_right(Map *map, int row, int col, int down, int right);
void change_edge_down(Map *map, int row, int col, int down);
void change_edge_right(Map *map, int row, int col, int right);

void find_neighbors(Map *map, Neighbors *neighbors, int nb_node);
void find_neighbors_row_col(Map *map, Neighbors *neighbors, int row, int col);



#endif /* MAP_H */
