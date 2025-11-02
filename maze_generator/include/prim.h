#ifndef PRIM_H
#define PRIM_H

#include <stdio.h>
#include <stdlib.h>
#include "map.h"
#include "maze.h"

int findMinCostNode(int* cheapest, bool* explored, int numVertices);
void prim(Map *map, Maze *maze);

#endif /* PRIM_H */

