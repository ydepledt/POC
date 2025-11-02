#ifndef LOADER_H
#define LOADER_H

#include <stdio.h>
#include <stdlib.h>
#include "map.h"

Map *load_map(const char *filename);

#endif /* LOADER_H */