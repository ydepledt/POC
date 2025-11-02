#include <iostream>
#include "Universe.hpp"
#include "Cell.hpp"

int main() {
    
    Universe* universe = Universe::loadUniverse("files/glider.txt");

    Universe universeBis = Universe(10, 10, 100);
    universeBis.addCell(1, 1);
    universeBis.addCell(2, 1);
    universeBis.addCell(1, 2);
    universeBis.addCell(3, 4);
    universeBis.saveUniverse("test.txt");


    if (universe == nullptr) {
        return 1;
    }

    universe->displayUniverse("o");

    delete universe;

    return 0;
}