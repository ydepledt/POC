#ifndef UNIVERSE_HPP
#define UNIVERSE_HPP

#include <iostream>
#include "Cell.hpp"

class Universe {
    public:
        Universe(int width, int height, int simulationStep = 100) : width(width), height(height), simulationStep(simulationStep), head(nullptr) {}
        ~Universe();
        
        static Universe* loadUniverse(std::string filepath);
        
        void saveUniverse(std::string filepath);
        void displayUniverse(std::string displayChar);
        void addCell(int coordx, int coordy);
        void removeCell(int coordx, int coordy);
        Cell* getCell(int coordx, int coordy);

        int countNeighbours(int coordx, int coordy);
        void updateCellStates();


    private:
        int width;
        int height;
        int simulationStep;
        Cell* head;
};

#endif