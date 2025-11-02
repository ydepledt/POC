
#include <stdio.h>
#include <stdlib.h>
#include "map.h"
#include "writer.h"

int main(int argc, char *argv[]) {
    if (argc < 3) {
        printf("Error: No size provided.\n");
        return EXIT_FAILURE;
    }

    int width  = atoi(argv[1]);
    int height = atoi(argv[2]);

    Map *map = create_random_map(width, height, -20, 20);
    if (map == NULL) {
        printf("Error: Could not create map.\n");
        return EXIT_FAILURE;
    }

    char subfix[100];
    sprintf(subfix, "%s", (argc == 4) ? argv[3] : "");

    write_map(map, subfix);
}
