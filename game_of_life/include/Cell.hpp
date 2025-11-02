#ifndef CELL_HPP
#define CELL_HPP

#include <iostream>


class Cell {
public:
    Cell(int coordx, int coordy) : coordx(coordx), coordy(coordy), willDie(false), next(nullptr) {}
    Cell* next;
    bool willDie;

    int getCoordx() const { return coordx; }
    int getCoordy() const { return coordy; }

private:
    int coordx;
    int coordy;

};

#endif
