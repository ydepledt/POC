#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include "map.h"
#include "prim.h"
#include "maze.h"

int findMinCostNode(int* cheapest, bool* explored, int numVertices) {
    int minCost = INFINITY;
    int minCostNode = -1;
    
    for (int i = 0; i < numVertices; i++) {
        if (!explored[i] && cheapest[i] < minCost) {
            minCost = cheapest[i];
            minCostNode = i;
        }
    }
    
    return minCostNode;
}

void prim(Map *map, Maze *maze) {
    
    int numVertices = map->height * map->width;
    int *cheapest   = malloc(numVertices * sizeof(int));
    bool *explored  = malloc(numVertices * sizeof(bool));

    for (int i = 0; i < numVertices; i++) {
        cheapest[i] = INFINITY;
        explored[i] = false;
    }

    int start = 0;
    cheapest[start] = 0;

    Neighbors *neighbors_struct = malloc(sizeof(Neighbors));

    while (true) {
        int minCostNode = findMinCostNode(cheapest, explored, numVertices);
        if (minCostNode == -1) {
            break; // No more nodes to explore
        }

        explored[minCostNode] = true;

        find_neighbors(map, neighbors_struct, minCostNode);

        for (int direction = BELOW; direction <= LEFT; direction++) {
            int neighbor = neighbors_struct->neighbors[direction];
            int cost     = neighbors_struct->costs[direction];

            if (neighbor != -1 && !explored[neighbor] && cost < cheapest[neighbor]) {
                cheapest[neighbor] = cost;
                maze->predecessors[neighbor] = minCostNode;
            }
        }

    }

    for (int i = 0; i < numVertices; i++) {
            maze->cost += cheapest[i];
    }

    free(neighbors_struct);
    free(cheapest);
    free(explored);
}